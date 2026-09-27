"""`ediaad.outlook` 的公開契約測試（TASK-006）。

觀察邊界：只呼叫 `ediaad.outlook.forward_stats` 並觀察回傳 `OutlookStats` 的五個欄位；
片段以輕量測試替身提供（同時具備 `end_index` 與 `recovery_index`），不檢視內部彙總方式。

**oracle 的來源**：期望值以 Python 標準庫 `statistics`（`mean`／`median`／`pstdev`）在測試中
獨立計算，不使用待測模組；每個值的推導寫在註解旁。所有測試離線可跑。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from ediaad.outlook import OutlookStats, forward_stats

HORIZON = 2


@dataclass(frozen=True)
class Fragment:
    """測試替身：同時具備兩條路線的結束索引欄位（見 AC-013）。"""

    end_index: int
    recovery_index: int | None = None


def build_series(closes: list[float]) -> pd.DataFrame:
    times = pd.date_range("2024-01-01T00:00:00Z", periods=len(closes), freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "time": times,
            "open": [value - 0.5 for value in closes],
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
            "close": [float(value) for value in closes],
            "volume": [10.0] * len(closes),
        }
    )


# 收盤價序列：後續報酬為 0.05、0.0、-0.25、0.3888…、0.2，最後一個片段被尾端排除
CLOSES = [100, 120, 105, 120, 90, 90, 130, 125, 140, 150]
ENDS = [0, 1, 3, 5, 7, 8]


# ---- AC-012：後續走勢統計與邊界 ---------------------------------------------


def test_two_fragments_with_known_returns():
    """TASK-006 測試計畫的第一個綠燈案例：+0.10 與 -0.05。"""
    series = build_series([100, 100, 110, 100, 100, 95])

    stats = forward_stats([Fragment(0), Fragment(3)], series, HORIZON)

    assert isinstance(stats, OutlookStats)
    assert stats.samples == 2
    assert stats.up_probability == pytest.approx(0.5)
    assert stats.mean_return == pytest.approx(0.025)


def test_statistics_match_independently_derived_values():
    series = build_series(CLOSES)

    stats = forward_stats([Fragment(end) for end in ENDS], series, HORIZON)

    # returns = [105/100-1, 120/120-1, 90/120-1, 125/90-1, 150/125-1]（end=8 被排除）
    assert stats.samples == 5
    assert stats.up_probability == pytest.approx(3 / 5)  # 0.0 不算上漲
    assert stats.mean_return == pytest.approx(0.07777777777777777)
    assert stats.median_return == pytest.approx(0.050000000000000044)
    assert stats.std_return == pytest.approx(0.21259710925644668)  # 母體標準差 ddof=0


def test_std_return_uses_population_standard_deviation():
    """刻意與 pandas 預設的 ddof=1 不同：母體標準差必須小於樣本標準差。"""
    series = build_series(CLOSES)

    stats = forward_stats([Fragment(end) for end in ENDS], series, HORIZON)

    sample_std = pd.Series([0.05, 0.0, -0.25, 0.38888888888888884, 0.2]).std(ddof=1)
    assert stats.std_return == pytest.approx(0.21259710925644668)
    assert stats.std_return < sample_std


def test_fragment_is_kept_when_end_plus_horizon_is_last_index():
    """邊界成對斷言：end+horizon == len-1 保留；== len 排除。"""
    series = build_series(CLOSES)

    kept = forward_stats([Fragment(len(series) - 1 - HORIZON)], series, HORIZON)
    dropped = forward_stats([Fragment(len(series) - HORIZON)], series, HORIZON)

    assert kept.samples == 1
    assert dropped.samples == 0


def test_zero_return_counts_as_sample_but_not_as_up():
    series = build_series([100, 100, 100, 110])

    stats = forward_stats([Fragment(0), Fragment(1)], series, HORIZON)

    # end=0 → 100/100-1 = 0.0（不是上漲）；end=1 → 110/100-1 = 0.1
    assert stats.samples == 2
    assert stats.up_probability == pytest.approx(0.5)


def test_empty_fragment_list_returns_zero_samples_and_none_fields():
    series = build_series(CLOSES)

    stats = forward_stats([], series, HORIZON)

    assert stats.samples == 0
    assert stats.up_probability is None
    assert stats.mean_return is None
    assert stats.median_return is None
    assert stats.std_return is None


def test_all_fragments_excluded_by_horizon_returns_none_fields():
    series = build_series(CLOSES)

    stats = forward_stats([Fragment(len(series) - HORIZON), Fragment(len(series) - 1)], series, HORIZON)

    assert stats.samples == 0
    assert stats.up_probability is None
    assert stats.mean_return is None
    assert stats.median_return is None
    assert stats.std_return is None


# ---- AC-013：雙路線共用介面（end_attr）與 F-002 回歸 -------------------------


def test_default_end_attribute_is_end_index():
    """F-002 回歸：未指定 end_attr 時必須用 end_index，而不是物件上的其他索引。"""
    series = build_series(CLOSES)
    # end_index=0 → 報酬 0.05；recovery_index=7 → 報酬 0.2。兩者必須可區分。
    fragment = Fragment(end_index=0, recovery_index=7)

    stats = forward_stats([fragment], series, HORIZON)

    assert stats.samples == 1
    assert stats.mean_return == pytest.approx(0.050000000000000044)


def test_end_attr_selects_the_recovery_index():
    series = build_series(CLOSES)
    fragment = Fragment(end_index=0, recovery_index=7)

    stats = forward_stats([fragment], series, HORIZON, end_attr="recovery_index")

    assert stats.samples == 1
    assert stats.mean_return == pytest.approx(0.19999999999999996)


def test_both_routes_share_the_same_function_and_agree():
    """兩條路線在同一組位置時必須得到完全相同的統計（F-002 的結構性修法）。"""
    series = build_series(CLOSES)
    positions = [0, 1, 3, 5, 7]

    scan_route = forward_stats(
        [Fragment(end_index=end, recovery_index=99) for end in positions], series, HORIZON
    )
    pattern_route = forward_stats(
        [Fragment(end_index=99, recovery_index=end) for end in positions],
        series,
        HORIZON,
        end_attr="recovery_index",
    )

    assert scan_route == pattern_route
    assert scan_route.samples == 5


def test_missing_end_attribute_reports_config_error_instead_of_attribute_error():
    """F-002 的失敗模式：物件缺欄位時要給出可讀錯誤，而不是裸的 AttributeError。"""
    from ediaad.errors import ConfigError

    @dataclass(frozen=True)
    class RecoveryOnly:
        recovery_index: int

    series = build_series(CLOSES)

    with pytest.raises(ConfigError, match="end_index"):
        forward_stats([RecoveryOnly(3)], series, HORIZON)


def test_zero_base_price_reports_config_error():
    from ediaad.errors import ConfigError

    series = build_series([100, 100, 100, 0, 50, 60])

    with pytest.raises(ConfigError, match="close"):
        forward_stats([Fragment(3)], series, HORIZON)


def test_non_finite_base_price_reports_config_error():
    from ediaad.errors import ConfigError

    series = build_series([100, 100, 100, 100, 50, 60])
    series.loc[3, "close"] = float("nan")

    with pytest.raises(ConfigError, match="close"):
        forward_stats([Fragment(3)], series, HORIZON)
