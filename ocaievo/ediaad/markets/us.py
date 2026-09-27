"""Twelve Data（美股）來源與金鑰存放隔離（AC-036）。

**金鑰隔離是這個模組的核心責任**（SPEC 第 5 節「資料生命週期、權限與狀態轉移」）：

- 金鑰只存在 `$EDIAAD_HOME/keys.json` 的 `twelvedata` 欄位，**絕不出現在**
  `watchlist.json`、網頁輸出或日誌中。
- 金鑰檔以 `0600` 建立（只有擁有者可讀寫）。若檔案已存在且含其他來源的金鑰，寫入時
  合併而不覆蓋；檔案損毀時**拒絕覆寫**（裡面可能有別人的金鑰）。
- 任何對外訊息（錯誤、日誌）都經過 `_redact`：客戶端例外常帶著完整 URL，而 URL 裡有
  `apikey=`，直接外洩等於把金鑰寫進日誌與網頁。
- 沒有金鑰時丟出 `SourceError`（exit 1 的來源失敗）而不是 `ConfigError`：依 SPEC 第 5 節
  「外部依賴與失敗處理」，無金鑰或額度用盡**不得影響其他商品**，因此它是單一商品的
  來源失敗，由監控迴圈的錯誤隔離接住（TASK-010 的 AC-024 已驗證該行為）。

不申請真實金鑰、不驗證真實額度（SPEC 第 8 節 Q-013 為 deferred）；不建立代理或內嵌金鑰
（報告第 7.3 節已否決）。HTTP 客戶端與 `EDIAAD_HOME` 皆可注入，測試全程離線。
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from ..data import from_rows
from ..errors import ConfigError, EdiaadError, SourceError
from ..paths import DEFAULT_HOME_PARTS, default_home, keys_path
from .base import INTERVAL_ORDER, Instrument, register

__all__ = [
    "APPLY_URL",
    "DEFAULT_HOME_PARTS",
    "INTERVAL_MAP",
    "KEYS_FILENAME",
    "KEY_FIELD",
    "TWELVE_DATA_URL",
    "TwelveDataSource",
    "default_home",
    "keys_path",
    "load_api_key",
    "save_api_key",
]

TWELVE_DATA_URL = "https://api.twelvedata.com"
TIME_SERIES_PATH = "/time_series"
SYMBOL_SEARCH_PATH = "/symbol_search"

#: 申請金鑰的說明網址（訊息中會出現，讓使用者知道去哪裡申請）。
APPLY_URL = "https://twelvedata.com/pricing"

KEYS_FILENAME = "keys.json"
KEY_FIELD = "twelvedata"

HTTP_TIMEOUT = 10.0
DEFAULT_LIMIT = 100
MAX_LIMIT = 5000

#: 本專案的週期 → Twelve Data 的 `interval` 參數值。
INTERVAL_MAP: dict[str, str] = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1day",
    "1w": "1week",
}

HttpClient = Callable[[str], Any]

_KEY_IN_URL = re.compile(r"(apikey=)[^&\s\"']+")


# `default_home`／`keys_path` 由 `ediaad.paths` 提供（單一解析點，見該模組說明）。


def _redact(text: str, secret: str | None) -> str:
    """遮蔽金鑰：先換掉已知的金鑰字串，再換掉任何 `apikey=...` 片段。"""
    if secret:
        text = text.replace(secret, "***")
    return _KEY_IN_URL.sub(r"\1***", text)


def _missing_key_error(path: Path) -> SourceError:
    return SourceError(
        f"缺少 {KEY_FIELD} 金鑰：請至 {APPLY_URL} 申請後，"
        f'填入 {path} 的 "{KEY_FIELD}" 欄位'
    )


def load_api_key(home: str | Path | None = None) -> str:
    """讀取 Twelve Data 金鑰；任何問題都丟出可讀的 `SourceError`（不猜測、不放行）。"""
    path = keys_path(home)
    if not path.is_file():
        raise _missing_key_error(path)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SourceError(f"讀不到金鑰檔 {path}：{error}") from error

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise SourceError(f"金鑰檔 {path} 不是合法 JSON：{error}") from error

    if not isinstance(payload, Mapping):
        raise SourceError(
            f"金鑰檔 {path} 必須是 JSON 物件，收到 {type(payload).__name__}"
        )

    value = payload.get(KEY_FIELD)
    if not isinstance(value, str) or not value.strip():
        raise _missing_key_error(path)
    return value.strip()


def save_api_key(home: str | Path | None, key: str) -> Path:
    """以 `0600` 原子寫入金鑰，保留同檔其他來源的鍵；檔案損毀時拒絕覆寫。"""
    if not isinstance(key, str) or not key.strip():
        raise ConfigError(f"金鑰必須是非空字串，收到 {key!r}")

    path = keys_path(home)
    stored: dict[str, Any] = {}

    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ConfigError(
                f"金鑰檔 {path} 不是合法 JSON，為避免覆蓋其他來源的金鑰而中止：{error}"
            ) from error
        except OSError as error:
            raise ConfigError(f"讀不到金鑰檔 {path}：{error}") from error
        if not isinstance(payload, Mapping):
            raise ConfigError(
                f"金鑰檔 {path} 必須是 JSON 物件，收到 {type(payload).__name__}"
            )
        stored = dict(payload)

    stored[KEY_FIELD] = key.strip()

    temporary = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(stored, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise ConfigError(f"無法寫入金鑰檔 {path}：{error}") from error

    return path


def _default_client(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _require_symbol(symbol: str) -> str:
    if not isinstance(symbol, str) or not symbol.strip():
        raise ConfigError(f"symbol 必須是非空字串，收到 {symbol!r}")
    return symbol.strip().upper()


def _require_interval(interval: str) -> str:
    if interval not in INTERVAL_MAP:
        raise ConfigError(
            f"來源 '{KEY_FIELD}' 不支援 interval {interval!r}；"
            f"可用週期：{[item for item in INTERVAL_ORDER if item in INTERVAL_MAP]}"
        )
    return INTERVAL_MAP[interval]


def _require_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ConfigError(f"limit 必須是 1 到 {MAX_LIMIT} 的整數，收到 {limit!r}")
    return limit


def _get_json(getter: HttpClient, url: str, key: str, label: str) -> Any:
    """呼叫客戶端並把任何例外化為遮蔽過的 `SourceError`。

    若原始訊息含金鑰，**不**以 `__cause__` 鏈結原例外——否則 traceback 會把金鑰印出來。
    """
    try:
        return getter(url)
    except Exception as error:
        original = str(error)
        redacted = _redact(original, key)
        if redacted != original:
            raise SourceError(f"Twelve Data {label}請求失敗：{redacted}")
        raise SourceError(f"Twelve Data {label}請求失敗：{original}") from error


def _to_float(value: Any, *, where: str, key: str) -> float:
    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError as error:
        raise SourceError(
            _redact(f"Twelve Data {where} 無法轉換成數值：{value!r}", key)
        ) from error


def _parse_time_series(payload: Any, key: str, limit: int) -> pd.DataFrame:
    """把 `time_series` 回應轉成序列。

    真實回應的 `values` 是**由新到舊**；`data.from_rows` 會依時間升冪排序，因此這裡
    不需要自己反轉。任何問題都化為遮蔽過的 `SourceError`。
    """
    if not isinstance(payload, Mapping):
        raise SourceError(
            f"Twelve Data 回應必須是 JSON 物件，收到 {type(payload).__name__}"
        )

    if payload.get("status") != "ok":
        detail = payload.get("message") or payload.get("status") or "未知錯誤"
        raise SourceError(
            _redact(f"Twelve Data 回應錯誤：{detail}（code={payload.get('code')}）", key)
        )

    values = payload.get("values")
    if not isinstance(values, list) or not values:
        raise SourceError("Twelve Data 回應沒有資料列（values 為空或不存在）")

    records: list[dict[str, Any]] = []
    required = ("datetime", "open", "high", "low", "close")
    for index, row in enumerate(values):
        if not isinstance(row, Mapping):
            raise SourceError(f"Twelve Data 第 {index} 列必須是物件，收到 {type(row).__name__}")
        missing = [name for name in required if name not in row]
        if missing:
            raise SourceError(f"Twelve Data 第 {index} 列缺少欄位：{'、'.join(missing)}")

        record: dict[str, Any] = {"time": row["datetime"]}
        for name in ("open", "high", "low", "close"):
            record[name] = _to_float(row[name], where=f"第 {index} 列的 {name}", key=key)
        volume = row.get("volume")
        record["volume"] = (
            0.0
            if volume is None or str(volume).strip() == ""
            else _to_float(volume, where=f"第 {index} 列的 volume", key=key)
        )
        records.append(record)

    try:
        series = from_rows(records)
    except EdiaadError as error:
        raise SourceError(f"Twelve Data 資料列無法解讀：{error}") from error

    if len(series) > limit:
        # 伺服器的 outputsize 應該已截斷；若回應更長，取最近 N 根（與其他來源一致）。
        series = series.iloc[-limit:].reset_index(drop=True)
    return series


def _parse_symbol_search(payload: Any, key: str, limit: int) -> list[Instrument]:
    if not isinstance(payload, Mapping):
        raise SourceError(
            f"Twelve Data 回應必須是 JSON 物件，收到 {type(payload).__name__}"
        )
    if payload.get("status") != "ok":
        detail = payload.get("message") or payload.get("status") or "未知錯誤"
        raise SourceError(
            _redact(f"Twelve Data 回應錯誤：{detail}（code={payload.get('code')}）", key)
        )

    entries = payload.get("data")
    if not isinstance(entries, list):
        raise SourceError("Twelve Data 商品搜尋回應缺少 data 陣列")

    results: list[Instrument] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise SourceError(
                f"Twelve Data 商品搜尋的項目必須是物件，收到 {type(entry).__name__}"
            )
        symbol = str(entry.get("symbol", "")).strip()
        if not symbol:
            continue
        name = str(entry.get("instrument_name", "")).strip() or symbol
        results.append(
            Instrument(
                symbol=symbol, interval="", source_id="twelvedata", display_name=name
            )
        )
        if len(results) >= limit:
            break
    return results


class TwelveDataSource:
    """`Source` 協定的 Twelve Data 實作（美股；`needs_api_key=True`）。"""

    id = "twelvedata"
    display_name = "Twelve Data（美股）"
    supported_intervals = tuple(item for item in INTERVAL_ORDER if item in INTERVAL_MAP)
    needs_api_key = True

    def fetch(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int = DEFAULT_LIMIT,
        home: str | Path | None = None,
        client: HttpClient | None = None,
    ) -> pd.DataFrame:
        """取得序列；沒有金鑰時丟出含申請說明的 `SourceError`。"""
        code = _require_symbol(symbol)
        remote_interval = _require_interval(interval)
        wanted = _require_limit(limit)
        key = load_api_key(home)
        getter = client if client is not None else _default_client

        url = (
            f"{TWELVE_DATA_URL}{TIME_SERIES_PATH}"
            f"?symbol={code}&interval={remote_interval}&outputsize={wanted}&apikey={key}"
        )
        payload = _get_json(getter, url, key, "行情")
        return _parse_time_series(payload, key, wanted)

    def search(
        self,
        query: str,
        limit: int = 20,
        *,
        home: str | Path | None = None,
        client: HttpClient | None = None,
    ) -> list[Instrument]:
        """以 Twelve Data 的 `symbol_search` 查詢商品（需要金鑰）。

        空查詢或 `limit < 1` 時直接回空清單：這是無效查詢，不該先抱怨金鑰。
        """
        text = query.strip()
        if not text or limit < 1:
            return []

        key = load_api_key(home)
        getter = client if client is not None else _default_client
        url = f"{TWELVE_DATA_URL}{SYMBOL_SEARCH_PATH}?symbol={text}&apikey={key}"
        payload = _get_json(getter, url, key, "商品搜尋")
        return _parse_symbol_search(payload, key, limit)


register(TwelveDataSource())
