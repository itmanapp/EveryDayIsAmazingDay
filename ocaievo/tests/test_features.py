"""`ediaad.features` 的公開契約測試（TASK-003）。

觀察邊界：只呼叫 `ediaad.features.extract`／`extract_matrix` 與讀取 `FEATURE_NAMES`；
不檢視私有輔助函式。

**oracle 的來源**：`EXPECTED_VECTOR` 是以**獨立算術**推導的——只使用 Python 標準庫
`statistics` 與四則運算，完全不經過 `ediaad.features`，因此不是「用同一段演算法當
oracle」。每個值的推導過程寫在旁邊的註解。

所有測試離線可跑，資料為合成序列。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ediaad.features import FEATURE_NAMES, extract, extract_matrix

# 4 根合成 K 線：open／high／low／close／volume
WINDOW_ROWS = [
    ("2024-01-01T00:00:00Z", 100, 110, 95, 105, 10),
    ("2024-01-01T01:00:00Z", 105, 115, 100, 100, 20),
    ("2024-01-01T02:00:00Z", 100, 108, 92, 96, 30),
    ("2024-01-01T03:00:00Z", 96, 102, 94, 101, 40),
]

# 以標準庫 statistics 與四則運算獨立推導（不經 ediaad.features）
EXPECTED_VECTOR = [
    -0.03809523809523807,  # total_return = 101/105 - 1
    0.04531121388301722,  # return_std = pstdev([-5/105, -4/100, 5/96])
    0.38541666666666663,  # mean_body_ratio = mean([5/15, 5/15, 4/16, 5/8])
    0.40625,  # mean_upper_shadow_ratio = mean([5/15, 10/15, 8/16, 1/8])
    0.20833333333333331,  # mean_lower_shadow_ratio = mean([5/15, 0, 4/16, 2/8])
    0.5,  # bull_ratio = 2/4
    0.08571428571428574,  # max_drawdown = 1 - min(close/cummax(close))
    -0.49975603804353946,  # ma_slope_normalized = -1.6 / pstdev(close)
    2.3333333333333335,  # volume_ratio = mean([30, 40]) / mean([10, 20])
    0.391304347826087,  # close_position = (101 - 92) / (115 - 92)
]

EXPECTED_NAMES = [
    "total_return",
    "return_std",
    "mean_body_ratio",
    "mean_upper_shadow_ratio",
    "mean_lower_shadow_ratio",
    "bull_ratio",
    "max_drawdown",
    "ma_slope_normalized",
    "volume_ratio",
    "close_position",
]


def build_window(rows=WINDOW_ROWS) -> pd.DataFrame:
    """由 (time, open, high, low, close, volume) 資料列建立符合序列契約的視窗。"""
    frame = pd.DataFrame(
        rows, columns=["time", "open", "high", "low", "close", "volume"]
    )
    frame["time"] = pd.to_datetime(frame["time"], utc=True).astype("datetime64[ns, UTC]")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = frame[column].astype("float64")
    return frame


# ---- AC-005：10 維特徵與手算值相符 -------------------------------------------


def test_feature_names_contract():
    assert len(FEATURE_NAMES) == 10
    assert list(FEATURE_NAMES) == EXPECTED_NAMES
    assert len(set(FEATURE_NAMES)) == 10
    assert all(isinstance(name, str) for name in FEATURE_NAMES)


def test_extract_returns_float64_vector_of_length_ten():
    vector = extract(build_window())

    assert isinstance(vector, np.ndarray)
    assert vector.shape == (10,)
    assert vector.dtype == np.float64


def test_extract_matches_independently_derived_values():
    vector = extract(build_window())

    np.testing.assert_allclose(vector, EXPECTED_VECTOR, rtol=0, atol=1e-9)


# ---- AC-006：尺度不變、平移不變的適用範圍與退化情境 --------------------------

# 0 基索引：第 3、4、5、6、8、9、10 維（依定義使用差值或比較，具平移不變性）
TRANSLATION_INVARIANT_INDICES = (2, 3, 4, 5, 7, 8, 9)
# 第 1、2、7 維（total_return、return_std、max_drawdown）依定義使用價格比值
TRANSLATION_VARIANT_INDICES = (0, 1, 6)


def scale_prices(rows, factor: float):
    return [(t, o * factor, h * factor, l * factor, c * factor, v) for t, o, h, l, c, v in rows]


def shift_prices(rows, shift: float):
    return [(t, o + shift, h + shift, l + shift, c + shift, v) for t, o, h, l, c, v in rows]


@pytest.mark.parametrize("factor", [0.01, 0.5, 1.0, 1000.0])
def test_extract_is_invariant_under_price_scaling(factor):
    base = extract(build_window())

    scaled = extract(build_window(scale_prices(WINDOW_ROWS, factor)))

    np.testing.assert_allclose(scaled, base, rtol=0, atol=1e-9)


@pytest.mark.parametrize("shift", [7.0, 1234.5, -42.0])
def test_extract_is_translation_invariant_for_difference_based_features(shift):
    base = extract(build_window())

    shifted = extract(build_window(shift_prices(WINDOW_ROWS, shift)))

    for index in TRANSLATION_INVARIANT_INDICES:
        assert shifted[index] == pytest.approx(base[index], abs=1e-9), FEATURE_NAMES[index]


@pytest.mark.parametrize("shift", [7.0, 1234.5, -42.0])
def test_translation_does_change_the_three_price_ratio_features(shift):
    """反向斷言：證明上一個測試不是空轉（若把不變性寫成恆真斷言，這裡會失敗）。"""
    base = extract(build_window())

    shifted = extract(build_window(shift_prices(WINDOW_ROWS, shift)))

    for index in TRANSLATION_VARIANT_INDICES:
        assert abs(shifted[index] - base[index]) > 1e-9, FEATURE_NAMES[index]


def test_extract_handles_flat_window_with_finite_values():
    flat = [
        (time, 100.0, 100.0, 100.0, 100.0, volume)
        for time, _, _, _, _, volume in WINDOW_ROWS
    ]

    vector = extract(build_window(flat))

    assert np.isfinite(vector).all()
    assert vector[2] == pytest.approx(0.0)  # mean_body_ratio
    assert vector[3] == pytest.approx(0.0)  # mean_upper_shadow_ratio
    assert vector[4] == pytest.approx(0.0)  # mean_lower_shadow_ratio
    assert vector[7] == pytest.approx(0.0)  # ma_slope_normalized（收盤標準差為 0）
    assert vector[9] == pytest.approx(0.0)  # close_position（區間高度為 0）


def test_extract_handles_zero_volume_window_with_finite_values():
    no_volume = [(t, o, h, l, c, 0.0) for t, o, h, l, c, _ in WINDOW_ROWS]

    vector = extract(build_window(no_volume))

    assert np.isfinite(vector).all()
    assert vector[8] == pytest.approx(0.0)  # volume_ratio：前半量能為 0 時取 0


@pytest.mark.parametrize("bars", [1, 2])
def test_extract_handles_very_short_windows(bars):
    vector = extract(build_window(WINDOW_ROWS[:bars]))

    assert vector.shape == (10,)
    assert np.isfinite(vector).all()


# ---- AC-007：批次矩陣的形狀、與逐窗一致、寬度不隨視窗成長 -------------------

from ediaad.errors import ConfigError  # noqa: E402


def build_series(bars: int = 200) -> pd.DataFrame:
    """確定性合成序列（以 math.sin 產生，無亂數、無網路），符合序列契約。"""
    import math

    times = pd.date_range("2024-01-01T00:00:00Z", periods=bars, freq="1h", tz="UTC")
    closes = [100.0 + 10.0 * math.sin(i / 7.0) + i * 0.05 for i in range(bars)]
    rows = []
    for i in range(bars):
        previous = closes[i - 1] if i > 0 else closes[0]
        open_ = previous
        close = closes[i]
        rows.append(
            (
                times[i],
                open_,
                max(open_, close) + 0.5,
                min(open_, close) - 0.5,
                close,
                100.0 + (i % 13) * 10.0,
            )
        )
    return build_window(rows)


def test_extract_matrix_shape_for_length_200_window_20_step_1():
    matrix = extract_matrix(build_series(200), window=20, step=1)

    assert matrix.shape == (181, 10)
    assert matrix.dtype == np.float64


def test_extract_matrix_rows_equal_per_window_extract():
    series = build_series(60)
    window = 15
    step = 3

    matrix = extract_matrix(series, window=window, step=step)

    starts = list(range(0, len(series) - window + 1, step))
    assert matrix.shape[0] == len(starts)
    for row_index, start in enumerate(starts):
        np.testing.assert_allclose(
            matrix[row_index],
            extract(series.iloc[start : start + window]),
            rtol=0,
            atol=1e-12,
        )


def test_extract_matrix_step_20_does_not_overlap():
    matrix = extract_matrix(build_series(200), window=20, step=20)

    assert matrix.shape == (10, 10)


def test_extract_matrix_width_is_fixed_and_payload_has_no_window_sized_data():
    for window in (5, 20, 60):
        matrix = extract_matrix(build_series(200), window=window, step=1)

        assert matrix.shape[1] == 10
        assert matrix.ndim == 2
        # 單一連續 float64 區塊，總位元組 = 列數 × 10 × 8，沒有隨視窗長度成長的內容
        assert matrix.nbytes == matrix.shape[0] * 10 * 8


@pytest.mark.parametrize("window,step", [(0, 1), (-1, 1), (20, 0), (20, -3)])
def test_extract_matrix_rejects_invalid_parameters(window, step):
    with pytest.raises(ConfigError):
        extract_matrix(build_series(50), window=window, step=step)


def test_extract_matrix_returns_empty_matrix_when_series_is_shorter_than_window():
    matrix = extract_matrix(build_series(10), window=20, step=1)

    assert matrix.shape == (0, 10)
    assert matrix.dtype == np.float64
