"""HTTP 路由註冊表與分派（TASK-020）。

**網頁層只做三件事**：參數解析、呼叫既有核心函式、把結果序列化（報告第 6.3 節：
「網頁層只做參數解析、錯誤轉譯與呈現，不重實作任何邏輯」）。因此這裡的每個 handler
都必須是既有函式的薄轉接——不含任何運算。

錯誤格式依 SPEC 第 5 節：`{"error": {"code": ..., "message": ...}}`，訊息可讀且**不含**
堆疊內容。
"""

from __future__ import annotations

import dataclasses
import logging
import os
import queue
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import load_settings
from ..license import (
    HTTP_CLIENT,
    LICENSE_PUBLIC_KEY,
    activate,
    lease_status,
    load_lease,
    machine_fingerprint,
)
from ..data import load_csv
from ..errors import ConfigError, DataFormatError, EdiaadError, SourceError
from ..markets.base import DEFAULT_SOURCE_ID, get_source
from ..markets.calendar import MARKET_PATTERN_DEFAULTS, default_spec_for
from ..markets.custom import CsvSource
from ..markets.base import all_sources
from ..match import (
    DEFAULT_HORIZON,
    DEFAULT_OVERLAP,
    DEFAULT_STEP,
    DEFAULT_TOP,
    run_match,
)
from ..monitor import save_config, validate_config
from ..patterns import NAMED_PATTERNS, PatternSpec, detect, from_json, learn, to_json
from .sse_hub import KEEP_ALIVE_FRAME, SSEHub

__all__ = [
    "error_response",
    "events",
    "instruments",
    "license_status",
    "status",
    "match",
    "pattern_events",
    "pattern_learn",
    "pattern_preview",
    "series",
    "route",
    "routes",
    "dispatch",
    "stream_for",
    "stream_route",
]

logger = logging.getLogger("ediaad.web")

Handler = Callable[[Any, Mapping[str, Sequence[str]], Any], tuple[int, dict[str, Any]]]
StreamHandler = Callable[
    [Any, Mapping[str, Sequence[str]], Mapping[str, str]], Iterator[bytes]
]

_REGISTRY: dict[tuple[str, str], Handler] = {}

#: 需要逐幀輸出的路由（SSE 不能包成單一 JSON 主體，因此與一般路由分開註冊）。
_STREAMS: dict[str, StreamHandler] = {}

#: 沒有事件時多久送一次 keep-alive（必須明顯小於客戶端與代理的閒置逾時）。
KEEP_ALIVE_SECONDS = 1.0


def route(method: str, path: str, handler: Handler) -> None:
    """註冊一個 handler；同一（方法, 路徑）重複註冊視為程式錯誤。"""
    key = (method.upper(), path)
    if key in _REGISTRY:
        raise ConfigError(f"路由重複註冊：{key[0]} {key[1]}")
    _REGISTRY[key] = handler


def routes() -> tuple[tuple[str, str], ...]:
    """已註冊的（方法, 路徑），依方法與路徑排序（供測試與系統狀態頁）。"""
    return tuple(sorted(_REGISTRY))


class _HttpError(Exception):
    """帶狀態碼的內部訊號（找不到路徑、方法不允許）。"""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_response(error: BaseException) -> tuple[int, dict[str, Any]]:
    """把例外轉成 `(狀態碼, 錯誤主體)`。

    - `ConfigError`／`DataFormatError` → 400（輸入或設定錯誤）
    - `SourceError` → 502（上游來源失敗；本機服務本身沒有問題）
    - 其他 `EdiaadError` → 400
    - 其他例外 → 500，訊息固定且**不含**例外內容或堆疊
    """
    if isinstance(error, _HttpError):
        return error.status, {"error": {"code": error.code, "message": error.message}}
    if isinstance(error, (ConfigError, DataFormatError)):
        return 400, {"error": {"code": "invalid_request", "message": str(error)}}
    if isinstance(error, SourceError):
        return 502, {"error": {"code": "source_failed", "message": str(error)}}
    if isinstance(error, EdiaadError):
        return 400, {"error": {"code": "invalid_request", "message": str(error)}}
    return 500, {
        "error": {
            "code": "internal_error",
            "message": "內部錯誤（詳見伺服器日誌）",
        }
    }


def dispatch(
    app: Any,
    method: str,
    path: str,
    query: Mapping[str, Sequence[str]] | None = None,
    body: Any = None,
) -> tuple[int, dict[str, Any]]:
    """分派一個請求；永遠回傳 `(狀態碼, JSON 主體)`，不讓例外外洩到 HTTP 層。"""
    verb = method.upper()
    try:
        handler = _REGISTRY.get((verb, path))
        if handler is None:
            if any(registered == path for _method, registered in _REGISTRY):
                raise _HttpError(405, "method_not_allowed", f"{path} 不接受 {verb}")
            raise _HttpError(404, "not_found", f"找不到路徑 {path}")
        return handler(app, query or {}, body)
    except Exception as error:  # 錯誤轉譯一律集中在這裡
        status, payload = error_response(error)
        if status >= 500:
            logger.exception("處理 %s %s 時發生未預期例外", verb, path)
        return status, payload


def health(_app: Any, _query: Mapping[str, Sequence[str]], _body: Any):
    """服務健康狀態（唯讀，不含任何運算）。"""
    return 200, {
        "status": "ok",
        "version": _app.version,
        "running": _app.running,
        "sources": [source.id for source in _app.sources],
        "problems": dict(_app.problems),
    }


def patterns(_app: Any, _query: Mapping[str, Sequence[str]], _body: Any):
    """可用的規律與市場別預設（直接序列化既有常數）。"""
    return 200, {
        "patterns": {name: dict(params) for name, params in NAMED_PATTERNS.items()},
        "markets": {market: dict(params) for market, params in MARKET_PATTERN_DEFAULTS.items()},
    }


def settings(app: Any, _query: Mapping[str, Sequence[str]], _body: Any):
    """目前設定；**每次請求都重新讀檔**，讓損毀的檔案能被回報而不是被快取掩蓋。"""
    return 200, load_settings(app.settings_path)


route("GET", "/api/health", health)
route("GET", "/api/patterns", patterns)
route("GET", "/api/settings", settings)


def stream_route(path: str, handler: StreamHandler) -> None:
    """註冊一個逐幀輸出的路由。"""
    if path in _STREAMS:
        raise ConfigError(f"串流路由重複註冊：{path}")
    _STREAMS[path] = handler


def stream_for(path: str) -> StreamHandler | None:
    return _STREAMS.get(path)


def stream_events(app: Any, _query: Mapping[str, Sequence[str]], _headers: Mapping[str, str]):
    """`GET /api/events/stream`：訂閱推播中樞並逐幀輸出（含 keep-alive）。

    `Last-Event-ID` 不需要額外處理：`SSEHub` 不會廣播重複的 id，因此重連的客戶端
    不可能收到已顯示過的事件；重連期間漏掉的事件由 `GET /api/events` 補齊。
    """
    hub: SSEHub = app.hub
    subscriber = hub.subscribe()
    try:
        while True:
            try:
                frame = subscriber.get(timeout=KEEP_ALIVE_SECONDS)
            except queue.Empty:
                yield KEEP_ALIVE_FRAME
                continue
            yield frame
    finally:
        hub.unsubscribe(subscriber)


register_stream = stream_route
register_stream("/api/events/stream", stream_events)


def _first(query: Mapping[str, Sequence[str]], name: str) -> str | None:
    values = query.get(name)
    if not values:
        return None
    text = str(values[0]).strip()
    return text or None


def events(app: Any, query: Mapping[str, Sequence[str]], _body: Any):
    """`GET /api/events?symbol=&start=&end=`：事件歷史（**只讀**儲存層）。

    篩選與時間比較都交給 `store.query_events`（web 層不重算、不重實作去重）；
    無符合條件時回 200 與空清單。
    """
    store = app.store
    if store is None:
        raise _HttpError(503, "store_unavailable", "資料庫無法使用，事件歷史暫時不可用")

    rows = store.query_events(
        symbol=_first(query, "symbol"),
        start=_first(query, "start"),
        end=_first(query, "end"),
    )
    return 200, {"events": rows, "count": len(rows)}


route("GET", "/api/events", events)


#: 序列端點一次最多回幾根（圖表只需要一個視窗；也讓 JSON 有界）。
DEFAULT_SERIES_LIMIT = 500
MAX_SERIES_LIMIT = 10_000


def _require_query(query: Mapping[str, Sequence[str]], name: str) -> str:
    value = _first(query, name)
    if value is None:
        raise ConfigError(f"查詢參數 {name} 為必填")
    return value


def _limit_value(raw: object) -> int:
    """把查詢字串或 JSON 數值轉成上限受控的 `limit`（`GET` 與 `POST` 共用）。"""
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise ConfigError(f"limit 必須是整數，收到 {raw!r}")
    try:
        limit = int(str(raw).strip())
    except ValueError as error:
        raise ConfigError(f"limit 必須是整數，收到 {raw!r}") from error
    # 下限由各來源自己的驗證負責（四個來源都要求 >= 1）；這裡只管路由層的政策上限，
    # 避免任何來源都能讓這個端點產生無界的 JSON。
    if limit > MAX_SERIES_LIMIT:
        raise ConfigError(f"limit 不得超過 {MAX_SERIES_LIMIT}，收到 {limit}")
    return limit


def _limit_from(query: Mapping[str, Sequence[str]]) -> int:
    raw = _first(query, "limit")
    if raw is None:
        return DEFAULT_SERIES_LIMIT
    return _limit_value(raw)


def _source_id_for(app: Any, query: Mapping[str, Sequence[str]], symbol: str) -> str:
    """決定用哪個來源：明確指定 → catalog 的商品對照 → 預設來源。

    這是「哪個商品該問哪個來源」的接線起點：catalog（TASK-017）就是為此存在的權威對照。
    """
    explicit = _first(query, "source")
    if explicit:
        return explicit

    catalog = getattr(app, "catalog", None)
    if catalog is not None:
        for instrument in catalog.instruments:
            if instrument.symbol.upper() == symbol.upper() and instrument.source_id:
                return instrument.source_id
    return DEFAULT_SOURCE_ID


def _fetch_series(app: Any, source_id: str, symbol: str, interval: str, limit: int):
    """取得序列；自訂 CSV 需要快取目錄，因此它由呼叫端以 `CsvSource(root)` 建構。"""
    if source_id == DEFAULT_SOURCE_ID:
        return CsvSource(app.cache_dir).fetch(symbol, interval, limit=limit)
    return get_source(source_id).fetch(symbol, interval, limit=limit)


def _spec_for(app: Any):
    """目前設定推導出的規格：明確覆寫優先，否則用市場別預設（TASK-015）＋pattern_id。"""
    settings = app.settings
    if settings.get("pattern_spec") is not None:
        return from_json(settings["pattern_spec"])
    return default_spec_for(settings["market"], {"pattern_id": settings["pattern_id"]})


def series(app: Any, query: Mapping[str, Sequence[str]], _body: Any):
    """`GET /api/series?symbol=&interval=&limit=&source=`：序列的六個平行陣列。"""
    symbol = _require_query(query, "symbol")
    interval = _require_query(query, "interval")
    limit = _limit_from(query)
    source_id = _source_id_for(app, query, symbol)

    frame = _fetch_series(app, source_id, symbol, interval, limit)
    return 200, {
        "symbol": symbol,
        "interval": interval,
        "source": source_id,
        "data_source": str(frame.attrs.get("data_source", source_id)),
        "count": len(frame),
        "time": [stamp.isoformat() for stamp in frame["time"]],
        "open": [float(value) for value in frame["open"]],
        "high": [float(value) for value in frame["high"]],
        "low": [float(value) for value in frame["low"]],
        "close": [float(value) for value in frame["close"]],
        "volume": [float(value) for value in frame["volume"]],
    }


def pattern_events(app: Any, query: Mapping[str, Sequence[str]], _body: Any):
    """`GET /api/patterns/events?...`：只呼叫 `patterns.detect`，不新增判定邏輯。

    「資料不足（無法評估）」與「評估後沒有命中」以 `status` 明確區分（F-003）。
    """
    symbol = _require_query(query, "symbol")
    interval = _require_query(query, "interval")
    limit = _limit_from(query)
    source_id = _source_id_for(app, query, symbol)

    frame = _fetch_series(app, source_id, symbol, interval, limit)
    spec = _spec_for(app)
    minimum = spec.range_bars_min + 1

    base = {
        "symbol": symbol,
        "interval": interval,
        "source": source_id,
        "pattern_id": spec.pattern_id,
        # 回報實際使用的規格：讓前端與系統狀態能看到門檻，也讓「設定 → 規格」的推導可被斷言。
        "spec": dataclasses.asdict(spec),
        "bars": len(frame),
        "events": [],
        "dropped": 0,
    }
    if len(frame) < minimum:
        return 200, {
            **base,
            "status": "insufficient",
            "message": f"資料不足，無法評估：需要至少 {minimum} 根，實際 {len(frame)} 根",
        }

    kept: list[dict[str, Any]] = []
    dropped = 0
    for event in detect(frame, spec):
        indices = (
            event.range_start_index,
            event.range_end_index,
            event.breakdown_index,
            event.recovery_index,
        )
        if max(indices) >= len(frame) or min(indices) < 0:
            # 前端只呈現，過濾在後端：索引超出序列範圍的事件不得被畫出。
            dropped += 1
            logger.warning(
                "事件索引超出序列範圍（%s 根）：%s", len(frame), indices
            )
            continue
        kept.append(dataclasses.asdict(event))

    return 200, {
        **base,
        "status": "evaluated",
        "message": "" if kept else "評估後沒有命中（序列中沒有符合條件的結構）",
        "events": kept,
        "dropped": dropped,
    }


route("GET", "/api/series", series)
route("GET", "/api/patterns/events", pattern_events)


# ---- AC-044：規律參數即時預覽（TASK-023） -----------------------------------

#: 白話參數的鍵就是 `PatternSpec` 的欄位名（中文標籤 ↔ 欄位的對應在 `params.js`）。
SPEC_FIELD_NAMES: tuple[str, ...] = tuple(
    field.name for field in dataclasses.fields(PatternSpec)
)

#: 請求主體允許的鍵：序列查詢用的鍵 ＋ 規格欄位（可放在頂層或 `params` 內）。
_BODY_KEYS: frozenset[str] = frozenset(
    {"symbol", "interval", "source", "limit", "params", *SPEC_FIELD_NAMES}
)


def _body_object(body: Any) -> Mapping[str, Any]:
    """主體必須是 JSON 物件；其他型別（清單、字串、無主體）一律可讀地拒絕。"""
    if body is None:
        raise ConfigError("請求主體為必填：請以 JSON 物件帶上 symbol、interval 與參數")
    if not isinstance(body, Mapping):
        raise ConfigError(f"請求主體必須是 JSON 物件，收到 {type(body).__name__}")
    return body


def _body_text(body: Mapping[str, Any], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"欄位 {name} 必須是非空字串，收到 {value!r}")
    return value.strip()


def _limit_from_body(body: Mapping[str, Any]) -> int:
    raw = body.get("limit")
    if raw is None:
        return DEFAULT_SERIES_LIMIT
    return _limit_value(raw)


def _source_id_from_body(app: Any, body: Mapping[str, Any], symbol: str) -> str:
    raw = body.get("source")
    if raw is None:
        return _source_id_for(app, {}, symbol)
    return _body_text(body, "source")


def _spec_for_body(app: Any, body: Mapping[str, Any]) -> PatternSpec:
    """由請求主體推導規格：設定的市場別預設 ＋ 請求中的覆寫。

    覆寫可放在**頂層**或 `params` 物件內（後者優先），因此「只改一個參數」也是合法請求；
    未提供的欄位一律沿用設定推導出的預設，不另立一套預設值（避免兩份真相）。
    未知的鍵一律丟出 `ConfigError`——打錯字的參數若被默默忽略，使用者看到的次數會與
    他以為的參數不符。
    """
    unknown = sorted(set(body) - _BODY_KEYS)
    if unknown:
        raise ConfigError(
            f"未知的欄位：{'、'.join(unknown)}；"
            f"可用欄位：{sorted(_BODY_KEYS)}"
        )

    overrides: dict[str, Any] = {
        name: body[name] for name in SPEC_FIELD_NAMES if name in body
    }
    nested = body.get("params")
    if nested is not None:
        if not isinstance(nested, Mapping):
            raise ConfigError(f"params 必須是 JSON 物件，收到 {type(nested).__name__}")
        unknown_nested = sorted(set(nested) - set(SPEC_FIELD_NAMES))
        if unknown_nested:
            raise ConfigError(
                f"未知的參數：{'、'.join(unknown_nested)}；"
                f"可用參數：{list(SPEC_FIELD_NAMES)}"
            )
        overrides.update(nested)

    base = _spec_for(app)
    try:
        return PatternSpec(**{**dataclasses.asdict(base), **overrides})
    except ConfigError as error:
        raise ConfigError(f"規律參數不合法：{error}") from error


def pattern_preview(app: Any, _query: Mapping[str, Sequence[str]], body: Any):
    """`POST /api/pattern/preview`：改參數後即時回報命中次數（AC-044）。

    只回**次數**與實際採用的參數，不回傳事件清單（面板不需要、也讓回應保持有界）；
    判定本身完全交給 `patterns.detect`，因此「同一參數在預覽與正式掃描得到相同次數」
    是構造上的保證，而不是兩套邏輯恰好一致。

    `status` 沿用 F-003 的區分：`insufficient`（資料不足，無法評估）與 `evaluated`
    （評估後沒有命中）不得混為一談——兩者 `hits` 都是 0，但意義相反。
    """
    payload = _body_object(body)
    symbol = _body_text(payload, "symbol")
    interval = _body_text(payload, "interval")
    spec = _spec_for_body(app, payload)
    limit = _limit_from_body(payload)
    source_id = _source_id_from_body(app, payload, symbol)

    frame = _fetch_series(app, source_id, symbol, interval, limit)
    minimum = spec.range_bars_min + 1
    base = {
        "symbol": symbol,
        "interval": interval,
        "source": source_id,
        "params": dataclasses.asdict(spec),
        "bars": len(frame),
    }
    if len(frame) < minimum:
        return 200, {
            **base,
            "status": "insufficient",
            "hits": 0,
            "message": f"資料不足，無法評估：需要至少 {minimum} 根，實際 {len(frame)} 根",
        }

    hits = len(detect(frame, spec))
    return 200, {
        **base,
        "status": "evaluated",
        "hits": hits,
        "message": "" if hits else "評估後沒有命中（序列中沒有符合條件的結構）",
    }


route("POST", "/api/pattern/preview", pattern_preview)


# ---- AC-045：範例學習（TASK-023） -------------------------------------------

#: 範例學習只需要範例內容；商品與週期是選配的（有才做命中預覽）。
LEARN_BODY_KEYS: frozenset[str] = frozenset(
    {"csv", "symbol", "interval", "source", "limit"}
)

#: 與「目前商品」有關的欄位：只要出現任一項，就必須同時提供 `symbol` 與 `interval`，
#: 否則該欄位會被默默忽略（例如 `limit` 有值卻沒有商品）——不明確的表達一律擋下。
INSTRUMENT_KEYS: tuple[str, ...] = ("symbol", "interval", "source", "limit")


def _load_sample(csv_text: str):
    """把請求中的 CSV **文字**寫成暫存檔後交給 `data.load_csv`（不另寫解析器）。

    解析、欄位正規化與 `DataFormatError` 的訊息完全沿用既有載入路徑；唯一改寫的是把
    暫存檔路徑換成「範例 CSV」——伺服器的隨機檔名對使用者沒有意義，而訊息中的欄位名與
    列號仍然保留（錯誤轉譯是網頁層的職責）。
    """
    with tempfile.NamedTemporaryFile(
        "w", suffix=".csv", encoding="utf-8", delete=False, newline=""
    ) as handle:
        handle.write(csv_text)
        path = Path(handle.name)
    try:
        return load_csv(path)
    except DataFormatError as error:
        raise DataFormatError(str(error).replace(f"CSV {path}", "範例 CSV")) from error
    finally:
        path.unlink(missing_ok=True)


def pattern_learn(app: Any, _query: Mapping[str, Sequence[str]], body: Any):
    """`POST /api/pattern/learn`：由一段範例 CSV 推估規格並預覽命中（AC-045）。

    推估完全交給 `patterns.learn`（TASK-009）：無法推估時 `ConfigError` 的原文就是回應的
    原因訊息，**不會**回退成隨意參數——「猜一組參數給你」比「說我推不出來」更糟。

    推估出的規格一律以 `spec`（物件）與 `spec_json`（`to_json` 的穩定鍵序）回傳；有指定
    商品與週期時附上以該規格對目前序列的命中預覽（`status`／`hits` 的語意與 AC-044 相同）。
    """
    payload = _body_object(body)
    unknown = sorted(set(payload) - LEARN_BODY_KEYS)
    if unknown:
        raise ConfigError(
            f"未知的欄位：{'、'.join(unknown)}；可用欄位：{sorted(LEARN_BODY_KEYS)}"
        )

    csv_text = payload.get("csv")
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise ConfigError(f"欄位 csv 必須是非空字串（範例 CSV 內容），收到 {csv_text!r}")

    sample = _load_sample(csv_text)
    spec = learn(sample)

    result: dict[str, Any] = {
        "spec": dataclasses.asdict(spec),
        "spec_json": to_json(spec),
        "sample_bars": len(sample),
        "symbol": None,
        "interval": None,
        "source": None,
        "bars": None,
        "status": "no_preview",
        "hits": None,
        "message": "未指定商品與週期，只回傳推估參數（沒有命中預覽）",
    }

    if all(payload.get(name) is None for name in INSTRUMENT_KEYS):
        # 只給範例：回推估參數，沒有預覽（上面已驗證沒有多餘的商品欄位被默默忽略）。
        return 200, result

    symbol = _body_text(payload, "symbol")
    interval = _body_text(payload, "interval")
    limit = _limit_from_body(payload)
    source_id = _source_id_from_body(app, payload, symbol)
    frame = _fetch_series(app, source_id, symbol, interval, limit)
    minimum = spec.range_bars_min + 1

    preview: dict[str, Any] = {
        "symbol": symbol,
        "interval": interval,
        "source": source_id,
        "bars": len(frame),
    }
    if len(frame) < minimum:
        preview.update(
            {
                "status": "insufficient",
                "hits": 0,
                "message": (
                    f"資料不足，無法評估：需要至少 {minimum} 根，實際 {len(frame)} 根"
                ),
            }
        )
    else:
        hits = len(detect(frame, spec))
        preview.update(
            {
                "status": "evaluated",
                "hits": hits,
                "message": "" if hits else "評估後沒有命中（序列中沒有符合條件的結構）",
            }
        )
    return 200, {**result, **preview}


route("POST", "/api/pattern/learn", pattern_learn)


# ---- AC-046：歷史回看（表單化 match，TASK-024） ------------------------------

#: 表單欄位：商品與週期（必要）＋ 掃描參數 ＋ 時間範圍（選配）。
MATCH_BODY_KEYS: frozenset[str] = frozenset(
    {
        "symbol",
        "interval",
        "source",
        "limit",
        "start",
        "end",
        "window",
        "top",
        "horizon",
        "step",
        "overlap",
    }
)


def _body_int(
    body: Mapping[str, Any],
    name: str,
    *,
    default: int | None = None,
    minimum: int | None = None,
) -> int:
    """主體中的整數欄位；缺值時用 `default`，仍缺就說「為必填」。

    表單（`<input>`）送出的是字串，因此數字字串是合法輸入；小數、布林與其他型別一律
    擋下並指出欄位名——`PatternSpec` 與掃描層都只收整數。

    `minimum` 用於**核心看不到的參數**：`window` 在網頁層會被換成「最後 N 根」，若不在
    這裡擋，`window=0` 會安靜地變成「整份序列」（`iloc[-0:]` 等於全部）——使用者的
    參數被默默改寫。`top`／`step`／`overlap` 的下限仍由 `scan_similar` 負責。
    """
    raw = body.get(name)
    if raw is None:
        if default is None:
            raise ConfigError(f"欄位 {name} 為必填")
        return default
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise ConfigError(f"欄位 {name} 必須是整數，收到 {raw!r}")
    try:
        value = int(str(raw).strip())
    except ValueError as error:
        raise ConfigError(f"欄位 {name} 必須是整數，收到 {raw!r}") from error
    if minimum is not None and value < minimum:
        raise ConfigError(f"欄位 {name} 必須 >= {minimum}，收到 {value}")
    return value


def _body_number(body: Mapping[str, Any], name: str, *, default: float) -> float:
    raw = body.get(name)
    if raw is None:
        return default
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise ConfigError(f"欄位 {name} 必須是數值，收到 {raw!r}")
    try:
        return float(str(raw).strip())
    except ValueError as error:
        raise ConfigError(f"欄位 {name} 必須是數值，收到 {raw!r}") from error


def _body_time(body: Mapping[str, Any], name: str) -> pd.Timestamp | None:
    """時間範圍端點；沒有時區時一律視為 UTC（序列契約是 UTC）。"""
    raw = body.get(name)
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ConfigError(f"欄位 {name} 必須是 ISO 時間字串，收到 {raw!r}")
    try:
        stamp = pd.Timestamp(raw.strip())
    except (TypeError, ValueError) as error:
        raise ConfigError(f"欄位 {name} 無法解析為時間：{raw!r}") from error
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp


def _filter_by_time(
    frame: Any, start: pd.Timestamp | None, end: pd.Timestamp | None
):
    """依時間範圍篩選（含頭尾）；篩選後重設索引，讓回報的索引對應篩選後的序列。"""
    if start is not None:
        frame = frame[frame["time"] >= start]
    if end is not None:
        frame = frame[frame["time"] <= end]
    return frame.reset_index(drop=True)


def match(app: Any, _query: Mapping[str, Sequence[str]], body: Any):
    """`POST /api/match`：以表單參數跑一次歷史回看（AC-046）。

    流程與 CLI `match` 完全相同——兩者都呼叫 `match.run_match`，因此回傳的就是那份
    五鍵報表（`sample`／`params`／`data_source`／`matches`／`outlook`），不是「另一份
    長得很像的 JSON」。範例＝**時間範圍內最後 `window` 根**（表單只需要商品、週期、
    時間範圍與 `window`，不必另外指定範例檔）。
    """
    payload = _body_object(body)
    unknown = sorted(set(payload) - MATCH_BODY_KEYS)
    if unknown:
        raise ConfigError(
            f"未知的欄位：{'、'.join(unknown)}；可用欄位：{sorted(MATCH_BODY_KEYS)}"
        )

    symbol = _body_text(payload, "symbol")
    interval = _body_text(payload, "interval")
    window = _body_int(payload, "window", minimum=1)
    top = _body_int(payload, "top", default=DEFAULT_TOP)
    horizon = _body_int(payload, "horizon", default=DEFAULT_HORIZON)
    step = _body_int(payload, "step", default=DEFAULT_STEP)
    overlap = _body_number(payload, "overlap", default=DEFAULT_OVERLAP)
    start = _body_time(payload, "start")
    end = _body_time(payload, "end")
    if start is not None and end is not None and start > end:
        raise ConfigError(
            f"start（{start.isoformat()}）不得晚於 end（{end.isoformat()}）"
        )

    limit = _limit_from_body(payload)
    source_id = _source_id_from_body(app, payload, symbol)
    frame = _fetch_series(app, source_id, symbol, interval, limit)
    # attrs 不保證經過篩選後仍在，因此在篩選前先取出資料來源標示。
    data_source = str(frame.attrs.get("data_source", source_id))
    frame = _filter_by_time(frame, start, end)

    # 這裡先擋「切不出 window 根」：網頁沒有使用者提供的範例檔，若不先擋就會把
    # 不足的範例當成完整的 window 傳進核心（變成默默改變使用者要求的視窗）。
    # 訊息與 `scan_similar` 的同名檢查一致。
    if window > len(frame):
        raise ConfigError(f"序列長度 {len(frame)} 短於 window={window}，無法掃描")
    sample = frame.iloc[-window:].reset_index(drop=True)

    report = run_match(
        frame,
        sample,
        top=top,
        horizon=horizon,
        step=step,
        overlap=overlap,
        data_source=data_source,
    )
    return 200, report


route("POST", "/api/match", match)


# ---- AC-050：網頁關閉服務（TASK-026） ---------------------------------------


def shutdown(app: Any, _query: Mapping[str, Sequence[str]], _body: Any):
    """`POST /api/shutdown`：要求服務優雅關閉（網頁的「關閉服務」按鈕）。

    只**設定關閉事件**並立刻回應，真正的停止由服務主迴圈執行（`launcher._run_service`
    等待同一個事件）。在 handler 裡直接關閉服務會讓瀏覽器收到連線中斷，而不是明確結果。
    """
    request = getattr(app, "request_shutdown", None)
    if not callable(request):
        raise _HttpError(503, "shutdown_unavailable", "此服務沒有可用的關閉路徑")
    request()
    return 200, {"status": "shutting_down", "message": "服務正在關閉，這個頁面即將無法連線"}


route("POST", "/api/shutdown", shutdown)


# ---- AC-047／AC-048／AC-066：監控清單、系統狀態、版本與授權（TASK-025） -----

#: 商品搜尋一次最多回幾筆（下拉選單用）。
DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 50
#: 監控設定允許由網頁變更的鍵（其餘鍵由「設定」頁負責，屬 TASK-019／TASK-025 的邊界）。
WATCHLIST_KEYS: tuple[str, ...] = (
    "poll_interval_seconds",
    "events_path",
    "cache_dir",
    "pattern_id",
    "pattern_spec",
    "horizon",
    "instruments",
)
#: 重新申請的導流位置（真正的重新申請頁屬 TASK-035）。
#: 現階段指向授權區塊的**既有錨點**——先前的 `/static/license_page.html#reapply` 指向一個
#: 不存在的頁面（`GET` 會 404），使用者點下去只會看到錯誤頁，等於沒有連結。
REAPPLY_URL = "/#license-heading"


def _search_limit(query: Mapping[str, Sequence[str]]) -> int:
    raw = _first(query, "limit")
    if raw is None:
        return DEFAULT_SEARCH_LIMIT
    try:
        limit = int(raw)
    except ValueError as error:
        raise ConfigError(f"limit 必須是整數，收到 {raw!r}") from error
    if limit < 1 or limit > MAX_SEARCH_LIMIT:
        raise ConfigError(f"limit 必須介於 1 與 {MAX_SEARCH_LIMIT}，收到 {limit}")
    return limit


def instruments(app: Any, query: Mapping[str, Sequence[str]], _body: Any):
    """`GET /api/instruments/search?q=&limit=&source=`：下拉搜尋商品（AC-047）。

    搜尋本身完全交給來源的 `search`（不在網頁層比對代號或名稱）；未指定 `source` 時
    依序問所有已註冊來源，**單一來源失敗不影響其他來源**（失敗原因隨回應附上，狀態頁
    也會呈現來源問題）。
    """
    keyword = _require_query(query, "q")
    limit = _search_limit(query)
    explicit = _first(query, "source")
    sources = [get_source(explicit)] if explicit else list(all_sources())

    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for source in sources:
        if len(items) >= limit:
            break
        try:
            found = source.search(keyword, limit=limit - len(items))
        except EdiaadError as error:
            errors.append(f"{source.id}：{error}")
            continue
        for instrument in found:
            items.append(
                {
                    "symbol": instrument.symbol,
                    "display_name": instrument.display_name or instrument.symbol,
                    "interval": instrument.interval,
                    "source_id": instrument.source_id or source.id,
                }
            )
            if len(items) >= limit:
                break
    return 200, {
        "items": items,
        "count": len(items),
        "sources": [source.id for source in sources],
        "errors": errors,
    }


def _watchlist_mapping(app: Any) -> dict[str, Any]:
    """目前監控設定的正規映射（沒有 `watchlist.json` 時以設定推導一份候選）。"""
    watchlist = app.watchlist
    if watchlist is not None:
        return {
            "poll_interval_seconds": watchlist.poll_interval_seconds,
            "events_path": watchlist.events_path,
            "cache_dir": watchlist.cache_dir,
            "pattern_id": watchlist.pattern_id,
            "pattern_spec": (
                None
                if watchlist.pattern_spec is None
                else dataclasses.asdict(watchlist.pattern_spec)
            ),
            "horizon": watchlist.horizon,
            "instruments": [
                {
                    "symbol": instrument.symbol,
                    "interval": instrument.interval,
                    "source_id": instrument.source_id,
                }
                for instrument in watchlist.instruments
            ],
        }

    settings = app.settings
    return {
        "poll_interval_seconds": settings["poll_interval_seconds"],
        "events_path": str(Path(app.home) / ".cache" / "events.jsonl"),
        "cache_dir": str(app.cache_dir),
        "pattern_id": settings["pattern_id"],
        "pattern_spec": settings["pattern_spec"],
        "horizon": settings["horizon"],
        "instruments": [],
    }


def _watchlist_payload(app: Any) -> dict[str, Any]:
    return {
        "watchlist": _watchlist_mapping(app),
        "path": str(app.watchlist_path),
        "configured": app.watchlist is not None,
        "monitor_running": app.monitor_running,
    }


def watchlist(app: Any, _query: Mapping[str, Sequence[str]], _body: Any):
    """`GET /api/watchlist`：目前監控設定（含檔案位置與是否已設定）。"""
    return 200, _watchlist_payload(app)


def save_watchlist(app: Any, _query: Mapping[str, Sequence[str]], body: Any):
    """`POST /api/watchlist`：驗證後原子寫入，**下一次 `run_once` 即以新清單輪詢**（AC-047）。

    驗證完全交給 `monitor.validate_config`（與 CLI 讀設定同一套規則，含「週期必須是該
    來源支援的」）；寫入用 `monitor.save_config`（原子）。驗證失敗一律 400 且**不寫檔**。
    """
    payload = _body_object(body)
    nested = payload.get("watchlist")
    changes: Mapping[str, Any] = nested if isinstance(nested, Mapping) else payload
    unknown = sorted(set(changes) - set(WATCHLIST_KEYS))
    if unknown:
        raise ConfigError(
            f"未知的設定鍵：{'、'.join(unknown)}；可用鍵：{list(WATCHLIST_KEYS)}"
        )

    candidate = _watchlist_mapping(app)
    candidate.update({key: changes[key] for key in changes})

    # 空清單與週期合法性都由 `validate_config` 統一把關（不在路由層重寫同一條規則）
    watchlist_object = validate_config(candidate)
    try:
        save_config(app.watchlist_path, watchlist_object)
    except OSError as error:
        raise SourceError(f"無法寫入監控設定 {app.watchlist_path}：{error}") from error

    app.watchlist = watchlist_object
    return 200, _watchlist_payload(app)


def status(app: Any, _query: Mapping[str, Sequence[str]], _body: Any):
    """`GET /api/status`：系統狀態頁的資料（最後輪詢時間、逐商品來源與錯誤）。"""
    return 200, app.status_payload()


def _update_message(state: Any, enabled: bool) -> str:
    """更新狀態的一句話（**「還沒檢查」「檢查中」「已關閉」「檢查失敗」四者不得混淆**）。

    與 F-003 同一條紀律：沒有結果、正在檢查、被關閉、以及檢查失敗是四種不同的處境；
    全部回「尚未檢查」會讓使用者以為服務還沒試過，而實際上已經試過且失敗了。
    """
    if not enabled:
        return "更新檢查已關閉"
    if state is None:
        return "尚未檢查更新"
    if getattr(state, "source", None) == "pending":
        return "更新檢查進行中"
    error = getattr(state, "error", None)
    if error:
        return f"更新檢查失敗：{error}"
    return ""


def version(app: Any, _query: Mapping[str, Sequence[str]], _body: Any):
    """`GET /api/version`：目前版本與最近一次更新檢查的結果（AC-048、AC-059 第 4 條）。

    順便排一次背景檢查（去抖動 5 分鐘、立即回快取，因此不阻塞本請求）。**要不要檢查由
    `Application.trigger_update_check` 單獨決定**（沒有網址或已關閉時它會回 `False`），
    這裡不再重寫一次同樣的判斷——兩處各判一次就是兩份會分岔的規則。
    沒有結果時欄位為 `null` 並標示「尚未檢查」，不假裝有資料。
    """
    trigger = getattr(app, "trigger_update_check", None)
    if trigger is not None:
        trigger()

    state = getattr(app, "update_state", None)
    enabled = bool(app.settings.get("update_enabled", True))
    latest = getattr(state, "latest_version", None) if state is not None else None
    return 200, {
        "version": app.version,
        "latest_version": latest,
        "released_at": getattr(state, "released_at", None) if state is not None else None,
        "notes": getattr(state, "notes", None) if state is not None else None,
        "checked_at": getattr(state, "checked_at", None) if state is not None else None,
        "catalog_version": getattr(state, "catalog_version", None) if state is not None else None,
        "source": getattr(state, "source", None) if state is not None else None,
        "error": getattr(state, "error", None) if state is not None else None,
        "update_enabled": enabled,
        "update_available": bool(latest is not None and latest != app.version),
        "message": _update_message(state, enabled),
    }


#: `lease_status` 的狀態 → 授權頁 API 的用語（`unactivated` 對外叫 `inactive`）。
LICENSE_STATES = {
    "unactivated": "inactive",
    "active": "active",
    "expired": "expired",
    "revoked": "revoked",
}


def license_status(app: Any, _query: Mapping[str, Sequence[str]], _body: Any):
    """`GET /api/license`：授權狀態、剩餘天數、功能與重新申請連結（AC-066）。

    `lease.json` 不存在是**正常狀態**（尚未啟用），回 `state="inactive"` 與首次啟用表單
    所需的資訊；租約損毀則回 `state="error"` 與可讀原因——兩者都不得是 500。
    """
    lease = None
    error_message = ""
    try:
        lease = load_lease(app.lease_path)
    except ConfigError as error:
        error_message = str(error)

    if error_message:
        return 200, {
            "state": "error",
            "message": f"租約無法解讀：{error_message}",
            "expires_at": None,
            "days_remaining": None,
            "reapply": True,
            "reapply_url": REAPPLY_URL,
            "features": [],
            "key_id": None,
            "has_lease": True,
        }

    verdict = lease_status(lease, now=None, revoked_path=app.revoked_path)
    return 200, {
        "state": LICENSE_STATES.get(verdict.state, verdict.state),
        "message": verdict.message,
        "expires_at": verdict.expires_at,
        "days_remaining": verdict.days_remaining,
        "reapply": verdict.reapply,
        "reapply_url": REAPPLY_URL,
        "features": list(lease.features) if lease is not None else [],
        "key_id": lease.key_id if lease is not None else None,
        "has_lease": lease is not None,
    }


route("GET", "/api/instruments/search", instruments)
route("GET", "/api/watchlist", watchlist)
route("POST", "/api/watchlist", save_watchlist)
route("GET", "/api/status", status)
route("GET", "/api/version", version)
route("GET", "/api/license", license_status)


def _license_url() -> str:
    """授權服務網址（環境變數 `EDIAAD_LICENSE_URL`；未設定時拒絕啟用而不是猜一個）。"""
    return (os.environ.get("EDIAAD_LICENSE_URL") or "").strip()


def activate_license(app: Any, _query: Mapping[str, Sequence[str]], body: Any):
    """`POST /api/license/activate`：首次啟用或更換密鑰（AC-052／AC-057／AC-066 的表單）。

    密鑰與機器指紋送給授權服務，成功後原子寫入 `lease.json`；4xx（無效密鑰）→ 400、
    5xx／連線失敗 → 502。已啟用時再次呼叫即為**更換密鑰**，以新租約為準。
    """
    payload = _body_object(body)
    key = _body_text(payload, "key")
    url = _license_url()
    if not url:
        raise ConfigError("尚未設定授權服務網址（環境變數 EDIAAD_LICENSE_URL）")
    http = getattr(app, "license_http", None) or HTTP_CLIENT
    activate(
        key,
        fingerprint=machine_fingerprint(),
        http=http,
        url=url,
        public_key=getattr(app, "license_public_key", None) or LICENSE_PUBLIC_KEY,
        lease_path=app.lease_path,
    )
    return license_status(app, {}, None)


route("POST", "/api/license/activate", activate_license)
