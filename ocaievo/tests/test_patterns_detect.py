"""`ediaad.patterns` 的 ATR 與規律偵測器測試（TASK-008）。

觀察邊界：只呼叫 `ediaad.patterns.atr` 與 `ediaad.patterns.detect`，並讀取
`PatternEvent` 與 `PatternSpec`；不檢視二分搜尋、累積和或其他內部結構。

**oracle 的來源**：ATR 期望值以純 Python 四則運算獨立推導（見測試註解）；
偵測器的相位索引則以「依已知參數植入三相位」的合成序列作為 oracle。
所有測試離線可跑，資料為確定性合成序列。
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from ediaad.patterns import PatternEvent, PatternSpec, atr, detect

# ---- ATR 的獨立 oracle ------------------------------------------------------

ATR_HIGH = [10.0, 11.5, 12.0, 11.0, 13.0, 12.5, 14.0, 13.5]
ATR_LOW = [9.0, 10.0, 10.5, 9.5, 11.0, 10.5, 12.0, 11.5]
ATR_CLOSE = [9.5, 11.0, 11.0, 10.0, 12.0, 11.0, 13.0, 12.0]

# TR = [1.0, 2.0, 1.5, 1.5, 3.0, 2.0, 3.0, 2.0]（純 Python 推導）
EXPECTED_ATR = [
    None,
    None,
    1.5,  # mean(TR[0..2]) = (1.0 + 2.0 + 1.5) / 3
    1.6666666666666667,  # mean(TR[1..3])
    2.0,  # mean(TR[2..4])
    2.1666666666666665,  # mean(TR[3..5])
    2.6666666666666665,  # mean(TR[4..6])
    2.3333333333333335,  # mean(TR[5..7])
]


def build_series(high, low, close, volume=10.0) -> pd.DataFrame:
    times = pd.date_range("2024-01-01T00:00:00Z", periods=len(close), freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "time": times,
            "open": [value - 0.1 for value in close],
            "high": [float(value) for value in high],
            "low": [float(value) for value in low],
            "close": [float(value) for value in close],
            "volume": [float(volume)] * len(close),
        }
    )


# ---- AC-016：ATR 的計算與「不引用未來」 -------------------------------------


def test_atr_returns_series_with_nan_warmup():
    series = build_series(ATR_HIGH, ATR_LOW, ATR_CLOSE)

    values = atr(series, 3)

    assert isinstance(values, pd.Series)
    assert len(values) == len(series)
    assert values.iloc[:2].isna().all()
    assert values.iloc[2:].notna().all()


def test_atr_matches_independently_derived_values():
    series = build_series(ATR_HIGH, ATR_LOW, ATR_CLOSE)

    values = atr(series, 3)

    assert values.iloc[0] != values.iloc[0]  # NaN
    assert values.iloc[1] != values.iloc[1]  # NaN
    for index, expected in enumerate(EXPECTED_ATR[2:], start=2):
        assert values.iloc[index] == pytest.approx(expected, abs=1e-12), index


def test_atr_with_period_one_equals_true_range():
    series = build_series(ATR_HIGH, ATR_LOW, ATR_CLOSE)

    values = atr(series, 1)

    assert values.notna().all()
    # TR[0] 以「前一根收盤 = 當根收盤」處理 → high - low
    assert values.iloc[0] == pytest.approx(ATR_HIGH[0] - ATR_LOW[0])
    assert values.iloc[4] == pytest.approx(3.0)  # TR[4] = |13.0 - 10.0|


def test_atr_does_not_look_ahead():
    """把植入點之後的資料乘 10，之前的 ATR 必須完全不變（差異 < 1e-12）。"""
    bars = 40
    closes = [100.0 + (index % 7) * 0.5 for index in range(bars)]
    highs = [value + 1.0 for value in closes]
    lows = [value - 1.0 for value in closes]
    series = build_series(highs, lows, closes)
    pivot = 25

    baseline = atr(series, 14)

    tampered = series.copy()
    for column in ("open", "high", "low", "close"):
        tampered.loc[pivot + 1 :, column] = tampered.loc[pivot + 1 :, column] * 10.0
    after = atr(tampered, 14)

    np.testing.assert_allclose(
        after.iloc[: pivot + 1].to_numpy(dtype=float),
        baseline.iloc[: pivot + 1].to_numpy(dtype=float),
        rtol=0,
        atol=1e-12,
    )
    # 對照：植入點之後的值必須確實改變，否則這個測試沒有辨識力
    assert after.iloc[pivot + 1] != pytest.approx(baseline.iloc[pivot + 1])


# ---- 三相位合成夾具 ---------------------------------------------------------

RANGE_SPEC = PatternSpec(
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

# 夾具設計（長度 80）：0..28 安靜震盪、29 深谷（避免盤整區間往前延伸）、
# 30..49 盤整區間（close 交錯 100.0/100.4、high=+1.0、low=-1.0 → band=2.4、區間低點 99.0、均值 100.2）、
# 50 跌破、之後為 between 與回歸根、再尾端安靜震盪。
RANGE_START, RANGE_END, BREAKDOWN_INDEX = 30, 49, 50
EXPECTED_BAND = 2.4
EXPECTED_RANGE_MEAN = 100.2


def build_pattern_series(
    *,
    breakdown_low: float = 97.0,
    breakdown_close: float = 98.5,
    between: tuple[tuple[float, float], ...] = (),
    recovery_close: float = 100.5,
    recovery_low: float = 99.5,
    tail_bars: int = 22,
) -> pd.DataFrame:
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []

    for index in range(RANGE_END + 1):
        base = 100.0 if index % 2 == 0 else 100.4
        closes.append(base)
        highs.append(base + 1.0)
        lows.append(base - 1.0)
    lows[29] = 90.0  # 深谷：讓盤整區間無法往前延伸到這裡

    closes.append(breakdown_close)
    highs.append(breakdown_close + 1.0)
    lows.append(breakdown_low)

    for low, close in between:
        closes.append(close)
        highs.append(close + 1.0)
        lows.append(low)

    closes.append(recovery_close)
    highs.append(recovery_close + 0.5)
    lows.append(recovery_low)

    for index in range(tail_bars):
        base = 100.0 if index % 2 == 0 else 100.4
        closes.append(base)
        highs.append(base + 1.0)
        lows.append(base - 1.0)

    return build_series(highs, lows, closes)


def average_true_range(series: pd.DataFrame, end_index: int, period: int) -> float:
    """獨立實作（純 Python）的 ATR，僅用於推導信心值期望值。"""
    high = [float(value) for value in series["high"]]
    low = [float(value) for value in series["low"]]
    close = [float(value) for value in series["close"]]
    ranges = []
    for index in range(end_index - period + 1, end_index + 1):
        previous_close = close[index - 1] if index > 0 else close[index]
        ranges.append(
            max(
                high[index] - low[index],
                abs(high[index] - previous_close),
                abs(low[index] - previous_close),
            )
        )
    return sum(ranges) / len(ranges)


# ---- AC-017：三相位命中、欄位定義與信心值 -----------------------------------


def test_event_has_the_nine_documented_fields():
    assert [field for field in PatternEvent.__dataclass_fields__] == [
        "pattern_id",
        "range_start_index",
        "range_end_index",
        "breakdown_index",
        "recovery_index",
        "confidence",
        "band",
        "breakdown_depth",
        "recovery_bars",
    ]


def planted_event(events: list[PatternEvent]) -> PatternEvent:
    """挑出「盤整相位結束於植入位置」的那筆事件。

    此處刻意不要求「恰好一筆」——同一段結構可能被多個長度命中，
    那是 AC-020 的去重契約，於 Cycle 5 驗證。
    """
    matches = [event for event in events if event.range_end_index == RANGE_END]
    assert matches, f"沒有找到盤整相位結束於 {RANGE_END} 的事件：{events}"
    return matches[0]


def test_detect_finds_the_planted_structure_with_correct_phase_indices():
    series = build_pattern_series()

    events = detect(series, RANGE_SPEC)

    event = planted_event(events)
    assert isinstance(event, PatternEvent)
    assert event.pattern_id == RANGE_SPEC.pattern_id
    assert event.range_start_index == RANGE_START
    assert event.range_end_index == RANGE_END
    assert event.breakdown_index == BREAKDOWN_INDEX
    assert event.recovery_index == BREAKDOWN_INDEX + 1


def test_detect_reports_measured_band_depth_and_recovery_bars():
    series = build_pattern_series()

    event = planted_event(detect(series, RANGE_SPEC))

    assert event.band == pytest.approx(EXPECTED_BAND)
    assert event.breakdown_depth == pytest.approx((99.0 - 97.0) / EXPECTED_BAND)
    assert event.recovery_bars == 1


def test_confidence_matches_the_documented_formula_and_is_within_range():
    series = build_pattern_series()
    event = planted_event(detect(series, RANGE_SPEC))

    limit = RANGE_SPEC.band_atr_multiple_max * average_true_range(
        series, RANGE_END, RANGE_SPEC.atr_period
    )
    band_score = 1 - min(event.band / limit, 1)
    midpoint = (
        RANGE_SPEC.breakdown_depth_band_min + RANGE_SPEC.breakdown_depth_band_max
    ) / 2
    half_range = (
        RANGE_SPEC.breakdown_depth_band_max - RANGE_SPEC.breakdown_depth_band_min
    ) / 2
    depth_score = 1 - abs(event.breakdown_depth - midpoint) / half_range
    recovery_score = 1 - event.recovery_bars / RANGE_SPEC.recovery_bars_max
    expected = (band_score + depth_score + recovery_score) / 3

    assert 0.0 <= event.confidence <= 1.0
    assert event.confidence == pytest.approx(expected, abs=1e-12)


def test_empty_result_for_a_series_without_any_structure():
    quiet = build_series(
        [101.0] * 60, [99.0] * 60, [100.0 if index % 2 == 0 else 100.4 for index in range(60)]
    )

    assert detect(quiet, RANGE_SPEC) == []


# ---- AC-018：四種反例防護 ---------------------------------------------------

TOO_SHALLOW_LOW = 98.6  # depth = (99.0 - 98.6) / 2.4 = 0.1667 < 0.2
TOO_DEEP_LOW = 93.0  # depth = (99.0 - 93.0) / 2.4 = 2.5 > 1.5


def test_no_hit_when_breakdown_depth_is_below_the_lower_bound():
    series = build_pattern_series(breakdown_low=TOO_SHALLOW_LOW)

    assert detect(series, RANGE_SPEC) == []


def test_no_hit_when_breakdown_depth_exceeds_the_upper_bound():
    series = build_pattern_series(breakdown_low=TOO_DEEP_LOW)

    assert detect(series, RANGE_SPEC) == []


def test_no_hit_when_a_lower_low_appears_before_the_recovery():
    """反例防護：回歸之前若出現比跌破低點更低的低點，該次跌破不成立。

    夾具說明：中間那根的 low 壓到 88.0（而非略低於 97.0）。原因是若只略低，
    「把原跌破根吸收進盤整區間、再被下一根跌破」會形成**另一個合法結構**
    （深度仍落在區間內），讓這個反例無法只由反例防護決定。壓到 88.0 後，
    該次要結構的深度為 (97-88)/4.4 ≈ 2.05 > 1.5 上限而必然被排除，
    因此零命中只能來自反例防護。
    """
    series = build_pattern_series(between=((88.0, 99.0),))

    assert detect(series, RANGE_SPEC) == []


def test_no_hit_when_the_recovery_comes_too_late():
    series = build_pattern_series(between=((97.5, 99.0),) * 5)

    assert detect(series, RANGE_SPEC) == []


def test_recovery_exactly_at_the_deadline_is_accepted():
    """對照組：回歸恰好落在 `k + recovery_bars_max` 時必須命中（避免把 <= 寫成 <）。"""
    series = build_pattern_series(between=((97.5, 99.0),) * 4)

    events = detect(series, RANGE_SPEC)

    event = planted_event(events)
    assert event.breakdown_index == BREAKDOWN_INDEX
    assert event.recovery_index == BREAKDOWN_INDEX + 5
    assert event.recovery_bars == RANGE_SPEC.recovery_bars_max


def test_breakdown_exactly_at_the_deadline_is_accepted():
    """對照組：跌破恰好落在 `j + breakdown_bars_max` 時必須命中。"""
    series = build_pattern_series(between=(), breakdown_low=97.0)
    # 把區間結束往前挪一格（讓 50 成為 j + 2），仍必須命中
    shifted = series.copy()
    shifted.loc[RANGE_END, ["open", "high", "low", "close"]] = [
        100.0,
        101.0,
        99.0,
        100.0,
    ]

    events = detect(shifted, RANGE_SPEC)

    assert any(
        event.breakdown_index == BREAKDOWN_INDEX for event in events
    ), "跌破恰好落在 j + breakdown_bars_max 時必須命中"


# ---- AC-019：偵測的尺度不變性 -----------------------------------------------

PHASE_FIELDS = ("range_start_index", "range_end_index", "breakdown_index", "recovery_index")


def phase_indices(event: PatternEvent) -> tuple[int, int, int, int]:
    return tuple(getattr(event, name) for name in PHASE_FIELDS)


@pytest.mark.parametrize("factor", [0.01, 0.5, 1000.0])
def test_detect_is_invariant_under_price_scaling(factor):
    series = build_pattern_series()
    baseline = planted_event(detect(series, RANGE_SPEC))

    scaled = series.copy()
    for column in ("open", "high", "low", "close"):
        scaled[column] = scaled[column] * factor

    event = planted_event(detect(scaled, RANGE_SPEC))

    assert phase_indices(event) == phase_indices(baseline)
    assert event.band == pytest.approx(baseline.band * factor)
    assert event.breakdown_depth == pytest.approx(baseline.breakdown_depth)
    assert event.recovery_bars == baseline.recovery_bars
    assert event.confidence == pytest.approx(baseline.confidence, abs=1e-9)


@pytest.mark.parametrize("shift", [7.0, 1000.0, 100000.0])
def test_detect_is_invariant_under_price_translation(shift):
    series = build_pattern_series()
    baseline = planted_event(detect(series, RANGE_SPEC))

    shifted = series.copy()
    for column in ("open", "high", "low", "close"):
        shifted[column] = shifted[column] + shift

    event = planted_event(detect(shifted, RANGE_SPEC))

    assert phase_indices(event) == phase_indices(baseline)
    assert event.band == pytest.approx(baseline.band)
    assert event.breakdown_depth == pytest.approx(baseline.breakdown_depth)
    assert event.confidence == pytest.approx(baseline.confidence, abs=1e-9)


# ---- AC-020：去重（同結構只留最長）與依盤整長度排序 --------------------------


def build_two_structure_series() -> pd.DataFrame:
    """兩段結構：第一段盤整 20 根，第二段因前面的深谷只能盤整 14 根。"""
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []

    def quiet_range(first: int, last: int) -> None:
        for index in range(first, last + 1):
            base = 100.0 if index % 2 == 0 else 100.4
            closes.append(base)
            highs.append(base + 1.0)
            lows.append(base - 1.0)

    def dip(index: int) -> None:
        closes.append(100.0)
        highs.append(101.0)
        lows.append(90.0)

    def breakdown() -> None:
        closes.append(98.5)
        highs.append(99.5)
        lows.append(97.0)

    def recovery() -> None:
        closes.append(100.5)
        highs.append(101.0)
        lows.append(99.5)

    dip(0)
    quiet_range(1, 24)
    breakdown()
    recovery()
    quiet_range(27, 40)
    dip(41)
    quiet_range(42, 55)
    breakdown()
    recovery()
    quiet_range(58, 75)

    return build_series(highs, lows, closes)


def range_length(event: PatternEvent) -> int:
    return event.range_end_index - event.range_start_index + 1


def test_one_structure_is_reported_once_with_the_longest_range():
    series = build_pattern_series()

    events = detect(series, RANGE_SPEC)

    assert len(events) == 1
    event = events[0]
    assert event.range_start_index == RANGE_START
    assert event.range_end_index == RANGE_END
    assert range_length(event) == RANGE_SPEC.range_bars_max


def test_no_two_events_share_the_same_breakdown_and_recovery():
    events = detect(build_two_structure_series(), RANGE_SPEC)

    keys = [(event.breakdown_index, event.recovery_index) for event in events]
    assert len(keys) == len(set(keys))


def test_events_are_sorted_by_range_length_descending():
    events = detect(build_two_structure_series(), RANGE_SPEC)

    lengths = [range_length(event) for event in events]
    assert lengths == sorted(lengths, reverse=True)
    assert lengths == [RANGE_SPEC.range_bars_max, 14]


def build_flat_range_series(*, recovery_close: float) -> pd.DataFrame:
    """平坦盤整（close 全為 100.0）→ 區間均值恰為 100.0，可用浮點精確表示。

    交錯的 100.0／100.4 均值是 100.20000000000002，無法用來測「恰好等於」的邊界。
    """
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    for index in range(80):
        if index == 29:
            closes.append(100.0)
            highs.append(101.0)
            lows.append(90.0)  # 深谷：界定盤整區間起點
        elif index == BREAKDOWN_INDEX:
            closes.append(98.5)
            highs.append(99.5)
            lows.append(97.0)
        elif index == BREAKDOWN_INDEX + 1:
            closes.append(recovery_close)
            highs.append(100.5)
            lows.append(99.5)
        else:
            closes.append(100.0)
            highs.append(101.0)
            lows.append(99.0)
    return build_series(highs, lows, closes)


def test_recovery_exactly_at_the_range_mean_is_accepted():
    """邊界：`close[m] >= mean(close[i..j])` 的「等於」必須算回歸成功。"""
    series = build_flat_range_series(recovery_close=100.0)

    event = planted_event(detect(series, RANGE_SPEC))

    assert event.recovery_index == BREAKDOWN_INDEX + 1
    assert float(series["close"][event.recovery_index]) == 100.0


def test_recovery_just_below_the_range_mean_is_not_a_recovery():
    """對照組：收盤略低於均值時不算回歸（下一個根才回歸）。"""
    series = build_flat_range_series(recovery_close=99.9)
    # 下一根（52）回到 100.0 才會回歸
    series.loc[BREAKDOWN_INDEX + 2, ["open", "high", "low", "close"]] = [
        99.9, 100.5, 99.5, 100.0,
    ]

    event = planted_event(detect(series, RANGE_SPEC))

    assert event.recovery_index == BREAKDOWN_INDEX + 2


def test_breakdown_exactly_at_the_range_floor_is_not_a_breach():
    """邊界：`low[k] < min(low[i..j])` 為嚴格小於，恰好等於不算跌破。"""
    series = build_pattern_series(breakdown_low=99.0, breakdown_close=99.5)

    assert detect(series, RANGE_SPEC) == []


def test_breakdown_requires_a_strictly_lower_low_even_when_zero_depth_is_allowed():
    """`low[k] < min(low[i..j])` 是**嚴格**比較。

    預設規格下「恰好等於區間低點」的深度為 0，會被深度下限擋掉，因此這個邊界
    在預設規格下看不出差異；把深度下限放寬到 0 之後，嚴格比較與 `<=` 才會分道揚鑣。
    """
    loose_spec = dataclasses.replace(RANGE_SPEC, breakdown_depth_band_min=0.0)
    series = build_flat_range_series(recovery_close=100.0)
    series.loc[BREAKDOWN_INDEX, ["open", "high", "low", "close"]] = [
        99.5,
        100.0,
        99.0,  # 恰好等於區間低點，不是跌破
        99.4,
    ]

    assert detect(series, loose_spec) == []
