"""`ediaad.markets.crypto`：Binance 公開端點來源與四種快取情境（TASK-013）。

觀察邊界：只呼叫模組級 `fetch_ohlcv`／`cache_path` 與 `get_source("binance").fetch`／
`search`，觀察回傳序列、`data_source` 標記、假 HTTP 客戶端的請求計數與快取檔內容。
所有測試離線，HTTP 一律注入假客戶端（可回傳固定 payload 或丟出例外）。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import pytest

from ediaad.data import SERIES_COLUMNS, load_csv
from ediaad.errors import ConfigError, SourceError
from ediaad.markets.base import all_sources, get_source

HOUR_MS = 3_600_000
START_MS = 1_700_000_000_000  # 2023-11-14T22:13:20Z


class FakeHttp:
    """假 HTTP 客戶端：記錄請求 URL，回傳固定 payload 或丟出指定例外。"""

    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[str] = []

    def __call__(self, url: str):
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        return self.payload

    @property
    def count(self) -> int:
        return len(self.calls)


def kline_rows(*, count: int = 3, base: float = 100.0, start_ms: int = START_MS) -> list[list]:
    """Binance `klines` 的回應形狀：每個元素是 12 欄的陣列，數字以字串表示。"""
    rows = []
    for index in range(count):
        opened = start_ms + index * HOUR_MS
        price = base + index
        rows.append(
            [
                opened,
                f"{price:.1f}",
                f"{price + 1:.1f}",
                f"{price - 1:.1f}",
                f"{price:.1f}",
                "10.5",
                opened + HOUR_MS - 1,
                "0.0",
                1,
                "0.0",
                "0.0",
                "0",
            ]
        )
    return rows


def write_cache(cache_dir: Path, symbol: str, interval: str, frame: pd.DataFrame) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{symbol}_{interval}.csv"
    frame.to_csv(path, index=False)
    return path


def make_frame(*, count: int = 3, base: float = 100.0) -> pd.DataFrame:
    """以模組自己的解析路徑建立一份符合契約的序列（不經過快取）。"""
    from ediaad.markets.crypto import fetch_ohlcv

    result = fetch_ohlcv(
        "BTCUSDT", "1h", cache_dir=None, client=FakeHttp(payload=kline_rows(count=count, base=base))
    )
    return result.series


def age_file(path: Path, seconds: float) -> None:
    """把檔案的 mtime 往回移，模擬過期快取。"""
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


# ---- AC-031：四種快取情境 ---------------------------------------------------


def test_fresh_cache_is_returned_without_any_request(tmp_path):
    from ediaad.markets.crypto import fetch_ohlcv

    cache_dir = tmp_path / "ohlcv"
    cached = make_frame(count=4, base=100.0)
    write_cache(cache_dir, "BTCUSDT", "1h", cached)
    http = FakeHttp(payload=kline_rows(count=4, base=999.0))

    result = fetch_ohlcv("BTCUSDT", "1h", cache_dir=cache_dir, client=http)

    assert result.data_source == "cache"
    assert http.count == 0, "快取有效時不得發出任何請求"
    pd.testing.assert_frame_equal(result.series, cached)


def test_fresh_cache_series_matches_the_contract(tmp_path):
    from ediaad.markets.crypto import fetch_ohlcv

    cache_dir = tmp_path / "ohlcv"
    write_cache(cache_dir, "BTCUSDT", "1h", make_frame(count=4))

    series = fetch_ohlcv("BTCUSDT", "1h", cache_dir=cache_dir, client=FakeHttp()).series

    assert list(series.columns) == list(SERIES_COLUMNS)
    assert str(series["time"].dtype) == "datetime64[ns, UTC]"
    assert series["time"].is_monotonic_increasing
    assert not series["time"].duplicated().any()
    for column in ("open", "high", "low", "close", "volume"):
        assert series[column].dtype == "float64", column


def test_expired_cache_triggers_a_request_and_rewrites_the_file(tmp_path):
    from ediaad.markets.crypto import fetch_ohlcv

    cache_dir = tmp_path / "ohlcv"
    stale = make_frame(count=2, base=100.0)
    path = write_cache(cache_dir, "BTCUSDT", "1h", stale)
    age_file(path, 10_000)
    http = FakeHttp(payload=kline_rows(count=5, base=200.0))

    result = fetch_ohlcv("BTCUSDT", "1h", cache_dir=cache_dir, client=http)

    assert result.data_source == "binance"
    assert http.count == 1
    assert "symbol=BTCUSDT" in http.calls[0]
    assert "interval=1h" in http.calls[0]
    assert len(result.series) == 5
    assert result.series["close"].iloc[0] == pytest.approx(200.0)

    rewritten = load_csv(path)
    pd.testing.assert_frame_equal(rewritten, result.series)


def test_missing_cache_triggers_a_request_and_creates_the_file(tmp_path):
    from ediaad.markets.crypto import cache_path, fetch_ohlcv

    cache_dir = tmp_path / "ohlcv"
    http = FakeHttp(payload=kline_rows(count=3, base=300.0))

    result = fetch_ohlcv("BTCUSDT", "1h", cache_dir=cache_dir, client=http)

    assert result.data_source == "binance"
    assert http.count == 1
    path = cache_path("BTCUSDT", "1h", cache_dir)
    assert path.is_file()
    pd.testing.assert_frame_equal(load_csv(path), result.series)


def test_failure_with_a_stale_cache_returns_the_stale_copy(tmp_path):
    from ediaad.markets.crypto import fetch_ohlcv

    cache_dir = tmp_path / "ohlcv"
    stale = make_frame(count=3, base=100.0)
    path = write_cache(cache_dir, "BTCUSDT", "1h", stale)
    age_file(path, 10_000)
    http = FakeHttp(error=OSError("network down"))

    result = fetch_ohlcv("BTCUSDT", "1h", cache_dir=cache_dir, client=http)

    assert result.data_source == "cache-stale"
    assert http.count == 1, "過期快取仍必須先嘗試重新取得"
    pd.testing.assert_frame_equal(result.series, stale)


def test_failure_without_a_cache_raises_a_source_error(tmp_path):
    from ediaad.markets.crypto import fetch_ohlcv

    http = FakeHttp(error=OSError("network down"))

    with pytest.raises(SourceError) as excinfo:
        fetch_ohlcv("BTCUSDT", "1h", cache_dir=tmp_path / "ohlcv", client=http)

    message = str(excinfo.value)
    assert "BTCUSDT" in message, "來源錯誤必須指出商品"
    assert "network down" in message, "來源錯誤必須保留原始原因"
    assert http.count == 1


def test_the_source_is_registered_and_reports_the_data_source_in_attrs(tmp_path):
    from ediaad.markets.crypto import BinanceSource

    cache_dir = tmp_path / "ohlcv"
    source = BinanceSource(cache_dir=cache_dir, client=FakeHttp(payload=kline_rows()))

    frame = source.fetch("BTCUSDT", "1h")

    assert frame.attrs["data_source"] == "binance"
    assert list(frame.columns) == list(SERIES_COLUMNS)
    assert get_source("binance") is get_source("binance")
    assert "binance" in [item.id for item in all_sources()]


def test_binance_source_declares_its_protocol_members(tmp_path):
    source = get_source("binance")

    assert source.id == "binance"
    assert source.display_name.strip()
    assert source.needs_api_key is False
    assert "1h" in source.supported_intervals
    assert all(item in source.supported_intervals for item in ("1m", "4h", "1d", "1w"))
    for member in ("search", "fetch"):
        assert callable(getattr(source, member))


def test_cache_path_follows_the_documented_layout(tmp_path):
    from ediaad.markets.crypto import cache_path

    path = cache_path("BTCUSDT", "1h", tmp_path)

    assert path == Path(tmp_path) / "BTCUSDT_1h.csv"


# ---- 契約與錯誤邊界 ---------------------------------------------------------


def test_without_a_cache_dir_every_call_requests_fresh_data():
    from ediaad.markets.crypto import fetch_ohlcv

    http = FakeHttp(payload=kline_rows(count=2, base=50.0))

    first = fetch_ohlcv("BTCUSDT", "1h", cache_dir=None, client=http)
    second = fetch_ohlcv("BTCUSDT", "1h", cache_dir=None, client=http)

    assert (first.data_source, second.data_source) == ("binance", "binance")
    assert http.count == 2, "不使用快取時不得跳過請求"
    assert len(second.series) == 2


def test_without_a_cache_dir_a_failure_is_a_source_error():
    from ediaad.markets.crypto import fetch_ohlcv

    with pytest.raises(SourceError, match="BTCUSDT"):
        fetch_ohlcv("BTCUSDT", "1h", cache_dir=None, client=FakeHttp(error=OSError("boom")))


def test_the_injected_clock_decides_freshness(tmp_path):
    """不動檔案 mtime，只用注入的時鐘決定快取是否過期。"""
    from ediaad.markets.crypto import fetch_ohlcv

    cache_dir = tmp_path / "ohlcv"
    cached = make_frame(count=3, base=100.0)
    write_cache(cache_dir, "BTCUSDT", "1h", cached)
    written_at = cache_path_mtime(cache_dir)

    http = FakeHttp(payload=kline_rows(count=3, base=777.0))

    fresh = fetch_ohlcv(
        "BTCUSDT", "1h", cache_dir=cache_dir, client=http, now=lambda: written_at + 899
    )
    expired = fetch_ohlcv(
        "BTCUSDT", "1h", cache_dir=cache_dir, client=http, now=lambda: written_at + 901
    )

    assert fresh.data_source == "cache"
    assert expired.data_source == "binance"
    assert http.count == 1, "只有過期的那一次可以發出請求"
    assert expired.series["close"].iloc[0] == pytest.approx(777.0)


def cache_path_mtime(cache_dir: Path) -> float:
    return (cache_dir / "BTCUSDT_1h.csv").stat().st_mtime


def test_a_zero_max_age_always_revalidates(tmp_path):
    from ediaad.markets.crypto import fetch_ohlcv

    cache_dir = tmp_path / "ohlcv"
    write_cache(cache_dir, "BTCUSDT", "1h", make_frame(count=2))
    http = FakeHttp(payload=kline_rows(count=2, base=123.0))

    result = fetch_ohlcv("BTCUSDT", "1h", cache_dir=cache_dir, client=http, max_age=0)

    assert result.data_source == "binance"
    assert http.count == 1


@pytest.mark.parametrize(
    "corrupt",
    [
        pytest.param("not a csv at all", id="非 CSV 內容"),
        pytest.param("time,open,high,low,close,volume\n", id="只有表頭沒有資料列"),
        pytest.param(
            "time,open,high,low,close\n2024-01-01T00:00:00Z,1,1,1,1\n", id="缺 volume 欄"
        ),
    ],
)
def test_a_corrupt_cache_is_treated_as_no_cache(tmp_path, corrupt):
    from ediaad.markets.crypto import fetch_ohlcv

    cache_dir = tmp_path / "ohlcv"
    cache_dir.mkdir()
    (cache_dir / "BTCUSDT_1h.csv").write_text(corrupt, encoding="utf-8")
    http = FakeHttp(payload=kline_rows(count=2, base=456.0))

    result = fetch_ohlcv("BTCUSDT", "1h", cache_dir=cache_dir, client=http)

    assert result.data_source == "binance", "損毀的快取不得被當成有效快取"
    assert http.count == 1
    assert result.series["close"].iloc[0] == pytest.approx(456.0)


def test_a_corrupt_cache_with_a_failing_source_raises_a_source_error(tmp_path):
    from ediaad.markets.crypto import fetch_ohlcv

    cache_dir = tmp_path / "ohlcv"
    cache_dir.mkdir()
    (cache_dir / "BTCUSDT_1h.csv").write_text("garbage", encoding="utf-8")

    with pytest.raises(SourceError):
        fetch_ohlcv("BTCUSDT", "1h", cache_dir=cache_dir, client=FakeHttp(error=OSError("x")))


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"code": -1121, "msg": "Invalid symbol."}, id="錯誤物件"),
        pytest.param([], id="空陣列"),
        pytest.param("not json", id="非 JSON 內容"),
        pytest.param([[1, "2", "3"]], id="欄位不足"),
        pytest.param([["not-a-number", "1", "1", "1", "1", "1"]], id="時間無法解讀"),
        pytest.param([[START_MS, "x", "1", "1", "1", "1"]], id="價格非數值"),
        pytest.param([START_MS], id="列不是陣列"),
    ],
)
def test_a_malformed_response_is_a_readable_source_error(tmp_path, payload):
    from ediaad.markets.crypto import fetch_ohlcv

    http = FakeHttp(payload=payload)

    with pytest.raises(SourceError) as excinfo:
        fetch_ohlcv("BTCUSDT", "1h", cache_dir=tmp_path / "ohlcv", client=http)

    assert "Binance" in str(excinfo.value), "訊息必須指出是 Binance 回應的問題"


@pytest.mark.parametrize(
    ("kwargs", "mentions"),
    [
        pytest.param({"interval": "2h"}, "2h", id="不支援的週期"),
        pytest.param({"interval": ""}, "interval", id="空週期"),
        pytest.param({"symbol": ""}, "symbol", id="空商品"),
        pytest.param({"symbol": "   "}, "symbol", id="空白商品"),
        pytest.param({"limit": 0}, "limit", id="limit 為 0"),
        pytest.param({"limit": 1001}, "limit", id="limit 超過上限"),
        pytest.param({"limit": True}, "limit", id="limit 為布林"),
    ],
)
def test_invalid_arguments_are_config_errors(tmp_path, kwargs, mentions):
    from ediaad.markets.crypto import fetch_ohlcv

    arguments = {"symbol": "BTCUSDT", "interval": "1h", **kwargs}

    with pytest.raises(ConfigError, match=mentions):
        fetch_ohlcv(
            **arguments, cache_dir=tmp_path / "ohlcv", client=FakeHttp(payload=kline_rows())
        )


def test_the_symbol_is_normalised_before_the_request_and_the_cache_path(tmp_path):
    from ediaad.markets.crypto import fetch_ohlcv

    cache_dir = tmp_path / "ohlcv"
    http = FakeHttp(payload=kline_rows(count=1))

    result = fetch_ohlcv("  btcusdt ", "1h", cache_dir=cache_dir, client=http)

    assert "symbol=BTCUSDT" in http.calls[0]
    assert (cache_dir / "BTCUSDT_1h.csv").is_file(), "快取檔名一律用大寫商品代號"
    assert load_csv(cache_dir / "BTCUSDT_1h.csv").equals(result.series)


def test_the_cache_is_written_atomically_leaving_no_temporary_file(tmp_path):
    from ediaad.markets.crypto import fetch_ohlcv

    cache_dir = tmp_path / "ohlcv"
    fetch_ohlcv(
        "BTCUSDT", "1h", cache_dir=cache_dir, client=FakeHttp(payload=kline_rows(count=2))
    )

    leftovers = sorted(path.name for path in cache_dir.iterdir())
    assert leftovers == ["BTCUSDT_1h.csv"], f"不得留下暫存檔：{leftovers}"


def test_an_unwritable_cache_directory_is_a_source_error(tmp_path):
    from ediaad.markets.crypto import fetch_ohlcv

    cache_dir = tmp_path / "readonly"
    cache_dir.mkdir()
    os.chmod(cache_dir, 0o500)
    try:
        with pytest.raises(SourceError) as excinfo:
            fetch_ohlcv(
                "BTCUSDT",
                "1h",
                cache_dir=cache_dir,
                client=FakeHttp(payload=kline_rows(count=2)),
            )
    finally:
        os.chmod(cache_dir, 0o700)

    assert "快取" in str(excinfo.value)
    assert not list(cache_dir.iterdir()), "失敗時不得留下半寫的快取檔"


# ---- 商品搜尋（exchangeInfo） -----------------------------------------------


def exchange_info(*entries) -> dict:
    return {
        "symbols": [
            {
                "symbol": symbol,
                "baseAsset": base,
                "quoteAsset": quote,
                "status": "TRADING",
            }
            for symbol, base, quote in entries
        ]
    }


DEFAULT_EXCHANGE_INFO = exchange_info(
    ("BTCUSDT", "BTC", "USDT"),
    ("ETHUSDT", "ETH", "USDT"),
    ("BTCTRY", "BTC", "TRY"),
    ("AAPL", "AAPL", "USDT"),
)


def test_search_returns_nothing_for_an_empty_query():
    from ediaad.markets.crypto import BinanceSource

    http = FakeHttp(payload=DEFAULT_EXCHANGE_INFO)
    source = BinanceSource(client=http)

    assert source.search("") == []
    assert source.search("   ") == []
    assert source.search("", limit=5) == []
    assert http.count == 0, "空查詢不應發出請求"


def test_search_matches_the_symbol_regardless_of_case():
    from ediaad.markets.crypto import BinanceSource

    source = BinanceSource(client=FakeHttp(payload=DEFAULT_EXCHANGE_INFO))

    results = source.search("btcusdt")

    assert [item.symbol for item in results] == ["BTCUSDT"]
    assert results[0].source_id == "binance"
    assert results[0].interval == ""
    assert results[0].display_name == "BTCUSDT"


def test_search_matches_any_symbol_containing_the_query():
    """子字串比對：`BTC` 命中兩個商品，`TRY` 只命中以 TRY 計價的那一個。"""
    from ediaad.markets.crypto import BinanceSource

    source = BinanceSource(client=FakeHttp(payload=DEFAULT_EXCHANGE_INFO))

    assert [item.symbol for item in source.search("BTC")] == ["BTCUSDT", "BTCTRY"]
    assert [item.symbol for item in source.search("try")] == ["BTCTRY"]
    assert source.search("NOPE") == []


def test_search_respects_the_limit_and_keeps_the_payload_order():
    from ediaad.markets.crypto import BinanceSource

    source = BinanceSource(client=FakeHttp(payload=DEFAULT_EXCHANGE_INFO))

    assert [item.symbol for item in source.search("USDT", limit=1)] == ["BTCUSDT"]
    assert [item.symbol for item in source.search("USDT", limit=2)] == [
        "BTCUSDT",
        "ETHUSDT",
    ]
    assert source.search("USDT", limit=0) == []


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(OSError("network down"), id="網路錯誤"),
        pytest.param(ValueError("invalid JSON"), id="客戶端解碼失敗"),
        pytest.param(RuntimeError("HTTP 500"), id="非預期例外"),
    ],
)
def test_any_exception_from_the_injected_client_is_a_source_error(tmp_path, error):
    """注入的客戶端是外部邊界：任何例外都是來源失敗（含舊快取回退的判斷）。"""
    from ediaad.markets.crypto import fetch_ohlcv

    cache_dir = tmp_path / "ohlcv"
    stale = make_frame(count=2, base=100.0)
    age_file(write_cache(cache_dir, "BTCUSDT", "1h", stale), 10_000)

    result = fetch_ohlcv("BTCUSDT", "1h", cache_dir=cache_dir, client=FakeHttp(error=error))

    assert result.data_source == "cache-stale"
    pd.testing.assert_frame_equal(result.series, stale)

    with pytest.raises(SourceError):
        fetch_ohlcv("BTCUSDT", "1h", cache_dir=None, client=FakeHttp(error=error))


def test_search_requests_the_exchange_info_endpoint():
    from ediaad.markets.crypto import EXCHANGE_INFO_PATH, BinanceSource

    http = FakeHttp(payload=DEFAULT_EXCHANGE_INFO)
    BinanceSource(client=http).search("BTC")

    assert http.count == 1
    assert http.calls[0].endswith(EXCHANGE_INFO_PATH)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param([], id="不是物件"),
        pytest.param({"symbols": "nope"}, id="symbols 不是陣列"),
        pytest.param({"code": -1}, id="缺少 symbols"),
    ],
)
def test_malformed_exchange_info_is_a_source_error(payload):
    from ediaad.markets.crypto import BinanceSource

    with pytest.raises(SourceError, match="Binance"):
        BinanceSource(client=FakeHttp(payload=payload)).search("BTC")


def test_a_failing_exchange_info_request_is_a_source_error():
    from ediaad.markets.crypto import BinanceSource

    with pytest.raises(SourceError, match="商品清單"):
        BinanceSource(client=FakeHttp(error=OSError("down"))).search("BTC")


def test_exchange_info_entries_missing_fields_are_skipped():
    from ediaad.markets.crypto import BinanceSource

    payload = {"symbols": [{"baseAsset": "BTC", "quoteAsset": "USDT"}, "junk", {"symbol": "ETHUSDT"}]}

    results = BinanceSource(client=FakeHttp(payload=payload)).search("")

    assert results == []
    hits = BinanceSource(client=FakeHttp(payload=payload)).search("ETH")
    assert [item.symbol for item in hits] == ["ETHUSDT"]
