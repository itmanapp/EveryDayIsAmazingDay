"""Twelve Data 來源與金鑰存放隔離（TASK-016）。

觀察邊界：`get_source("twelvedata").fetch`／`search` 的例外與回傳值、`load_api_key`／
`save_api_key` 對 `$EDIAAD_HOME/keys.json` 的檔案效果（權限位與內容），以及日誌輸出。
HTTP 一律注入假客戶端，`EDIAAD_HOME` 以 `tmp_path` 取代，全程離線、不需要真實金鑰。
"""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path

import pandas as pd
import pytest

from ediaad.data import SERIES_COLUMNS
from ediaad.errors import ConfigError, SourceError
from ediaad.markets.base import get_source

KEY = "sk-test-0123456789abcdef"
OTHER_KEY = "sk-other-9999999999999999"


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


def write_keys(home: Path, payload) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    path = home / "keys.json"
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def time_series_values(*, count: int = 3, base: float = 100.0, newest_first: bool = True):
    """Twelve Data `time_series` 的 `values`：預設**由新到舊**（真實回應的順序）。"""
    rows = []
    for index in range(count):
        price = base + index
        rows.append(
            {
                "datetime": f"2024-07-{index + 1:02d}",
                "open": f"{price:.2f}",
                "high": f"{price + 1:.2f}",
                "low": f"{price - 1:.2f}",
                "close": f"{price:.2f}",
                "volume": f"{1000 + index}",
            }
        )
    if newest_first:
        rows.reverse()
    return rows


def time_series_payload(values=None, *, status: str = "ok") -> dict:
    return {
        "meta": {
            "symbol": "AAPL",
            "interval": "1day",
            "currency": "USD",
            "exchange": "NASDAQ",
            "type": "Common Stock",
        },
        "values": time_series_values() if values is None else values,
        "status": status,
    }


# ---- AC-036：金鑰的讀取、寫入與隔離 -----------------------------------------


def test_fetch_without_a_key_raises_a_readable_error_with_instructions(tmp_path):
    home = tmp_path / "ediaad"
    home.mkdir()

    with pytest.raises(SourceError) as excinfo:
        get_source("twelvedata").fetch("AAPL", "1d", home=home, client=FakeHttp())

    message = str(excinfo.value)
    assert "keys.json" in message, "訊息必須指出金鑰要填在哪個檔案"
    assert str(home / "keys.json") in message, "訊息必須給出完整路徑"
    assert "twelvedata.com" in message, "訊息必須含申請金鑰的說明"
    assert "twelvedata" in message, "訊息必須指出缺少哪一個來源的金鑰"


def test_load_api_key_returns_the_stored_key(tmp_path):
    from ediaad.markets.us import load_api_key

    write_keys(tmp_path, {"twelvedata": KEY})

    assert load_api_key(tmp_path) == KEY


def test_save_api_key_creates_a_key_file_with_mode_0600(tmp_path):
    from ediaad.markets.us import save_api_key

    home = tmp_path / "ediaad"
    path = save_api_key(home, KEY)

    assert path.name == "keys.json"
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600, "金鑰檔必須只有擁有者可讀寫"
    assert json.loads(path.read_text(encoding="utf-8"))["twelvedata"] == KEY


def test_save_api_key_preserves_other_sources_and_their_mode(tmp_path):
    from ediaad.markets.us import load_api_key, save_api_key

    write_keys(tmp_path, {"some_other_source": OTHER_KEY, "twelvedata": "old"})

    save_api_key(tmp_path, KEY)

    stored = json.loads((tmp_path / "keys.json").read_text(encoding="utf-8"))
    assert stored == {"some_other_source": OTHER_KEY, "twelvedata": KEY}
    assert load_api_key(tmp_path) == KEY
    assert stat.S_IMODE((tmp_path / "keys.json").stat().st_mode) == 0o600


def test_save_api_key_leaves_no_temporary_file(tmp_path):
    from ediaad.markets.us import save_api_key

    save_api_key(tmp_path, KEY)

    assert sorted(item.name for item in tmp_path.iterdir()) == ["keys.json"]


def test_save_api_key_rejects_an_empty_or_non_string_key(tmp_path):
    from ediaad.markets.us import save_api_key

    for bad in ("", "   ", None, 123):
        with pytest.raises(ConfigError, match="金鑰"):
            save_api_key(tmp_path, bad)


def test_save_api_key_does_not_clobber_a_corrupt_file(tmp_path):
    from ediaad.markets.us import save_api_key

    path = write_keys(tmp_path, "{not json")
    before = path.read_bytes()

    with pytest.raises(ConfigError, match="keys.json"):
        save_api_key(tmp_path, KEY)

    assert path.read_bytes() == before, "損毀的檔案不得被覆寫（裡面可能有其他來源的金鑰）"


@pytest.mark.parametrize(
    ("payload", "mentions"),
    [
        pytest.param("{not json", "JSON", id="損毀 JSON"),
        pytest.param({}, "twelvedata", id="沒有 twelvedata 鍵"),
        pytest.param({"twelvedata": ""}, "twelvedata", id="空字串金鑰"),
        pytest.param({"twelvedata": "   "}, "twelvedata", id="空白金鑰"),
        pytest.param({"twelvedata": 12345}, "twelvedata", id="非字串金鑰"),
        pytest.param([1, 2, 3], "物件", id="不是物件"),
    ],
)
def test_load_api_key_reports_bad_files(tmp_path, payload, mentions):
    from ediaad.markets.us import load_api_key

    write_keys(tmp_path, payload)

    with pytest.raises(SourceError, match=mentions):
        load_api_key(tmp_path)


def test_default_home_follows_the_ediaad_home_variable(tmp_path, monkeypatch):
    from ediaad.markets.us import default_home

    monkeypatch.setenv("EDIAAD_HOME", str(tmp_path / "custom"))
    assert default_home() == tmp_path / "custom"

    monkeypatch.delenv("EDIAAD_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))
    assert default_home() == tmp_path / "fake-home" / ".local" / "share" / "ediaad"


def test_an_empty_ediaad_home_falls_back_to_the_default(tmp_path, monkeypatch):
    from ediaad.markets.us import default_home

    monkeypatch.setenv("EDIAAD_HOME", "   ")
    monkeypatch.setenv("HOME", str(tmp_path / "fake-home"))

    assert default_home() == tmp_path / "fake-home" / ".local" / "share" / "ediaad"


def test_fetch_without_a_key_uses_the_default_home(tmp_path, monkeypatch):
    monkeypatch.setenv("EDIAAD_HOME", str(tmp_path / "empty-home"))

    with pytest.raises(SourceError) as excinfo:
        get_source("twelvedata").fetch("AAPL", "1d", client=FakeHttp())

    assert str(tmp_path / "empty-home" / "keys.json") in str(excinfo.value)


def test_the_key_is_redacted_from_error_messages(tmp_path, caplog):
    """客戶端例外常帶著完整 URL（含 apikey=）——外洩到訊息等於外洩到日誌與網頁。"""
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    leaky = RuntimeError(
        f"HTTP 401 for https://api.twelvedata.com/time_series?symbol=AAPL&apikey={KEY}"
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(SourceError) as excinfo:
            get_source("twelvedata").fetch("AAPL", "1d", home=home, client=FakeHttp(error=leaky))

    assert KEY not in str(excinfo.value), "錯誤訊息不得包含金鑰"
    assert "***" in str(excinfo.value), "必須以遮蔽符號取代金鑰"
    assert KEY not in caplog.text, "日誌不得包含金鑰"
    assert excinfo.value.__cause__ is None, (
        "不得以 __cause__ 保留含金鑰的原始例外，否則 traceback 會把金鑰印出來"
    )


# ---- AC-036：有金鑰時的取得與解析 -------------------------------------------


def keyed(home: Path, **kwargs) -> dict:
    write_keys(home, {"twelvedata": KEY})
    return kwargs


def test_fetch_parses_values_into_the_series_contract(tmp_path):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    http = FakeHttp(time_series_payload())

    series = get_source("twelvedata").fetch("AAPL", "1d", home=home, client=http)

    assert list(series.columns) == list(SERIES_COLUMNS)
    assert str(series["time"].dtype) == "datetime64[ns, UTC]"
    for column in ("open", "high", "low", "close", "volume"):
        assert series[column].dtype == "float64", column
    assert http.count == 1
    first = series.iloc[0]
    assert first["time"] == pd.Timestamp("2024-07-01", tz="UTC")
    assert (first["open"], first["high"], first["low"], first["close"]) == (
        100.0,
        101.0,
        99.0,
        100.0,
    )
    assert first["volume"] == pytest.approx(1000.0)


def test_fetch_turns_the_newest_first_response_into_ascending_time(tmp_path):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    assert time_series_values()[0]["datetime"] == "2024-07-03", "假回應必須是由新到舊"

    series = get_source("twelvedata").fetch(
        "AAPL", "1d", home=home, client=FakeHttp(time_series_payload())
    )

    assert [str(stamp.date()) for stamp in series["time"]] == [
        "2024-07-01",
        "2024-07-02",
        "2024-07-03",
    ]
    assert series["time"].is_monotonic_increasing


def test_fetch_sends_the_documented_parameters(tmp_path):
    from ediaad.markets.us import TIME_SERIES_PATH, TWELVE_DATA_URL

    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    http = FakeHttp(time_series_payload())

    get_source("twelvedata").fetch("aapl", "1d", limit=42, home=home, client=http)

    url = http.calls[0]
    assert url.startswith(f"{TWELVE_DATA_URL}{TIME_SERIES_PATH}")
    assert "symbol=AAPL" in url, "商品代號必須正規化為大寫"
    assert "interval=1day" in url
    assert "outputsize=42" in url
    assert f"apikey={KEY}" in url, "請求本身當然要帶金鑰（隔離要求的是不外洩到檔案與日誌）"


@pytest.mark.parametrize(
    ("interval", "remote"),
    [
        ("1m", "1min"),
        ("5m", "5min"),
        ("15m", "15min"),
        ("30m", "30min"),
        ("1h", "1h"),
        ("4h", "4h"),
        ("1d", "1day"),
        ("1w", "1week"),
    ],
)
def test_every_declared_interval_maps_to_a_twelvedata_name(tmp_path, interval, remote):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    http = FakeHttp(time_series_payload())

    get_source("twelvedata").fetch("AAPL", interval, home=home, client=http)

    assert f"interval={remote}" in http.calls[0]


def test_the_declared_intervals_are_exactly_the_mapped_ones():
    from ediaad.markets.us import INTERVAL_MAP

    source = get_source("twelvedata")

    assert source.needs_api_key is True
    assert source.id == "twelvedata"
    assert tuple(source.supported_intervals) == tuple(INTERVAL_MAP)
    assert all(callable(getattr(source, member)) for member in ("search", "fetch"))


def test_fetch_reports_a_rejected_key_readably(tmp_path):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    payload = {"code": 401, "message": "Invalid API key", "status": "error"}

    with pytest.raises(SourceError) as excinfo:
        get_source("twelvedata").fetch("AAPL", "1d", home=home, client=FakeHttp(payload))

    message = str(excinfo.value)
    assert "Invalid API key" in message, "必須保留來源的可讀說明"
    assert KEY not in message


def test_fetch_reports_an_exhausted_quota(tmp_path):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    payload = {
        "code": 429,
        "message": "You have reached the API credits quota for the current minute.",
        "status": "error",
    }

    with pytest.raises(SourceError, match="quota"):
        get_source("twelvedata").fetch("AAPL", "1d", home=home, client=FakeHttp(payload))


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param([], id="不是物件"),
        pytest.param("not json", id="字串"),
        pytest.param({"status": "ok"}, id="缺 values"),
        pytest.param({"status": "ok", "values": "x"}, id="values 不是陣列"),
        pytest.param({"status": "ok", "values": []}, id="values 為空"),
        pytest.param(
            {"status": "ok", "values": [{"datetime": "2024-07-01", "open": "1"}]},
            id="缺必要欄位",
        ),
        pytest.param(
            {"status": "ok", "values": [dict(time_series_values()[0], close="N/A")]},
            id="非數值價格",
        ),
        pytest.param(
            {"status": "ok", "values": [dict(time_series_values()[0], datetime="not-a-date")]},
            id="時間無法解讀",
        ),
    ],
)
def test_a_malformed_response_is_a_readable_source_error(tmp_path, payload):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})

    with pytest.raises(SourceError, match="Twelve Data"):
        get_source("twelvedata").fetch("AAPL", "1d", home=home, client=FakeHttp(payload))


@pytest.mark.parametrize(
    ("kwargs", "mentions"),
    [
        pytest.param({"symbol": ""}, "symbol", id="空商品"),
        pytest.param({"symbol": "  "}, "symbol", id="空白商品"),
        pytest.param({"interval": "2h"}, "2h", id="不支援的週期"),
        pytest.param({"interval": ""}, "interval", id="空週期"),
        pytest.param({"limit": 0}, "limit", id="limit 為 0"),
        pytest.param({"limit": 5001}, "limit", id="limit 超過上限"),
        pytest.param({"limit": True}, "limit", id="limit 為布林"),
    ],
)
def test_invalid_arguments_are_config_errors(tmp_path, kwargs, mentions):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    arguments = {"symbol": "AAPL", "interval": "1d", **kwargs}

    with pytest.raises(ConfigError, match=mentions):
        get_source("twelvedata").fetch(home=home, client=FakeHttp(time_series_payload()), **arguments)


def test_config_errors_happen_before_reading_the_key(tmp_path):
    """參數錯誤不該先抱怨金鑰——否則使用者會被指向錯誤的方向。"""
    with pytest.raises(ConfigError, match="2h"):
        get_source("twelvedata").fetch("AAPL", "2h", home=tmp_path, client=FakeHttp())


def test_fetch_keeps_the_most_recent_rows_up_to_the_limit(tmp_path):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    payload = time_series_payload(time_series_values(count=5))

    series = get_source("twelvedata").fetch("AAPL", "1d", limit=2, home=home, client=FakeHttp(payload))

    assert [str(stamp.date()) for stamp in series["time"]] == ["2024-07-04", "2024-07-05"]


def test_the_key_only_ever_appears_in_keys_json(tmp_path):
    """走完一次完整流程後，除了 `keys.json` 之外任何檔案都不得含金鑰。"""
    from ediaad.markets.us import save_api_key

    home = tmp_path / "ediaad"
    save_api_key(home, KEY)
    watchlist = tmp_path / "watchlist.json"
    watchlist.write_text(
        json.dumps(
            {
                "poll_interval_seconds": 60,
                "events_path": str(tmp_path / "events.jsonl"),
                "cache_dir": str(tmp_path / "ohlcv"),
                "pattern_id": "range_fakeout_reversion",
                "pattern_spec": None,
                "horizon": 3,
                "instruments": [{"symbol": "AAPL", "interval": "1d", "source_id": "twelvedata"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    get_source("twelvedata").fetch("AAPL", "1d", home=home, client=FakeHttp(time_series_payload()))

    assert KEY not in watchlist.read_text(encoding="utf-8"), "watchlist.json 不得含金鑰"
    leaked = [
        path
        for path in [*home.rglob("*"), *tmp_path.rglob("*")]
        if path.is_file() and path.name != "keys.json" and KEY in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert leaked == [], f"金鑰外洩到這些檔案：{leaked}"


# ---- AC-036：商品搜尋（symbol_search） ---------------------------------------


def symbol_search_payload(entries=None, *, status: str = "ok") -> dict:
    return {
        "data": [
            {
                "symbol": "AAPL",
                "instrument_name": "Apple Inc.",
                "exchange": "NASDAQ",
                "instrument_type": "Common Stock",
                "currency": "USD",
            },
            {
                "symbol": "AAPL.MX",
                "instrument_name": "Apple Inc.",
                "exchange": "BMV",
                "instrument_type": "Common Stock",
                "currency": "MXN",
            },
        ]
        if entries is None
        else entries,
        "status": status,
    }


def test_search_requires_a_key(tmp_path):
    with pytest.raises(SourceError) as excinfo:
        get_source("twelvedata").search("AAPL", home=tmp_path / "empty", client=FakeHttp())

    assert "twelvedata.com" in str(excinfo.value)
    assert "keys.json" in str(excinfo.value)


def test_search_returns_instruments_with_display_names(tmp_path):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})

    results = get_source("twelvedata").search("apple", home=home, client=FakeHttp(symbol_search_payload()))

    assert [item.symbol for item in results] == ["AAPL", "AAPL.MX"]
    assert results[0].display_name == "Apple Inc."
    assert results[0].source_id == "twelvedata"
    assert results[0].interval == ""


def test_search_requests_the_symbol_search_endpoint(tmp_path):
    from ediaad.markets.us import SYMBOL_SEARCH_PATH, TWELVE_DATA_URL

    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    http = FakeHttp(symbol_search_payload())

    get_source("twelvedata").search("  apple  ", home=home, client=http)

    assert http.count == 1
    url = http.calls[0]
    assert url.startswith(f"{TWELVE_DATA_URL}{SYMBOL_SEARCH_PATH}")
    assert "symbol=apple" in url
    assert f"apikey={KEY}" in url


def test_search_returns_nothing_for_an_empty_query_without_a_key_or_request(tmp_path):
    http = FakeHttp(symbol_search_payload())

    assert get_source("twelvedata").search("", home=tmp_path / "empty", client=http) == []
    assert get_source("twelvedata").search("   ", home=tmp_path / "empty", client=http) == []
    assert get_source("twelvedata").search("x", limit=0, home=tmp_path / "empty", client=http) == []
    assert http.count == 0


def test_search_respects_the_limit(tmp_path):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    source = get_source("twelvedata")

    assert len(source.search("apple", limit=1, home=home, client=FakeHttp(symbol_search_payload()))) == 1
    assert [
        item.symbol
        for item in source.search("apple", limit=1, home=home, client=FakeHttp(symbol_search_payload()))
    ] == ["AAPL"]


def test_search_reports_an_error_payload(tmp_path):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    payload = {"code": 401, "message": "Invalid API key", "status": "error"}

    with pytest.raises(SourceError) as excinfo:
        get_source("twelvedata").search("apple", home=home, client=FakeHttp(payload))

    assert "Invalid API key" in str(excinfo.value)
    assert KEY not in str(excinfo.value)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param([], id="不是物件"),
        pytest.param({"status": "ok"}, id="缺 data"),
        pytest.param({"status": "ok", "data": "x"}, id="data 不是陣列"),
        pytest.param({"status": "ok", "data": ["x"]}, id="項目不是物件"),
    ],
)
def test_search_reports_malformed_payloads(tmp_path, payload):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})

    with pytest.raises(SourceError, match="Twelve Data"):
        get_source("twelvedata").search("apple", home=home, client=FakeHttp(payload))


def test_search_skips_entries_without_a_symbol_and_falls_back_to_the_symbol_as_name(tmp_path):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    entries = [
        {"instrument_name": "沒有代號"},
        {"symbol": "MSFT"},
        {"symbol": "NVDA", "instrument_name": "NVIDIA Corporation"},
    ]

    results = get_source("twelvedata").search("x", home=home, client=FakeHttp(symbol_search_payload(entries)))

    assert [item.symbol for item in results] == ["MSFT", "NVDA"]
    assert [item.display_name for item in results] == ["MSFT", "NVIDIA Corporation"]


def test_search_redacts_the_key_from_client_errors(tmp_path, caplog):
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    leaky = RuntimeError(f"boom https://api.twelvedata.com/symbol_search?symbol=x&apikey={KEY}")

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(SourceError) as excinfo:
            get_source("twelvedata").search("apple", home=home, client=FakeHttp(error=leaky))

    assert KEY not in str(excinfo.value)
    assert "***" in str(excinfo.value)
    assert KEY not in caplog.text


# ---- 補測：遮蔽與選填欄位 ---------------------------------------------------


def test_error_messages_mask_any_apikey_even_when_it_is_not_our_key(tmp_path):
    """來源端或中間層可能回一個「別的金鑰字串」；一律遮蔽，不依賴已知值比對。"""
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    leaky = RuntimeError("400 for https://api.twelvedata.com/time_series?apikey=rotated-secret&symbol=AAPL")

    with pytest.raises(SourceError) as excinfo:
        get_source("twelvedata").fetch("AAPL", "1d", home=home, client=FakeHttp(error=leaky))

    assert "rotated-secret" not in str(excinfo.value)
    assert "apikey=***" in str(excinfo.value)


def test_a_missing_volume_becomes_zero(tmp_path):
    """指數或外匯沒有成交量；序列契約仍要求 volume 欄位。"""
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    row = {name: value for name, value in time_series_values(count=1)[0].items() if name != "volume"}

    series = get_source("twelvedata").fetch(
        "SPX", "1d", home=home, client=FakeHttp(time_series_payload([row]))
    )

    assert list(series.columns) == list(SERIES_COLUMNS)
    assert series["volume"].iloc[0] == 0.0


def test_error_messages_mask_the_key_even_without_the_apikey_prefix(tmp_path):
    """客戶端或中介層可能用其他寫法提到金鑰（例如「rejected credentials <key>」）。"""
    home = tmp_path / "ediaad"
    write_keys(home, {"twelvedata": KEY})
    leaky = RuntimeError(f"twelvedata: rejected credentials {KEY} (see docs)")

    with pytest.raises(SourceError) as excinfo:
        get_source("twelvedata").fetch("AAPL", "1d", home=home, client=FakeHttp(error=leaky))

    assert KEY not in str(excinfo.value)
    assert "***" in str(excinfo.value)
