"""`ediaad.monitor` 的公開契約測試（TASK-010）。

觀察邊界：只呼叫 `ediaad.monitor.load_config`／`run_once`／`run_forever`／`format_alert`／
`append_event`／`event_times`，並觀察 `Watchlist`／`RunResult`、`emit` 的呼叫內容、
`warn` 的訊息與事件檔內容；`fetch`／`emit`／`warn`／`sleep`／`should_stop` 全部以
測試替身注入。所有測試離線可跑，時間與資料完全可控。
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from ediaad.errors import ConfigError, SourceError
from ediaad.monitor import (
    AlertState,
    Instrument,
    Watchlist,
    append_event,
    event_times,
    format_alert,
    load_config,
    run_forever,
    run_once,
)
from ediaad.patterns import NAMED_PATTERNS, PatternSpec, detect

VALID_CONFIG = {
    "poll_interval_seconds": 60,
    "events_path": ".cache/events.jsonl",
    "cache_dir": ".cache/ohlcv",
    "pattern_id": "range_fakeout_reversion",
    "pattern_spec": None,
    "horizon": 20,
    "instruments": [{"symbol": "BTCUSDT", "interval": "1h"}],
}


def write_config(tmp_path, overrides: dict | None = None, *, drop: str | None = None):
    payload = dict(VALID_CONFIG)
    if overrides:
        payload.update(overrides)
    if drop:
        payload.pop(drop, None)
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# ---- AC-022：設定載入與驗證 -------------------------------------------------


def test_load_config_returns_watchlist_with_the_configured_instrument(tmp_path):
    watchlist = load_config(write_config(tmp_path))

    assert isinstance(watchlist, Watchlist)
    assert watchlist.poll_interval_seconds == 60
    assert watchlist.horizon == 20
    assert len(watchlist.instruments) == 1
    instrument = watchlist.instruments[0]
    assert isinstance(instrument, Instrument)
    assert instrument.symbol == "BTCUSDT"
    assert instrument.interval == "1h"


def test_load_config_accepts_an_explicit_pattern_spec(tmp_path):
    spec_payload = dict(NAMED_PATTERNS["range_fakeout_reversion"])

    watchlist = load_config(write_config(tmp_path, {"pattern_spec": spec_payload}))

    assert isinstance(watchlist.pattern_spec, PatternSpec)
    assert watchlist.pattern_spec.pattern_id == watchlist.pattern_id


def test_load_config_rejects_a_missing_key(tmp_path):
    with pytest.raises(ConfigError, match="horizon"):
        load_config(write_config(tmp_path, drop="horizon"))


def test_load_config_rejects_an_unknown_key(tmp_path):
    with pytest.raises(ConfigError, match="unexpected_key"):
        load_config(write_config(tmp_path, {"unexpected_key": 1}))


def test_load_config_rejects_a_wrong_type(tmp_path):
    with pytest.raises(ConfigError, match="poll_interval_seconds"):
        load_config(write_config(tmp_path, {"poll_interval_seconds": "60"}))


def test_load_config_rejects_empty_instruments(tmp_path):
    with pytest.raises(ConfigError, match="instruments"):
        load_config(write_config(tmp_path, {"instruments": []}))


def test_load_config_rejects_an_unsupported_interval_with_the_index(tmp_path):
    with pytest.raises(ConfigError, match=r"instruments\[0\]"):
        load_config(
            write_config(
                tmp_path, {"instruments": [{"symbol": "BTCUSDT", "interval": "2h"}]}
            )
        )


def test_load_config_rejects_a_pattern_spec_with_a_different_identity(tmp_path):
    spec_payload = dict(NAMED_PATTERNS["range_fakeout_reversion"])
    spec_payload["pattern_id"] = "some_other_pattern"

    with pytest.raises(ConfigError, match="pattern_id"):
        load_config(write_config(tmp_path, {"pattern_spec": spec_payload}))


# 全域 ALLOWED_INTERVALS 已於 TASK-012 依 AC-030 廢除；週期改由各來源的
# supported_intervals 決定，對應測試移至 tests/test_markets_base.py。


# ---- 監控用夾具 -------------------------------------------------------------

MONITOR_SPEC = PatternSpec(
    pattern_id="range_fakeout_reversion",
    range_bars_min=5,
    range_bars_max=20,
    band_atr_multiple_max=3.0,
    atr_period=14,
    breakdown_bars_max=2,
    breakdown_depth_band_min=0.2,
    breakdown_depth_band_max=1.5,
    recovery_bars_max=5,
    recovery_target="range_mean",
)

RANGE_BARS = 12


def build_series_with_pattern(*, offset: int, total: int = 80) -> pd.DataFrame:
    """在 `offset` 處植入一段完整結構；`offset - 1` 的深谷用來界定盤整起點。"""
    closes = [100.0] * total
    highs = [101.0] * total
    lows = [99.0] * total

    lows[offset - 1] = 90.0  # 深谷：讓盤整區間無法往前延伸

    for step in range(RANGE_BARS):
        base = 100.0 if step % 2 == 0 else 100.4
        closes[offset + step] = base
        highs[offset + step] = base + 1.0
        lows[offset + step] = base - 1.0

    breakdown = offset + RANGE_BARS
    closes[breakdown] = 98.5
    highs[breakdown] = 99.5
    lows[breakdown] = 97.0

    recovery = breakdown + 1
    closes[recovery] = 100.5
    highs[recovery] = 101.0
    lows[recovery] = 99.5

    times = pd.date_range("2024-01-01T00:00:00Z", periods=total, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "time": times,
            "open": [value - 0.1 for value in closes],
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [10.0] * total,
        }
    )


def build_watchlist(tmp_path, *, instruments=(("BTCUSDT", "1h"),)) -> Watchlist:
    from ediaad.monitor import Instrument as _Instrument

    return Watchlist(
        poll_interval_seconds=60,
        events_path=str(tmp_path / "events.jsonl"),
        cache_dir=str(tmp_path / "ohlcv"),
        pattern_id=MONITOR_SPEC.pattern_id,
        pattern_spec=MONITOR_SPEC,
        horizon=3,
        instruments=tuple(_Instrument(symbol, interval) for symbol, interval in instruments),
    )


class Recorder:
    """收集 emit／warn 的呼叫內容。"""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict]] = []
        self.warnings: list[str] = []

    def emit(self, line, payload) -> None:
        self.emitted.append((line, dict(payload)))

    def warn(self, message: str) -> None:
        self.warnings.append(message)


# ---- AC-023：三輪輪詢的提醒去重 ---------------------------------------------


def test_event_times_returns_start_and_recovery_times():
    series = build_series_with_pattern(offset=10)
    event = detect(series, MONITOR_SPEC)[0]

    start, end = event_times(event, series)

    assert start == series["time"].iloc[event.range_start_index]
    assert end == series["time"].iloc[event.recovery_index]


def test_three_rounds_alert_once_zero_once_for_the_same_then_a_new_event(tmp_path):
    watchlist = build_watchlist(tmp_path)
    recorder = Recorder()
    state = AlertState()
    first = build_series_with_pattern(offset=10)
    third = build_series_with_pattern(offset=40)
    rounds = [first, first, third]

    holder = {"series": first}

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        return holder["series"]

    results = []
    for series in rounds:
        holder["series"] = series
        results.append(
            run_once(watchlist, fetch, recorder.emit, recorder.warn, state=state)
        )

    assert [result.alerted for result in results] == [1, 0, 1]
    assert [result.processed for result in results] == [1, 1, 1]


def test_dedup_key_is_symbol_interval_pattern_and_event_start_time(tmp_path):
    watchlist = build_watchlist(tmp_path)
    recorder = Recorder()
    state = AlertState()
    series = build_series_with_pattern(offset=10)
    event = detect(series, MONITOR_SPEC)[0]

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        return series

    run_once(watchlist, fetch, recorder.emit, recorder.warn, state=state)

    expected_start = series["time"].iloc[event.range_start_index].isoformat()
    assert state.seen == {("BTCUSDT", "1h", MONITOR_SPEC.pattern_id, expected_start)}
    _, payload = recorder.emitted[0]
    assert payload["event_start_time"] == expected_start


# ---- AC-024：錯誤隔離與程式錯誤上拋 -----------------------------------------

TWO_INSTRUMENTS = (("BTCUSDT", "1h"), ("ETHUSDT", "1h"))


def test_one_instrument_failure_does_not_stop_the_others(tmp_path):
    watchlist = build_watchlist(tmp_path, instruments=TWO_INSTRUMENTS)
    recorder = Recorder()
    series = build_series_with_pattern(offset=10)

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        if symbol == "BTCUSDT":
            raise SourceError("交易所暫時無法連線")
        return series

    result = run_once(watchlist, fetch, recorder.emit, recorder.warn)

    assert result.processed == 1
    assert result.alerted == 1
    assert result.skipped == 0
    assert result.warnings == 1
    # 失敗的商品計入 warning、成功的商品計入 processed：兩者相加等於商品數
    assert result.processed + result.warnings == len(watchlist.instruments)
    assert any("BTCUSDT" in message for message in recorder.warnings)
    assert len(recorder.emitted) == 1
    assert recorder.emitted[0][1]["symbol"] == "ETHUSDT"


def test_malformed_source_frame_is_isolated_as_a_warning(tmp_path):
    """來源轉接器回傳畸形資料框架（KeyError）時只記 warning。"""
    watchlist = build_watchlist(tmp_path, instruments=TWO_INSTRUMENTS)
    recorder = Recorder()
    series = build_series_with_pattern(offset=10)

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        if symbol == "BTCUSDT":
            return series.drop(columns=["close"])
        return series

    result = run_once(watchlist, fetch, recorder.emit, recorder.warn)

    assert result.warnings == 1
    assert result.alerted == 1
    assert any("BTCUSDT" in message for message in recorder.warnings)


def test_programming_errors_are_not_swallowed(tmp_path):
    """非領域錯誤（程式缺陷）必須向上拋出，不得被當成 warning 吞掉。"""
    watchlist = build_watchlist(tmp_path, instruments=TWO_INSTRUMENTS)
    recorder = Recorder()

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        raise ValueError("程式缺陷")

    with pytest.raises(ValueError, match="程式缺陷"):
        run_once(watchlist, fetch, recorder.emit, recorder.warn)


# ---- AC-025：資料不足與「評估後無命中」必須區分（F-003） -------------------


def build_flat_series(bars: int = 80) -> pd.DataFrame:
    times = pd.date_range("2024-01-01T00:00:00Z", periods=bars, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "time": times,
            "open": [99.9] * bars,
            "high": [101.0] * bars,
            "low": [99.0] * bars,
            "close": [100.0] * bars,
            "volume": [10.0] * bars,
        }
    )


def test_insufficient_data_is_skipped_with_a_warning(tmp_path):
    watchlist = build_watchlist(tmp_path)
    recorder = Recorder()
    too_short = build_flat_series(MONITOR_SPEC.range_bars_min)  # 剛好少一根

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        return too_short

    result = run_once(watchlist, fetch, recorder.emit, recorder.warn)

    assert result.skipped == 1
    assert result.processed == 0
    assert result.alerted == 0
    assert result.warnings == 1
    assert any("資料不足" in message for message in recorder.warnings)
    assert recorder.emitted == []


def test_no_hit_is_processed_and_not_counted_as_skipped(tmp_path):
    """對照組：長度足夠但沒有命中時，商品算「已評估」而非「資料不足」。"""
    watchlist = build_watchlist(tmp_path)
    recorder = Recorder()
    quiet = build_flat_series(80)

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        return quiet

    result = run_once(watchlist, fetch, recorder.emit, recorder.warn)

    assert result.processed == 1
    assert result.skipped == 0
    assert result.alerted == 0
    assert result.warnings == 0


def test_the_boundary_length_is_evaluated(tmp_path):
    """邊界：長度剛好等於 `range_bars_min + 1` 時必須被評估（不是資料不足）。"""
    watchlist = build_watchlist(tmp_path)
    recorder = Recorder()
    boundary = build_flat_series(MONITOR_SPEC.range_bars_min + 1)

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        return boundary

    result = run_once(watchlist, fetch, recorder.emit, recorder.warn)

    assert result.processed == 1
    assert result.skipped == 0
    assert result.warnings == 0


def test_short_and_long_instruments_are_counted_separately(tmp_path):
    watchlist = build_watchlist(tmp_path, instruments=TWO_INSTRUMENTS)
    recorder = Recorder()

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        return build_flat_series(5 if symbol == "BTCUSDT" else 80)

    result = run_once(watchlist, fetch, recorder.emit, recorder.warn)

    assert result.skipped == 1
    assert result.processed == 1
    assert result.warnings == 1
    assert result.processed + result.skipped + 0 == len(watchlist.instruments)


# ---- AC-026：提醒輸出格式與 JSONL 附加寫入 ---------------------------------

EVENT_FIELDS = (
    "symbol",
    "interval",
    "pattern_id",
    "event_start_time",
    "event_end_time",
    "confidence",
    "detected_at",
    "history_up_probability",
    "history_samples",
)


def sample_payload(**overrides) -> dict:
    payload = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "pattern_id": "range_fakeout_reversion",
        "event_start_time": "2024-01-01T10:00:00+00:00",
        "event_end_time": "2024-01-01T11:00:00+00:00",
        "confidence": 0.791452991452991,
        "detected_at": "2024-01-01T12:00:00+00:00",
        "history_up_probability": 0.6,
        "history_samples": 5,
    }
    payload.update(overrides)
    return payload


def test_format_alert_is_one_line_with_the_documented_field_order():
    line = format_alert(
        symbol="BTCUSDT",
        interval="1h",
        pattern_id="range_fakeout_reversion",
        start_time=pd.Timestamp("2024-01-01T10:00:00Z"),
        end_time=pd.Timestamp("2024-01-01T11:00:00Z"),
        confidence=0.791452991452991,
        up_probability=0.6,
        samples=5,
    )

    assert "\n" not in line
    assert line == (
        "[ALERT] BTCUSDT 1h range_fakeout_reversion "
        "2024-01-01T10:00:00+00:00..2024-01-01T11:00:00+00:00 "
        "confidence=0.7915 history_up_prob=0.6000 samples=5"
    )


def test_format_alert_marks_missing_history_with_a_dash():
    line = format_alert(
        symbol="ETHUSDT",
        interval="4h",
        pattern_id="range_fakeout_reversion",
        start_time=pd.Timestamp("2024-01-01T10:00:00Z"),
        end_time=pd.Timestamp("2024-01-01T11:00:00Z"),
        confidence=0.5,
        up_probability=None,
        samples=0,
    )

    assert line.endswith("confidence=0.5000 history_up_prob=- samples=0")


def test_append_event_writes_one_json_object_with_nine_fields_per_line(tmp_path):
    path = tmp_path / "nested" / "events.jsonl"

    append_event(path, sample_payload())
    append_event(path, sample_payload(symbol="ETHUSDT"))
    append_event(path, sample_payload(symbol="SOLUSDT"))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    for line in lines:
        payload = json.loads(line)
        assert tuple(sorted(payload)) == tuple(sorted(EVENT_FIELDS))


def test_append_event_never_rewrites_existing_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    append_event(path, sample_payload())
    first_line = path.read_text(encoding="utf-8").splitlines()[0]

    append_event(path, sample_payload(symbol="ETHUSDT"))
    append_event(path, sample_payload(symbol="SOLUSDT"))

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == first_line
    assert len(lines) == 3


def test_run_once_payload_carries_all_nine_event_fields(tmp_path):
    watchlist = build_watchlist(tmp_path)
    recorder = Recorder()
    series = build_series_with_pattern(offset=10)

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        return series

    run_once(
        watchlist,
        fetch,
        recorder.emit,
        recorder.warn,
        now=lambda: pd.Timestamp("2024-01-02T00:00:00Z"),
    )

    _, payload = recorder.emitted[0]
    assert tuple(sorted(payload)) == tuple(sorted(EVENT_FIELDS))
    assert payload["detected_at"] == "2024-01-02T00:00:00+00:00"
    assert payload["symbol"] == "BTCUSDT"
    assert payload["interval"] == "1h"
    # 事件在序列中段（recovery 索引 23、horizon 3、共 80 根）→ 後續走勢足夠，1 個樣本
    assert payload["history_samples"] == 1
    assert payload["history_up_probability"] is not None


def test_run_forever_loops_until_should_stop(tmp_path):
    watchlist = build_watchlist(tmp_path)
    recorder = Recorder()
    series = build_series_with_pattern(offset=10)
    sleeps: list[int] = []
    checks = {"count": 0}

    def should_stop() -> bool:
        checks["count"] += 1
        return checks["count"] > 2

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        return series

    run_forever(
        watchlist,
        fetch,
        recorder.emit,
        recorder.warn,
        sleep=sleeps.append,
        should_stop=should_stop,
    )

    assert sleeps == [watchlist.poll_interval_seconds] * 2
    assert len(recorder.emitted) == 1  # 第二輪同一事件已被去重
