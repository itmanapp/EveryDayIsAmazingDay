"""`ediaad.patterns.learn` 的公開契約測試（TASK-009）。

觀察邊界：只呼叫 `ediaad.patterns.learn`，再把回傳的 `PatternSpec` 交給
`ediaad.patterns.detect`／`to_json`／`atr` 觀察結果；不檢視門檻階梯或內部變數。

**夾具**：14 根範例——索引 0..11 為盤整區間（12 根；close 交錯 100.0／100.4、
high=+1.0、low=−1.0 → band 2.4、區間低點 99.0、均值 100.2），索引 12 跌破
（low 97.0），索引 13 回歸（close 100.5）。因此可推得：盤整 12 根、深度
2.0／2.4 = 0.8333、回歸 1 根。所有測試離線可跑。
"""

from __future__ import annotations

import pandas as pd
import pytest

from ediaad.errors import ConfigError
from ediaad.patterns import PatternSpec, atr, detect, learn, to_json

RANGE_BARS = 12
BREAKDOWN_INDEX = 12
RECOVERY_INDEX = 13
SAMPLE_BARS = 14

EXPECTED_BAND = 2.4
EXPECTED_DEPTH = (99.0 - 97.0) / EXPECTED_BAND
EXPECTED_RECOVERY_BARS = RECOVERY_INDEX - BREAKDOWN_INDEX


def build_series(high, low, close) -> pd.DataFrame:
    times = pd.date_range("2024-01-01T00:00:00Z", periods=len(close), freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "time": times,
            "open": [value - 0.1 for value in close],
            "high": [float(value) for value in high],
            "low": [float(value) for value in low],
            "close": [float(value) for value in close],
            "volume": [10.0] * len(close),
        }
    )


def build_sample(*, range_bars: int = RANGE_BARS, tail_low: bool = False) -> pd.DataFrame:
    """依已知參數合成範例；`tail_low=True` 時回歸根的收盤仍低於均值。"""
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    for index in range(range_bars):
        base = 100.0 if index % 2 == 0 else 100.4
        closes.append(base)
        highs.append(base + 1.0)
        lows.append(base - 1.0)

    closes.append(98.5)
    highs.append(99.5)
    lows.append(97.0)

    closes.append(98.0 if tail_low else 100.5)
    highs.append(101.0 if not tail_low else 99.0)
    lows.append(99.5 if not tail_low else 97.5)

    return build_series(highs, lows, closes)


def build_flat_sample(bars: int = SAMPLE_BARS) -> pd.DataFrame:
    return build_series([101.0] * bars, [99.0] * bars, [100.0] * bars)


# ---- AC-021：推估結果可用、落在容差內、可命中範例自身 -----------------------


def test_learn_returns_a_pattern_spec():
    spec = learn(build_sample())

    assert isinstance(spec, PatternSpec)
    assert spec.pattern_id  # 必須有識別名
    assert to_json(spec)  # 必須可序列化


def test_learned_spec_hits_its_own_sample():
    sample = build_sample()

    spec = learn(sample)
    events = detect(sample, spec)

    assert events, "推估出的規格必須能命中自己的範例"
    event = events[0]
    assert event.breakdown_index == BREAKDOWN_INDEX
    assert event.recovery_index == RECOVERY_INDEX


def test_learned_spec_range_phase_covers_the_planted_range():
    sample = build_sample()

    spec = learn(sample)
    event = detect(sample, spec)[0]

    assert event.range_start_index <= 0 + 1
    assert event.range_end_index >= RANGE_BARS - 2
    assert spec.range_bars_min <= RANGE_BARS <= spec.range_bars_max


def test_learned_tolerances_follow_the_documented_formulas():
    sample = build_sample()

    spec = learn(sample)

    assert spec.range_bars_min == round(RANGE_BARS * 0.5)
    assert spec.range_bars_max == round(RANGE_BARS * 1.5)
    assert spec.recovery_bars_max == EXPECTED_RECOVERY_BARS + 2
    assert spec.breakdown_depth_band_min == pytest.approx(
        max(0.05, EXPECTED_DEPTH * 0.7)
    )
    assert spec.breakdown_depth_band_max == pytest.approx(
        min(3.0, EXPECTED_DEPTH * 1.3)
    )
    assert 1.0 <= spec.band_atr_multiple_max <= 6.0
    assert spec.breakdown_depth_band_min <= EXPECTED_DEPTH <= spec.breakdown_depth_band_max


def test_learned_band_multiple_is_derived_from_the_measured_band_and_atr():
    sample = build_sample()

    spec = learn(sample)
    atr_values = atr(sample, spec.atr_period)

    measured = EXPECTED_BAND / float(atr_values.iloc[RANGE_BARS - 1])
    assert spec.band_atr_multiple_max == pytest.approx(
        min(6.0, max(1.0, measured * 1.2))
    )


def test_learn_uses_an_atr_period_that_is_defined_at_the_range_end():
    sample = build_sample()

    spec = learn(sample)

    assert spec.atr_period >= 1
    assert spec.atr_period <= RANGE_BARS  # 使 ATR[range_end] 有定義
    assert not pd.isna(atr(sample, spec.atr_period).iloc[RANGE_BARS - 1])


def test_learn_is_deterministic_for_the_same_sample():
    sample = build_sample()

    assert to_json(learn(sample)) == to_json(learn(sample))


# ---- AC-021：無法推估時必須報錯且不回傳隨意參數 ----------------------------


def test_too_short_sample_is_rejected():
    short = build_sample(range_bars=9)  # 9 + 跌破 + 回歸 = 11 根

    with pytest.raises(ConfigError, match="至少需要"):
        learn(short)


def test_sample_without_a_phase_after_the_range_is_rejected():
    with pytest.raises(ConfigError, match="盤整區間之後"):
        learn(build_flat_sample())


def test_monotonic_rise_is_rejected_because_nothing_breaks_the_range_floor():
    bars = 14
    closes = [100.0 + index * 2.0 for index in range(bars)]
    climbing = build_series(
        [value + 1.0 for value in closes], [value - 1.0 for value in closes], closes
    )

    with pytest.raises(ConfigError, match="未低於區間下緣"):
        learn(climbing)


def test_sample_without_recovery_is_rejected():
    with pytest.raises(ConfigError, match="回歸相位"):
        learn(build_sample(tail_low=True))


def test_minimum_length_sample_with_a_complete_structure_is_learnable():
    """邊界：剛好 12 根（10 根盤整 + 跌破 + 回歸）必須可以推估。"""
    sample = build_sample(range_bars=10)

    assert len(sample) == 12
    spec = learn(sample)

    assert spec.range_bars_min == round(10 * 0.5)
    assert spec.range_bars_max == round(10 * 1.5)
    assert detect(sample, spec), "12 根的完整結構必須能被自己的規格命中"
