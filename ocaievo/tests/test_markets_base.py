"""`ediaad.markets` 的來源介面、registry 與自訂 CSV 來源（TASK-012）。

觀察邊界：只匯入 `ediaad.markets.base`／`ediaad.markets.custom` 的公開名稱，以及
`ediaad.monitor.load_config`；不檢視模組內部的私有字典或常數。registry 的隔離以
公開的 `register`／`unregister` 完成。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ediaad.data import SERIES_COLUMNS, load_csv
from ediaad.errors import ConfigError, DataFormatError, SourceError
from ediaad.markets.base import (
    DEFAULT_SOURCE_ID,
    INTERVAL_ORDER,
    Instrument,
    all_sources,
    get_source,
    register,
    unregister,
)

#: AC-030 明訂的六項來源成員。
SOURCE_MEMBERS = (
    "id",
    "display_name",
    "supported_intervals",
    "needs_api_key",
    "search",
    "fetch",
)


class FakeDailySource:
    """只支援日線的假來源，用來驗證「依來源查詢週期」而非全域清單。"""

    id = "fake_daily"
    display_name = "假來源（僅日線）"
    supported_intervals = ("1d",)
    needs_api_key = False

    def search(self, query: str, limit: int = 20) -> list[Instrument]:
        return []

    def fetch(self, symbol: str, interval: str) -> pd.DataFrame:
        raise SourceError("假來源不可用")


@pytest.fixture
def with_fake_daily_source():
    """註冊假來源，測試結束後移除；不影響其他測試。"""
    register(FakeDailySource())
    try:
        yield FakeDailySource
    finally:
        unregister(FakeDailySource.id)


# ---- AC-030：Source 協定與 registry ----------------------------------------


def test_csv_source_is_registered_with_six_protocol_members():
    source = get_source("csv")

    for member in SOURCE_MEMBERS:
        assert hasattr(source, member), f"來源缺少成員 {member}"

    assert source.id == "csv"
    assert isinstance(source.display_name, str) and source.display_name.strip()
    assert isinstance(source.supported_intervals, tuple)
    assert source.supported_intervals, "來源至少要宣告一個支援的週期"
    assert all(isinstance(item, str) and item for item in source.supported_intervals)
    assert source.needs_api_key is False
    assert callable(source.search)
    assert callable(source.fetch)


def test_all_sources_lists_every_registered_source_sorted_by_id():
    before = [source.id for source in all_sources()]
    assert "csv" in before, "內建的自訂 CSV 來源必須預設註冊"

    register(FakeDailySource())
    try:
        ids = [source.id for source in all_sources()]
    finally:
        unregister(FakeDailySource.id)

    assert ids == sorted(ids), "all_sources 必須以 id 排序，讓輸出穩定"
    assert "csv" in ids and "fake_daily" in ids


def test_get_source_returns_the_registered_object():
    assert get_source("csv") is get_source("csv")


def test_get_source_reports_the_queried_id_and_the_available_ids():
    with pytest.raises(ConfigError) as excinfo:
        get_source("no_such_source")

    message = str(excinfo.value)
    assert "no_such_source" in message, "錯誤訊息必須指出查詢的 id"
    assert "csv" in message, "錯誤訊息必須列出可用的 id"


def test_register_rejects_a_duplicate_id_unless_replacement_is_explicit():
    class SecondCsvSource(FakeDailySource):
        id = "csv"

    with pytest.raises(ConfigError, match="csv"):
        register(SecondCsvSource())

    register(SecondCsvSource(), replace=True)
    try:
        assert get_source("csv").display_name == FakeDailySource.display_name
    finally:
        # 還原真正的 CSV 來源，避免汙染其他測試。
        from ediaad.markets.custom import CsvSource

        register(CsvSource(), replace=True)

    assert get_source("csv").__class__.__name__ == "CsvSource"


def test_register_rejects_an_incomplete_source():
    class Incomplete:
        id = "incomplete"
        display_name = "缺 fetch"
        supported_intervals = ("1d",)
        needs_api_key = False

        def search(self, query: str, limit: int = 20) -> list[Instrument]:
            return []

    with pytest.raises(ConfigError, match="fetch"):
        register(Incomplete())


def test_unregister_reports_an_unknown_id():
    with pytest.raises(ConfigError, match="ghost"):
        unregister("ghost")


def test_registered_source_exposes_its_own_supported_intervals(with_fake_daily_source):
    assert get_source("fake_daily").supported_intervals == ("1d",)
    assert "1h" not in get_source("fake_daily").supported_intervals
    # csv 來源與只支援日線的來源並存，證明週期不是全域清單。
    assert "1h" in get_source("csv").supported_intervals


def test_interval_order_is_a_canonical_ordering_not_an_allowlist():
    assert INTERVAL_ORDER == ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w")
    assert len(set(INTERVAL_ORDER)) == len(INTERVAL_ORDER)
    assert tuple(get_source("csv").supported_intervals) == INTERVAL_ORDER


def test_instrument_carries_symbol_interval_source_and_display_name():
    instrument = Instrument(
        symbol="BTCUSDT", interval="1h", source_id="csv", display_name="比特幣"
    )

    assert (instrument.symbol, instrument.interval) == ("BTCUSDT", "1h")
    assert (instrument.source_id, instrument.display_name) == ("csv", "比特幣")
    assert instrument == Instrument(
        symbol="BTCUSDT", interval="1h", source_id="csv", display_name="比特幣"
    )


def test_instrument_defaults_leave_the_source_unspecified():
    instrument = Instrument(symbol="2330", interval="1d")

    assert instrument.source_id == ""
    assert instrument.display_name == ""


# ---- AC-037：自訂 CSV 來源 --------------------------------------------------


def build_rows(total: int = 6) -> pd.DataFrame:
    times = pd.date_range("2024-01-01T00:00:00Z", periods=total, freq="1h", tz="UTC")
    closes = [100.0 + index for index in range(total)]
    return pd.DataFrame(
        {
            "time": times,
            "open": [value - 0.5 for value in closes],
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": closes,
            "volume": [10.0 + index for index in range(total)],
        }
    )


def write_csv_at(root: Path, symbol: str, interval: str, frame: pd.DataFrame) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{symbol}_{interval}.csv"
    frame.to_csv(path, index=False)
    return path


def test_csv_fetch_returns_exactly_what_load_csv_returns(tmp_path):
    from ediaad.markets.custom import CsvSource

    root = tmp_path / "ohlcv"
    path = write_csv_at(root, "BTCUSDT", "1h", build_rows())

    frame = CsvSource(root).fetch("BTCUSDT", "1h")
    expected = load_csv(path)

    pd.testing.assert_frame_equal(frame, expected)
    assert list(frame.columns) == list(SERIES_COLUMNS)
    assert frame["time"].is_monotonic_increasing


def test_csv_fetch_reports_a_missing_file_as_a_source_error(tmp_path):
    from ediaad.markets.custom import CsvSource

    root = tmp_path / "ohlcv"
    root.mkdir()

    with pytest.raises(SourceError) as excinfo:
        CsvSource(root).fetch("NOPE", "1d")

    message = str(excinfo.value)
    assert "NOPE_1d.csv" in message, "來源錯誤必須指出預期的檔名"


def test_csv_fetch_requires_a_directory(tmp_path):
    from ediaad.markets.custom import CsvSource

    with pytest.raises(ConfigError, match="CSV"):
        CsvSource().fetch("BTCUSDT", "1h")


def test_csv_fetch_accepts_a_per_call_directory(tmp_path):
    from ediaad.markets.custom import CsvSource

    root = tmp_path / "elsewhere"
    write_csv_at(root, "2330", "1d", build_rows(total=3))

    frame = CsvSource().fetch("2330", "1d", root=root)

    assert len(frame) == 3


@pytest.mark.parametrize(
    "corrupt",
    [
        pytest.param(lambda frame: frame.drop(columns=["close"]), id="缺必要欄位"),
        pytest.param(lambda frame: None, id="空檔案"),
        pytest.param(
            lambda frame: frame.assign(close=["abc"] * len(frame)), id="非數值收盤價"
        ),
        pytest.param(
            lambda frame: frame.assign(time=["not-a-time"] * len(frame)), id="時間無法解析"
        ),
        pytest.param(
            lambda frame: pd.concat([frame, frame.iloc[[0]]]), id="重複時間戳"
        ),
    ],
)
def test_csv_fetch_reproduces_load_csv_errors_verbatim(tmp_path, corrupt):
    """壞輸入必須得到與 `load_csv` 逐字相同的錯誤——證明沒有第二套解析。"""
    from ediaad.markets.custom import CsvSource

    root = tmp_path / "ohlcv"
    frame = build_rows()
    corrupted = corrupt(frame)
    path = root / "BTCUSDT_1h.csv"
    root.mkdir(parents=True, exist_ok=True)
    if corrupted is None:
        path.write_text("", encoding="utf-8")
    else:
        corrupted.to_csv(path, index=False)

    with pytest.raises(DataFormatError) as direct:
        load_csv(path)
    with pytest.raises(DataFormatError) as through_source:
        CsvSource(root).fetch("BTCUSDT", "1h")

    assert str(through_source.value) == str(direct.value)


def test_csv_search_returns_nothing_for_an_empty_query(tmp_path):
    from ediaad.markets.custom import CsvSource

    source = CsvSource(tmp_path)

    assert source.search("") == []
    assert source.search("   ") == []
    assert source.search("", limit=5) == []


def test_csv_search_echoes_the_typed_symbol_as_a_single_instrument(tmp_path):
    from ediaad.markets.custom import CsvSource

    source = CsvSource(tmp_path)

    results = source.search("  BTCUSDT  ")

    assert len(results) == 1
    assert results[0].symbol == "BTCUSDT"
    assert results[0].source_id == "csv"
    assert results[0].display_name == "BTCUSDT"
    assert results[0].interval == "", "自訂 CSV 沒有預設週期，由使用者選擇"


def test_csv_search_respects_the_limit(tmp_path):
    from ediaad.markets.custom import CsvSource

    source = CsvSource(tmp_path)

    assert source.search("BTCUSDT", limit=0) == []
    assert source.search("BTCUSDT", limit=-1) == []
    assert len(source.search("BTCUSDT", limit=20)) == 1


# ---- AC-030：設定驗證改依來源查詢週期（不再有全域常數） ----------------------


def write_monitor_config(tmp_path: Path, instruments: list[dict]) -> Path:
    payload = {
        "poll_interval_seconds": 60,
        "events_path": str(tmp_path / "events.jsonl"),
        "cache_dir": str(tmp_path / "ohlcv"),
        "pattern_id": "range_fakeout_reversion",
        "pattern_spec": None,
        "horizon": 3,
        "instruments": instruments,
    }
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_monitor_no_longer_exposes_a_global_interval_allowlist():
    from ediaad import monitor

    assert not hasattr(monitor, "ALLOWED_INTERVALS"), (
        "AC-030 要求廢除全域 ALLOWED_INTERVALS；週期只能由各來源宣告"
    )


def test_monitor_instrument_is_the_markets_instrument():
    from ediaad import monitor
    from ediaad.markets import base

    assert monitor.Instrument is base.Instrument


def test_load_config_validates_the_interval_against_the_named_source(
    tmp_path, with_fake_daily_source
):
    from ediaad.monitor import load_config

    watchlist = load_config(
        write_monitor_config(
            tmp_path,
            [{"symbol": "2330", "interval": "1d", "source_id": "fake_daily"}],
        )
    )

    assert watchlist.instruments[0].symbol == "2330"
    assert watchlist.instruments[0].source_id == "fake_daily"


def test_load_config_rejects_an_interval_the_named_source_does_not_support(
    tmp_path, with_fake_daily_source
):
    from ediaad.monitor import load_config

    with pytest.raises(ConfigError) as excinfo:
        load_config(
            write_monitor_config(
                tmp_path,
                [{"symbol": "2330", "interval": "1h", "source_id": "fake_daily"}],
            )
        )

    message = str(excinfo.value)
    assert "instruments[0]" in message, "訊息必須指出出錯的索引位置"
    assert "fake_daily" in message, "訊息必須指出出錯的來源"
    assert "1h" in message, "訊息必須指出出錯的週期"
    assert "1d" in message, "訊息必須列出該來源可用的週期"


def test_the_same_interval_is_accepted_by_a_source_that_declares_it(
    tmp_path, with_fake_daily_source
):
    """同一個 `1h`：日線來源拒收、csv 接受——證明週期不是全域清單。"""
    from ediaad.monitor import load_config

    watchlist = load_config(
        write_monitor_config(
            tmp_path, [{"symbol": "BTCUSDT", "interval": "1h", "source_id": "csv"}]
        )
    )

    assert watchlist.instruments[0].interval == "1h"
    assert watchlist.instruments[0].source_id == "csv"


def test_load_config_reports_an_unknown_source_id(tmp_path):
    from ediaad.monitor import load_config

    with pytest.raises(ConfigError) as excinfo:
        load_config(
            write_monitor_config(
                tmp_path, [{"symbol": "X", "interval": "1d", "source_id": "nope"}]
            )
        )

    message = str(excinfo.value)
    assert "instruments[0]" in message
    assert "nope" in message
    assert "csv" in message


def test_an_instrument_without_a_source_uses_the_default_source(tmp_path):
    from ediaad.markets.base import DEFAULT_SOURCE_ID
    from ediaad.monitor import load_config

    watchlist = load_config(
        write_monitor_config(tmp_path, [{"symbol": "BTCUSDT", "interval": "1h"}])
    )

    assert DEFAULT_SOURCE_ID == "csv"
    assert watchlist.instruments[0].source_id == "csv"


def test_an_instrument_with_an_empty_source_falls_back_to_the_default(tmp_path):
    from ediaad.monitor import load_config

    watchlist = load_config(
        write_monitor_config(
            tmp_path, [{"symbol": "BTCUSDT", "interval": "1h", "source_id": ""}]
        )
    )

    assert watchlist.instruments[0].source_id == "csv"


# ---- 補測：registry 的結構驗證與 source_id 型別 ------------------------------


def _malformed_source(**overrides):
    attributes = {
        "id": "malformed",
        "display_name": "壞來源",
        "supported_intervals": ("1d",),
        "needs_api_key": False,
        "search": lambda query, limit=20: [],
        "fetch": lambda symbol, interval: None,
    }
    attributes.update(overrides)
    return type("MalformedSource", (), attributes)()


@pytest.mark.parametrize(
    ("overrides", "mentions"),
    [
        pytest.param({"id": ""}, "id", id="id 為空字串"),
        pytest.param({"id": 7}, "id", id="id 非字串"),
        pytest.param({"display_name": ""}, "display_name", id="display_name 為空"),
        pytest.param({"supported_intervals": ()}, "supported_intervals", id="週期清單為空"),
        pytest.param({"supported_intervals": "1d"}, "supported_intervals", id="週期為字串"),
        pytest.param({"supported_intervals": ("1d", "")}, "supported_intervals", id="週期含空字串"),
        pytest.param({"needs_api_key": "no"}, "needs_api_key", id="needs_api_key 非布林"),
        pytest.param({"search": None}, "search", id="search 不可呼叫"),
        pytest.param({"fetch": None}, "fetch", id="fetch 不可呼叫"),
    ],
)
def test_register_rejects_a_malformed_source(overrides, mentions):
    with pytest.raises(ConfigError, match=mentions):
        register(_malformed_source(**overrides))

    assert "malformed" not in [source.id for source in all_sources()], (
        "驗證失敗的來源不得進入 registry"
    )


def test_load_config_rejects_a_non_string_source_id(tmp_path):
    from ediaad.monitor import load_config

    with pytest.raises(ConfigError, match=r"instruments\[0\]"):
        load_config(
            write_monitor_config(
                tmp_path, [{"symbol": "X", "interval": "1d", "source_id": 7}]
            )
        )


def test_csv_fetch_respects_the_limit_like_the_other_sources(tmp_path):
    from ediaad.markets.custom import CsvSource

    root = tmp_path / "ohlcv"
    write_csv_at(root, "BTCUSDT", "1h", build_rows(total=6))

    series = CsvSource(root).fetch("BTCUSDT", "1h", limit=2)

    assert len(series) == 2, "limit 取最近 N 根（與 Binance／TWSE 一致）"
    assert str(series["time"].dtype) == "datetime64[ns, UTC]"


def test_csv_fetch_without_a_limit_returns_everything(tmp_path):
    from ediaad.markets.custom import CsvSource

    root = tmp_path / "ohlcv"
    write_csv_at(root, "BTCUSDT", "1h", build_rows(total=6))

    assert len(CsvSource(root).fetch("BTCUSDT", "1h")) == 6
