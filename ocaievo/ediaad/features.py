"""10 維尺度不變形態特徵。

把一段 K 線視窗壓縮成長度 10 的向量（見 `docs/workflow/SPEC.md` 第 5 節與報告第 5.1 節）。
這些特徵用於**相似度路線**（找出「差不多」的片段）；**規律路線**不依賴它們，而是直接
檢查閾值條件。

**尺度不變**：把整段價格乘上正數 k 後，10 維特徵全部不變。**平移不變**只涵蓋第
3、4、5、6、8、9、10 維；第 1、2、7 維（`total_return`、`return_std`、
`max_drawdown`）依定義使用價格**比值**，加常數平移後必然改變（SPEC AC-006）。

**退化情境一律回傳有限值而非 NaN**：所有除法都先檢查分母或以
`numpy.divide(..., where=...)` 處理，被遮蓋的位置為 0。全平坦視窗（`high == low`）
會得到實體比 0、影線比 0、斜率 0、位置 0。

本模組只做計算：不讀寫檔案、不連網、不使用亂數、不輸出訊息（SPEC 第 5 節原則 1）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .errors import ConfigError

__all__ = ["FEATURE_NAMES", "extract", "extract_matrix"]

FEATURE_NAMES: tuple[str, ...] = (
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
)

_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def _safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """逐元素相除，分母為 0 的位置回傳 0（退化情境的統一慣例）。"""
    num = np.asarray(numerator, dtype=np.float64)
    den = np.asarray(denominator, dtype=np.float64)
    out = np.zeros(np.broadcast_shapes(num.shape, den.shape), dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        np.divide(num, den, out=out, where=(den != 0))
    return out


def _columns(window: pd.DataFrame) -> dict[str, np.ndarray]:
    return {
        column: window[column].to_numpy(dtype=np.float64) for column in _OHLCV_COLUMNS
    }


def _scalar(value) -> float:
    return float(np.asarray(value, dtype=np.float64))


def extract(window: pd.DataFrame) -> np.ndarray:
    """由一段視窗抽出 10 維特徵向量（形狀 `(10,)`、dtype float64）。"""
    data = _columns(window)
    open_ = data["open"]
    high = data["high"]
    low = data["low"]
    close = data["close"]
    volume = data["volume"]
    bars = close.shape[0]

    total_return = _scalar(_safe_divide(close[-1] - close[0], close[0]))

    if bars > 1:
        returns = _safe_divide(close[1:] - close[:-1], close[:-1])
        return_std = _scalar(np.std(returns))
    else:
        return_std = 0.0

    bar_range = high - low
    body_ratio = _scalar(np.mean(_safe_divide(np.abs(close - open_), bar_range)))
    upper_shadow = _scalar(np.mean(_safe_divide(high - np.maximum(open_, close), bar_range)))
    lower_shadow = _scalar(np.mean(_safe_divide(np.minimum(open_, close) - low, bar_range)))
    bull_ratio = _scalar(np.count_nonzero(close > open_) / bars)

    running_max = np.maximum.accumulate(close)
    max_drawdown = _scalar(1.0 - np.min(_safe_divide(close, running_max)))

    index = np.arange(bars, dtype=np.float64)
    index_mean = _scalar(np.mean(index))
    close_mean = _scalar(np.mean(close))
    slope_variance = _scalar(np.sum((index - index_mean) ** 2))
    if slope_variance != 0:
        slope = _scalar(
            np.sum((index - index_mean) * (close - close_mean)) / slope_variance
        )
    else:
        slope = 0.0
    close_std = _scalar(np.std(close))
    ma_slope_normalized = slope / close_std if close_std != 0 else 0.0

    first_half = volume[: bars // 2]
    second_half = volume[bars // 2 :]
    if first_half.size == 0 or _scalar(np.mean(first_half)) == 0:
        volume_ratio = 0.0
    else:
        volume_ratio = _scalar(np.mean(second_half) / np.mean(first_half))

    close_position = _scalar(
        _safe_divide(close[-1] - np.min(low), np.max(high) - np.min(low))
    )

    return np.array(
        [
            total_return,
            return_std,
            body_ratio,
            upper_shadow,
            lower_shadow,
            bull_ratio,
            max_drawdown,
            ma_slope_normalized,
            volume_ratio,
            close_position,
        ],
        dtype=np.float64,
    )


def extract_matrix(series: pd.DataFrame, window: int, step: int = 1) -> np.ndarray:
    """對整個序列抽出所有候選視窗的特徵矩陣（形狀 `(M, 10)`）。

    `M = len(range(0, len(series) - window + 1, step))`。輸出寬度固定為 10，**不隨
    視窗長度成長**（報告第 5.3 節的效能設計）。序列短於視窗時回傳形狀 `(0, 10)`
    的空矩陣；該情境由掃描層（TASK-005 的 `scan_similar`）以 `ConfigError` 擋下。
    """
    if window < 1:
        raise ConfigError(f"window 必須 >= 1，收到 {window}")
    if step < 1:
        raise ConfigError(f"step 必須 >= 1，收到 {step}")

    length = len(series)
    starts = range(0, length - window + 1, step)
    rows = [extract(series.iloc[start : start + window]) for start in starts]
    if not rows:
        return np.empty((0, len(FEATURE_NAMES)), dtype=np.float64)
    return np.vstack(rows).astype(np.float64, copy=False)
