"""Binance 公開端點來源（加密貨幣）與四種快取情境（AC-031）。

**本模組是 Binance 的唯一實作路徑**（SPEC 第 5 節「相容性／遷移」與 ADR-001）：不建立
報告第 4.3／6.1 節的 `ediaad/sources/binance.py` 向後相容層，避免同一份資料經兩條路徑
產生不同結構（報告 F-001）。

四種快取情境（報告第 3.1 節 F13）：

| 情況 | 行為 | `data_source` |
| --- | --- | --- |
| 快取仍在有效期內 | 直接讀快取，**不發出請求** | `cache` |
| 快取過期或不存在 | 重新取得並覆寫快取 | `binance` |
| 取得失敗但有過期快取 | 使用過期快取 | `cache-stale` |
| 取得失敗且無快取 | 丟出 `SourceError` | — |

**只用公開端點**（`/klines`、`/exchangeInfo`），不接觸任何金鑰或私有 API。HTTP 以標準庫
`urllib` 實作，客戶端與時鐘皆可注入（SPEC 第 5 節原則 2），因此四種情境完全離線可測。
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from ..data import from_rows, load_csv
from ..errors import ConfigError, EdiaadError, SourceError
from .base import INTERVAL_ORDER, Instrument, register

__all__ = [
    "BASE_URL",
    "DEFAULT_LIMIT",
    "DEFAULT_MAX_AGE",
    "MAX_LIMIT",
    "BinanceSource",
    "OhlcvResult",
    "cache_path",
    "fetch_ohlcv",
]

#: Binance 公開 REST 端點（不需要金鑰）。
BASE_URL = "https://api.binance.com/api/v3"
KLINES_PATH = "/klines"
EXCHANGE_INFO_PATH = "/exchangeInfo"

#: `klines` 每列的欄位（只取前六欄成為序列契約）。
KLINE_COLUMNS: tuple[str, ...] = ("time", "open", "high", "low", "close", "volume")

DEFAULT_LIMIT = 500
MAX_LIMIT = 1000
#: 快取有效期（秒）。SPEC 第 5 節資料生命週期：`<cache_dir>/<symbol>_<interval>.csv` 由 `max_age` 控制。
DEFAULT_MAX_AGE = 900.0
HTTP_TIMEOUT = 10.0

HttpClient = Callable[[str], Any]


@dataclass(frozen=True)
class OhlcvResult:
    """一次取值的結果：序列與它的來源標記（`cache`／`binance`／`cache-stale`）。"""

    series: pd.DataFrame
    data_source: str


def cache_path(symbol: str, interval: str, cache_dir: str | Path) -> Path:
    """快取檔位置：`<cache_dir>/<symbol>_<interval>.csv`（SPEC 第 5 節資料生命週期）。"""
    return Path(cache_dir) / f"{symbol}_{interval}.csv"


def _default_client(url: str) -> Any:
    """標準庫 HTTP 客戶端：取得 JSON。不引入 `requests` 等新依賴。"""
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _require_symbol(symbol: str) -> str:
    if not isinstance(symbol, str) or not symbol.strip():
        raise ConfigError(f"symbol 必須是非空字串，收到 {symbol!r}")
    return symbol.strip().upper()


def _require_interval(interval: str) -> str:
    if interval not in INTERVAL_ORDER:
        raise ConfigError(
            f"interval 不支援 {interval!r}；Binance 可用週期：{list(INTERVAL_ORDER)}"
        )
    return interval


def _require_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ConfigError(f"limit 必須是 1 到 {MAX_LIMIT} 的整數，收到 {limit!r}")
    return limit


def _read_cache(path: Path | None) -> pd.DataFrame | None:
    """讀快取；不存在、無法讀取或內容損毀一律視為「沒有快取」。"""
    if path is None or not path.is_file():
        return None
    try:
        return load_csv(path)
    except (EdiaadError, OSError):
        return None


def _age_seconds(path: Path, clock: Callable[[], float]) -> float:
    return clock() - path.stat().st_mtime


def _is_fresh(path: Path, max_age: float, clock: Callable[[], float]) -> bool:
    try:
        return _age_seconds(path, clock) <= max_age
    except OSError:
        return False


def _write_cache(path: Path, series: pd.DataFrame) -> None:
    """原子覆寫快取：先寫同目錄暫存檔再 `replace`，避免留下半寫的 CSV。

    寫入失敗視為執行期失敗（`SourceError`）——快取目錄不可寫是部署問題，應立刻讓使用者
    知道（與 CLI「輸出檔不可寫 → exit 1」的分層一致），而不是每輪重試後才失敗。
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.tmp")
        try:
            series.to_csv(temporary, index=False)
            temporary.replace(path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise
    except OSError as error:
        raise SourceError(f"無法寫入快取 {path}：{error}") from error


def _fetch_klines(
    symbol: str, interval: str, limit: int, getter: HttpClient
) -> pd.DataFrame:
    """取得並解析 K 線；任何失敗都化為 `SourceError`（可讀且保留原因）。"""
    url = f"{BASE_URL}{KLINES_PATH}?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        payload = getter(url)
    except Exception as error:  # 注入的客戶端是外部邊界，任何例外都是來源失敗
        raise SourceError(f"Binance 請求失敗：{error}") from error

    if not isinstance(payload, list) or not payload:
        raise SourceError(
            f"Binance 回應必須是非空陣列，收到 {type(payload).__name__}"
        )

    # Binance 每列有 12 欄，序列契約只取前六欄；每列都必須是陣列。
    rows: list[list[Any]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, (list, tuple)):
            raise SourceError(
                f"Binance K 線第 {index} 列必須是陣列，收到 {type(row).__name__}"
            )
        rows.append(list(row)[: len(KLINE_COLUMNS)])

    try:
        return from_rows(rows, columns=KLINE_COLUMNS, time_unit="ms")
    except (EdiaadError, IndexError, ValueError, TypeError) as error:
        raise SourceError(f"Binance K 線格式無法解讀：{error}") from error


def fetch_ohlcv(
    symbol: str,
    interval: str,
    *,
    limit: int = DEFAULT_LIMIT,
    cache_dir: str | Path | None = None,
    client: HttpClient | None = None,
    max_age: float = DEFAULT_MAX_AGE,
    now: Callable[[], float] | None = None,
) -> OhlcvResult:
    """依四種快取情境取得序列（AC-031）。

    `cache_dir=None` 表示不使用快取（一律請求；失敗一律 `SourceError`），供只需要
    「抓一份乾淨資料」的呼叫端使用。
    """
    normalized = _require_symbol(symbol)
    interval = _require_interval(interval)
    limit = _require_limit(limit)
    getter = client if client is not None else _default_client
    clock = now if now is not None else time.time

    path = cache_path(normalized, interval, cache_dir) if cache_dir is not None else None
    cached = _read_cache(path)

    if path is not None and cached is not None and _is_fresh(path, max_age, clock):
        return OhlcvResult(series=cached, data_source="cache")

    try:
        fresh = _fetch_klines(normalized, interval, limit, getter)
    except SourceError as error:
        if cached is not None:
            return OhlcvResult(series=cached, data_source="cache-stale")
        raise SourceError(
            f"取得 {normalized} {interval} 失敗，且沒有可用的快取：{error}"
        ) from error

    if path is not None:
        _write_cache(path, fresh)
    return OhlcvResult(series=fresh, data_source="binance")


class BinanceSource:
    """`Source` 協定的 Binance 實作（`needs_api_key=False`，只用公開端點）。"""

    id = "binance"
    display_name = "Binance 加密貨幣"
    supported_intervals = INTERVAL_ORDER
    needs_api_key = False

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        *,
        client: HttpClient | None = None,
        limit: int = DEFAULT_LIMIT,
        max_age: float = DEFAULT_MAX_AGE,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.client = client
        self.limit = limit
        self.max_age = max_age
        self.now = now

    def fetch(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int | None = None,
        cache_dir: str | Path | None = None,
        client: HttpClient | None = None,
        max_age: float | None = None,
        now: Callable[[], float] | None = None,
    ) -> pd.DataFrame:
        """回傳序列，並在 `attrs["data_source"]` 標示來源（`cache`／`binance`／`cache-stale`）。"""
        result = fetch_ohlcv(
            symbol,
            interval,
            limit=self.limit if limit is None else limit,
            cache_dir=self.cache_dir if cache_dir is None else cache_dir,
            client=self.client if client is None else client,
            max_age=self.max_age if max_age is None else max_age,
            now=self.now if now is None else now,
        )
        series = result.series
        series.attrs["data_source"] = result.data_source
        return series

    def search(
        self, query: str, limit: int = 20, *, client: HttpClient | None = None
    ) -> list[Instrument]:
        """以 `exchangeInfo` 的商品清單比對商品代號（不分大小寫、子字串比對）。

        Binance spot 的商品代號固定是「基礎資產 ＋ 計價資產」（`BTC` ＋ `USDT` →
        `BTCUSDT`），因此比對代號已涵蓋基礎與計價資產，不需要額外比對
        `baseAsset`／`quoteAsset`（那兩個欄位必然是代號的子字串，額外比對無法觀測）。
        """
        text = query.strip().upper()
        if not text or limit < 1:
            return []

        getter = client if client is not None else (self.client or _default_client)
        url = f"{BASE_URL}{EXCHANGE_INFO_PATH}"
        try:
            payload = getter(url)
        except Exception as error:
            raise SourceError(f"Binance 商品清單請求失敗：{error}") from error

        symbols = payload.get("symbols") if isinstance(payload, dict) else None
        if not isinstance(symbols, list):
            raise SourceError("Binance exchangeInfo 回應缺少 symbols 陣列")

        results: list[Instrument] = []
        for item in symbols:
            if not isinstance(item, dict):
                continue
            name = str(item.get("symbol", ""))
            if not name:
                continue
            if text in name.upper():
                results.append(
                    Instrument(
                        symbol=name, interval="", source_id=self.id, display_name=name
                    )
                )
                if len(results) >= limit:
                    break
        return results


register(BinanceSource())
