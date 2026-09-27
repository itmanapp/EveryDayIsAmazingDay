"""更新檢查子系統（TASK-032／AC-059）：manifest 讀取、快取與六條架構約束。

**只顯示版本資訊，不下載、不安裝**：本模組只讀 manifest 的顯示欄位，不碰 `url`／
`sha256` 指向的檔案，也不寫安裝目錄。六條約束（報告第 6.5 節）逐條落在這裡：

1. **逾時上限 5 秒**：`_get_with_deadline` 以 worker 執行緒 ＋ `join(timeout)` 給出**硬上限**。
   只把 `timeout=` 傳給 socket 不夠——慢速滴水的伺服器可以拖過 socket 逾時。
2. **絕不阻塞啟動／網頁回應／監控輪詢**：`background=True` 立刻回傳快取（沒有快取時為
   `pending`），實際檢查交給注入的 `executor`（未提供時用 daemon 執行緒）。
3. **失敗一律靜默，只記狀態**：所有例外都收斂成 `UpdateState.error`，不印出、不記 ERROR。
4. **網頁先回快取**：呼叫端立即拿到 `source="cache"` 的結果。
5. **去抖動 5 分鐘**：以快取檔的 `checked_at` 判斷，因此**跨程序**有效。
6. **可完全關閉**：`enabled=False` 時不發請求、不建立執行緒，回 `source="disabled"`。

時間一律由呼叫端以 `now` 注入；本模組不讀系統時鐘（測試以原始碼斷言這一點）。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .errors import ConfigError, SourceError

if TYPE_CHECKING:  # pragma: no cover - 只為型別檢查
    from .markets.catalog import UpdateResult

__all__ = [
    "DEFAULT_DEBOUNCE_SECONDS",
    "DEFAULT_TIMEOUT",
    "UPDATE_SOURCES",
    "UpdateState",
    "check_update",
    "fetch_catalog",
    "http_get",
    "load_cache",
    "parse_manifest",
    "save_cache",
]

#: 單次請求的逾時上限（報告第 6.5 節第 1 條）。
DEFAULT_TIMEOUT = 5.0
#: 同一時窗內不重複發出請求（第 5 條）。
DEFAULT_DEBOUNCE_SECONDS = 300
#: `UpdateState.source` 的值域：顯示資料來自哪裡（`pending`＝背景檢查進行中）。
UPDATE_SOURCES = ("network", "cache", "disabled", "pending")

logger = logging.getLogger("ediaad.update")

#: manifest 只用於顯示的欄位（失敗時要保留上一份的這些值）。
_DISPLAY_FIELDS = (
    "latest_version",
    "released_at",
    "min_supported",
    "notes",
    "catalog_version",
    "catalog_url",
)
#: 可以是 `null` 的顯示欄位；`latest_version` 與 `released_at` 是 manifest 的必要欄位。
_OPTIONAL_FIELDS = ("min_supported", "notes", "catalog_version", "catalog_url")
_TEXT_FIELDS = _DISPLAY_FIELDS + ("checked_at", "error")


def _stamp(moment: datetime) -> str:
    """UTC ISO 時間字串（與租約的 `expires_at` 同一種寫法）。"""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_stamp(text: str) -> datetime:
    """解析快取裡的時間字串；naive 一律視為 UTC。"""
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


@dataclass(frozen=True)
class UpdateState:
    """最近一次更新檢查的結果（顯示欄位 ＋ 這次檢查的來源與錯誤）。"""

    latest_version: str | None = None
    released_at: str | None = None
    min_supported: str | None = None
    notes: str | None = None
    catalog_version: str | None = None
    catalog_url: str | None = None
    checked_at: str | None = None
    source: str = "pending"
    error: str | None = None

    def to_json(self) -> str:
        """正規 JSON（鍵排序、無多餘空白）：快取檔的唯一定義。"""
        return json.dumps(
            asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    @classmethod
    def from_json(cls, text: str) -> "UpdateState":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise ConfigError(f"更新快取不是合法 JSON：{error}") from error
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, payload: Any) -> "UpdateState":
        if not isinstance(payload, Mapping):
            raise ConfigError(
                f"更新快取必須是 JSON 物件，收到 {type(payload).__name__}"
            )
        unknown = sorted(set(payload) - set(cls.__dataclass_fields__))
        if unknown:
            raise ConfigError(f"更新快取含未知鍵：{'、'.join(unknown)}")

        values: dict[str, Any] = {}
        for name in _TEXT_FIELDS:
            value = payload.get(name)
            if value is not None and not isinstance(value, str):
                raise ConfigError(
                    f"更新快取的 {name} 必須是字串或 null，收到 {type(value).__name__}"
                )
            values[name] = value
        source = payload.get("source", "pending")
        if source not in UPDATE_SOURCES:
            raise ConfigError(
                f"更新快取的 source 必須是 {'／'.join(UPDATE_SOURCES)} 之一，收到 {source!r}"
            )
        values["source"] = source
        return cls(**values)

    def display_fields(self) -> dict[str, Any]:
        """只含顯示欄位（失敗時保留上一份的已知資訊，不抹成 `None`）。"""
        return {name: getattr(self, name) for name in _DISPLAY_FIELDS}

    def is_stale(self, now: datetime, debounce_seconds: int = DEFAULT_DEBOUNCE_SECONDS) -> bool:
        """是否已超過去抖動時窗（沒有 `checked_at` 或無法解讀時視為過期）。"""
        if self.checked_at is None:
            return True
        try:
            checked = _parse_stamp(self.checked_at)
        except ValueError:
            return True
        return (now - checked).total_seconds() >= debounce_seconds


def load_cache(path: str | Path) -> UpdateState | None:
    """讀取快取；檔案不存在、損毀或內容不合法時回 `None`（**絕不拋例外**）。

    版本頁是唯讀介面，一份壞掉的快取不該讓它整個壞掉——這個判斷與「有快取但過期」
    不同，因此以 `None` 表示「沒有可用的快取」。
    """
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        return UpdateState.from_json(text)
    except ConfigError as error:
        logger.debug("更新快取無法解讀（%s）：%s", target, error)
        return None


def save_cache(path: str | Path, state: UpdateState) -> Path:
    """**原子**寫入快取（先寫暫存檔再 `os.replace`）；非 `UpdateState` 一律拒絕。"""
    if not isinstance(state, UpdateState):
        raise ConfigError(
            f"save_cache 只接受 UpdateState，收到 {type(state).__name__}"
        )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(state.to_json(), encoding="utf-8")
    os.replace(temporary, target)
    return target


def parse_manifest(payload: Any) -> UpdateState:
    """驗證 manifest 並取出**顯示欄位**（`latest_version`／`released_at` 為必要）。

    只讀顯示欄位：`url`／`sha256`／`size` 就算存在也不會被使用——v0.3 只顯示不下載。
    """
    if not isinstance(payload, Mapping):
        raise ConfigError(f"manifest 必須是 JSON 物件，收到 {type(payload).__name__}")
    schema = payload.get("schema")
    if schema != 1:
        raise ConfigError(f"不支援的 manifest schema：{schema!r}（本版只認 1）")

    def required(name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"manifest 缺少可用的 {name}（收到 {value!r}）")
        return value.strip()

    values: dict[str, Any] = {
        "latest_version": required("version"),
        "released_at": required("released_at"),
    }
    for name in _OPTIONAL_FIELDS:
        value = payload.get(name)
        if value is not None and not isinstance(value, str):
            raise ConfigError(
                f"manifest 的 {name} 必須是字串或 null，收到 {type(value).__name__}"
            )
        values[name] = value.strip() if isinstance(value, str) and value.strip() else None
    return UpdateState(**values, source="network")


def _get_with_deadline(http: Any, url: str, timeout: float) -> tuple[int, Any]:
    """呼叫 `http.get(url, timeout)` 並保證**在 `timeout` 秒內**返回或失敗。

    實作方式是把請求放進 worker 執行緒再 `join(timeout)`：socket 的 `timeout=` 只管單一
    讀寫，慢速滴水的伺服器可以拖過它，因此硬上限必須由這裡給。卡住的 worker 是 daemon，
    不會阻止行程結束。
    """
    box: dict[str, Any] = {}

    def request() -> None:
        try:
            box["value"] = http.get(url, timeout)
        except BaseException as error:  # 不讓 worker 的例外消失在執行緒框架裡
            box["error"] = error

    worker = threading.Thread(target=request, name="ediaad-update-http", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise SourceError(f"更新服務逾時（超過 {timeout:g} 秒）：{url}")
    if "error" in box:
        error = box["error"]
        if isinstance(error, Exception):
            raise error
        raise SourceError(f"更新服務請求失敗：{error}")
    return box["value"]


def _fetch_json(http: Any, url: str, timeout: float) -> tuple[int, Any]:
    """取得並解析 JSON；HTTP 非 2xx 視為 `SourceError`、內容不是 JSON 視為 `ConfigError`。"""
    status, body = _get_with_deadline(http, url, timeout)
    text = (
        body.decode("utf-8", "replace")
        if isinstance(body, (bytes, bytearray))
        else str(body)
    )
    code = int(status)
    if not 200 <= code < 300:
        detail = text.strip()[:200] or "（沒有內容）"
        raise SourceError(f"更新服務回應 HTTP {code}：{detail}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ConfigError(f"更新服務回應不是合法 JSON：{error}") from error
    return code, payload


def _perform(
    *,
    http: Any,
    manifest_url: str,
    cache_path: str | Path,
    now: datetime,
    timeout: float,
) -> UpdateState:
    """真正做一次檢查並把結果寫進快取；**絕不拋例外**（失敗只記狀態）。"""
    previous = load_cache(cache_path)
    try:
        _status, payload = _fetch_json(http, manifest_url, timeout)
        fresh = parse_manifest(payload)
    except Exception as error:  # 靜默：任何失敗都只變成狀態
        state = UpdateState(
            **(previous.display_fields() if previous is not None else {}),
            checked_at=_stamp(now),
            source="cache" if previous is not None else "network",
            error=str(error),
        )
    else:
        state = replace(fresh, checked_at=_stamp(now), source="network", error=None)

    try:
        save_cache(cache_path, state)
    except OSError as error:  # 快取寫不進去也不影響服務
        logger.debug("更新快取無法寫入（%s）：%s", cache_path, error)
    return state


def _deliver(function: Callable[[], UpdateState], on_result: Callable[[UpdateState], None] | None) -> None:
    state = function()
    if on_result is None:
        return
    try:
        on_result(state)
    except Exception:  # 呼叫端的回呼不得讓背景執行緒爆掉
        logger.debug("更新檢查的回呼失敗", exc_info=True)


def _submit(executor: Any, function: Callable[[], UpdateState], on_result) -> None:
    task = lambda: _deliver(function, on_result)  # noqa: E731 - 只為了把回呼綁進去
    if executor is not None:
        executor.submit(task)
        return
    threading.Thread(target=task, name="ediaad-update-check", daemon=True).start()


def check_update(
    *,
    http: Any,
    manifest_url: str,
    cache_path: str | Path,
    now: datetime,
    enabled: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
    debounce_seconds: int = DEFAULT_DEBOUNCE_SECONDS,
    force: bool = False,
    background: bool = False,
    executor: Any = None,
    on_result: Callable[[UpdateState], None] | None = None,
) -> UpdateState:
    """檢查是否有新版本（AC-059）。**網路或內容失敗永不拋例外**，一律收斂成狀態。

    （呼叫端自己的參數錯誤——例如 `cache_path=None`——仍會拋例外：那是程式錯誤，
    安靜吞掉只會讓更新永遠不檢查卻沒有人知道。）

    - `enabled=False`：不發請求、不建立執行緒，回 `source="disabled"`（仍顯示上次已知值）。
    - 五分鐘內檢查過且 `force=False`：回 `source="cache"`，不發請求。
    - `background=True`：立刻回目前看得到的結果（快取或 `pending`），實際檢查交給
      `executor`（未提供時用 daemon 執行緒），完成後呼叫 `on_result`。
    - `background=False`：同步完成檢查並回傳這次的結果。
    """
    cache = Path(cache_path)
    previous = load_cache(cache)

    if not enabled:
        if previous is None:
            return UpdateState(source="disabled")
        return UpdateState(
            **previous.display_fields(),
            checked_at=previous.checked_at,
            source="disabled",
            error=previous.error,
        )

    if previous is not None and not force and not previous.is_stale(now, debounce_seconds):
        # 沿用上次的來源標記：`cache` 專門表示「顯示的是**過期**快取、背景正在補」，
        # 不該把「五分鐘內剛檢查過的新結果」也說成過期快取。
        return previous

    perform = lambda: _perform(  # noqa: E731 - 讓同步與背景走同一條路徑
        http=http, manifest_url=manifest_url, cache_path=cache, now=now, timeout=timeout
    )

    if not background:
        return perform()

    immediate = (
        replace(previous, source="cache")
        if previous is not None
        else UpdateState(source="pending")
    )
    _submit(executor, perform, on_result)
    return immediate


def fetch_catalog(
    *,
    http: Any,
    catalog_url: str,
    cache_path: str | Path,
    timeout: float = DEFAULT_TIMEOUT,
    remote_version: str | None = None,
) -> "UpdateResult":
    """更新 catalog：**完全交給 `markets.catalog.update_catalog`**，本函式只做介面轉接。

    TASK-017 已經有完整且被測試凍結的流程：`remote_version` 相同時**不發請求**（AC-038）、
    下載後以 catalog 的 schema 驗證、原子取代本地檔、失敗回傳狀態而不丟例外。再寫一份
    下載與寫檔就是報告 F-001 的溫床（同一份資料兩條路徑），因此這裡只把
    `http.get(url, timeout) -> (狀態碼, 內容)` 轉成它要的 `client(url) -> payload`。

    回傳 `UpdateResult`（`installed`／`updated`／`current`／`local-newer`／`failed`）；
    失敗是**狀態**不是例外，與 `check_update` 的靜默紀律一致。
    """
    # 延後 import：`markets.catalog` 會拉進 `urllib`（I/O 模組），而本模組的 import 不該碰 I/O。
    from .markets.catalog import update_catalog

    def client(url: str) -> Any:
        _status, payload = _fetch_json(http, url, timeout)
        return payload

    return update_catalog(
        cache_path, catalog_url, remote_version=remote_version, client=client
    )


def http_get(url: str, timeout: float = DEFAULT_TIMEOUT) -> tuple[int, str]:
    """標準庫 HTTP 客戶端（`urllib`）：回 `(狀態碼, 回應內容字串)`。

    這是 `check_update` 的**預設**客戶端；測試與服務都可注入自己的實作。`urllib` 在函式內
    才 import，因此 `import ediaad.update` 不會拉進網路模組（與 `license.http_post` 同一原則）。
    """
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:  # 4xx／5xx 也是「有回應」
        return int(error.code), error.read().decode("utf-8", "replace")
    except urllib.error.URLError as error:
        raise SourceError(f"無法連線更新服務 {url}：{error.reason}") from error
    except OSError as error:
        raise SourceError(f"無法連線更新服務 {url}：{error}") from error
