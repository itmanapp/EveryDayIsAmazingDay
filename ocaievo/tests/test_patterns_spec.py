"""`ediaad.patterns.PatternSpec` 的公開契約測試（TASK-007）。

觀察邊界：只透過 `ediaad.patterns` 的公開名稱建構 `PatternSpec`、呼叫 `to_json`／
`from_json`、讀取 `NAMED_PATTERNS` 與 `RECOVERY_TARGETS`；不呼叫私有驗證函式，也不
斷言 `__post_init__` 的實作細節。全部離線可跑。
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from ediaad.errors import ConfigError
from ediaad.patterns import (
    NAMED_PATTERNS,
    RECOVERY_TARGETS,
    PatternSpec,
    from_json,
    to_json,
)

FIELD_NAMES = (
    "pattern_id",
    "range_bars_min",
    "range_bars_max",
    "band_atr_multiple_max",
    "atr_period",
    "breakdown_bars_max",
    "breakdown_depth_band_min",
    "breakdown_depth_band_max",
    "recovery_bars_max",
    "recovery_target",
)

# SPEC 第 5 節的內建規律預設值
EXPECTED_DEFAULTS = {
    "pattern_id": "range_fakeout_reversion",
    "range_bars_min": 20,
    "range_bars_max": 120,
    "band_atr_multiple_max": 3.0,
    "atr_period": 14,
    "breakdown_bars_max": 2,
    "breakdown_depth_band_min": 0.2,
    "breakdown_depth_band_max": 1.5,
    "recovery_bars_max": 5,
    "recovery_target": "range_mean",
}


def valid_kwargs(**overrides) -> dict:
    kwargs = dict(EXPECTED_DEFAULTS)
    kwargs.update(overrides)
    return kwargs


def build_spec(**overrides) -> PatternSpec:
    return PatternSpec(**valid_kwargs(**overrides))


# ---- AC-014：規格模型、相對單位欄位與建構時驗證 -----------------------------


def test_named_patterns_contains_the_first_named_pattern_with_spec_defaults():
    assert "range_fakeout_reversion" in NAMED_PATTERNS
    defaults = dict(NAMED_PATTERNS["range_fakeout_reversion"])
    assert defaults == EXPECTED_DEFAULTS

    spec = PatternSpec(**defaults)
    assert spec.pattern_id == "range_fakeout_reversion"


def test_spec_exposes_exactly_the_documented_relative_unit_fields():
    spec = build_spec()

    assert tuple(field.name for field in dataclasses.fields(spec)) == FIELD_NAMES
    assert "range_mean" in RECOVERY_TARGETS


def test_no_field_is_an_absolute_price():
    """相對單位保證：欄位名不得出現價格字眼（價格量級不該影響判定）。"""
    price_words = ("price", "open", "high", "low", "close", "volume")
    for name in FIELD_NAMES:
        assert not any(word in name for word in price_words), name
    assert RECOVERY_TARGETS == ("range_mean",)


def test_spec_is_frozen():
    spec = build_spec()

    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.range_bars_min = 5  # type: ignore[misc]


def test_equal_range_bounds_are_a_valid_boundary():
    spec = build_spec(range_bars_min=20, range_bars_max=20)

    assert spec.range_bars_min == spec.range_bars_max


def test_zero_recovery_bars_is_valid():
    """`k <= m <= k + 0` 合法：跌破與回歸可發生在同一根。"""
    assert build_spec(recovery_bars_max=0).recovery_bars_max == 0


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"pattern_id": ""}, id="空 pattern_id"),
        pytest.param({"pattern_id": None}, id="pattern_id 非字串"),
        pytest.param({"range_bars_min": 0}, id="range_bars_min 為 0"),
        pytest.param({"range_bars_min": -1}, id="range_bars_min 為負"),
        pytest.param({"range_bars_min": 30, "range_bars_max": 20}, id="min 大於 max"),
        pytest.param({"band_atr_multiple_max": 0}, id="band 上限為 0"),
        pytest.param({"band_atr_multiple_max": -1.0}, id="band 上限為負"),
        pytest.param({"atr_period": 0}, id="atr_period 為 0"),
        pytest.param({"atr_period": -1}, id="atr_period 為負"),
        pytest.param({"breakdown_bars_max": 0}, id="breakdown_bars_max 為 0"),
        pytest.param({"breakdown_bars_max": -1}, id="breakdown_bars_max 為負"),
        pytest.param({"breakdown_depth_band_min": -0.1}, id="深度下限為負"),
        pytest.param({"breakdown_depth_band_min": 0.5, "breakdown_depth_band_max": 0.2}, id="深度下限大於上限"),
        pytest.param({"recovery_bars_max": -1}, id="recovery_bars_max 為負"),
        pytest.param({"recovery_target": "range_high"}, id="未知 recovery_target"),
        pytest.param({"recovery_target": None}, id="recovery_target 非字串"),
        pytest.param({"range_bars_min": "20"}, id="int 欄位給字串"),
        pytest.param({"range_bars_min": True}, id="int 欄位給 bool"),
        pytest.param({"band_atr_multiple_max": "3.0"}, id="float 欄位給字串"),
        pytest.param({"atr_period": 14.5}, id="int 欄位給浮點數"),
    ],
)
def test_invalid_specs_cannot_be_constructed(overrides):
    with pytest.raises(ConfigError):
        PatternSpec(**valid_kwargs(**overrides))


# ---- AC-015：序列化契約（round-trip、穩定鍵序、嚴格還原）--------------------


def test_json_round_trip_is_lossless():
    spec = build_spec(range_bars_min=25, range_bars_max=25, recovery_bars_max=0)

    assert from_json(to_json(spec)) == spec


def test_to_json_is_stable_and_uses_sorted_keys():
    spec = build_spec()

    first = to_json(spec)
    second = to_json(spec)

    assert first == second
    keys = list(json.loads(first).keys())
    assert keys == sorted(keys)
    assert set(keys) == set(FIELD_NAMES)


def test_from_json_accepts_both_text_and_mapping():
    assert from_json(dict(EXPECTED_DEFAULTS)) == build_spec()
    assert from_json(json.dumps(EXPECTED_DEFAULTS)) == build_spec()


def test_from_json_rejects_a_missing_field_without_filling_defaults():
    payload = dict(EXPECTED_DEFAULTS)
    payload.pop("atr_period")

    with pytest.raises(ConfigError, match="atr_period"):
        from_json(payload)


def test_from_json_rejects_a_partial_payload():
    with pytest.raises(ConfigError):
        from_json({"pattern_id": "range_fakeout_reversion"})


def test_from_json_rejects_an_unknown_extra_field():
    payload = dict(EXPECTED_DEFAULTS)
    payload["unexpected_field"] = 1

    with pytest.raises(ConfigError, match="unexpected_field"):
        from_json(payload)


def test_from_json_rejects_wrong_types():
    payload = dict(EXPECTED_DEFAULTS)
    payload["range_bars_min"] = "20"

    with pytest.raises(ConfigError):
        from_json(payload)


def test_from_json_rejects_invalid_json_text():
    with pytest.raises(ConfigError):
        from_json("{not json")


def test_from_json_rejects_non_object_json():
    with pytest.raises(ConfigError):
        from_json("[1, 2, 3]")
