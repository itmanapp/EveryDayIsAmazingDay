"""穩健正規化與加權相似度排序。

**問題**：10 個特徵的單位與尺度差異很大（報酬是 0.01 級、量能比可能是 3.0），
不能直接相加。

**解法（規格第 5.2 節）**：以**候選池自身的統計量**做穩健正規化，再計算加權 L1 距離：

```
median[j] = 中位數(P[:, j])
IQR[j]    = 第 75 百分位 - 第 25 百分位
z(x)[j]   = (x[j] - median[j]) / IQR[j]   若 IQR[j] != 0
          = 0                             若 IQR[j] == 0（退化為 0，避免除以零）
d         = Σ w[j] · |z(範例)[j] - z(候選)[j]| / Σ w[j]
score     = 1 / (1 + d)          ∈ (0, 1]
```

**為什麼用中位數與 IQR 而不是平均數與標準差**：中位數與 IQR 對離群值不敏感。價格
資料常有一兩根極端 K 線，用平均數會讓整組統計被單點拉歪。

**排序穩定性**：以 `numpy.lexsort` 先依分數降冪、再依索引升冪，因此同分時的順序
唯一且可重現（符合「同一輸入必須得到相同結果」的品質要求）。

本模組只做計算：不讀寫檔案、不連網、不輸出訊息（SPEC 第 5 節原則 1）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .errors import ConfigError
from .features import FEATURE_NAMES

__all__ = ["Match", "DEFAULT_WEIGHTS", "rank"]

DEFAULT_WEIGHTS: tuple[float, ...] = tuple(1.0 for _ in FEATURE_NAMES)


@dataclass(frozen=True)
class Match:
    """一筆候選的相似度結果。"""

    index: int
    """候選在候選池中的列索引。"""

    score: float
    """相似度分數，`1 / (1 + 距離)`，落在 (0, 1]。"""

    feature_distance: float
    """加權 L1 特徵距離，0 表示特徵完全相同。"""


def _robust_normalize(values: np.ndarray, pool: np.ndarray) -> np.ndarray:
    """以候選池的中位數與 IQR 做穩健正規化；IQR 為 0 的維度退化為 0。"""
    median = np.median(pool, axis=0)
    iqr = np.percentile(pool, 75, axis=0) - np.percentile(pool, 25, axis=0)
    array = np.asarray(values, dtype=np.float64)
    normalized = np.zeros(array.shape, dtype=np.float64)
    informative = iqr != 0
    normalized[..., informative] = (
        array[..., informative] - median[informative]
    ) / iqr[informative]
    return normalized


def rank(
    sample: Sequence[float] | np.ndarray,
    pool: Sequence[Sequence[float]] | np.ndarray,
    weights: Sequence[float] | np.ndarray = DEFAULT_WEIGHTS,
) -> list[Match]:
    """對候選池的每一列計分並排序（分數降冪、同分索引升冪）。

    `pool` 形狀為 `(M, 10)`；`sample` 長度為 10。回傳長度為 `M` 的 `Match` 清單。
    """
    pool_array = np.asarray(pool, dtype=np.float64)
    sample_array = np.asarray(sample, dtype=np.float64)
    weight_array = np.asarray(weights, dtype=np.float64)
    expected_dimensions = len(FEATURE_NAMES)

    if sample_array.shape != (expected_dimensions,):
        raise ConfigError(
            f"範例特徵必須是長度 {expected_dimensions} 的一維向量，"
            f"收到形狀 {sample_array.shape}"
        )
    if pool_array.ndim != 2 or pool_array.shape[1] != expected_dimensions:
        raise ConfigError(
            f"候選池必須是形狀 (M, {expected_dimensions}) 的二維矩陣，"
            f"收到形狀 {pool_array.shape}"
        )
    if weight_array.shape != (expected_dimensions,):
        raise ConfigError(
            f"權重長度必須是 {expected_dimensions}，收到長度 {weight_array.shape[0] if weight_array.ndim else 0}"
        )
    if np.any(weight_array < 0):
        raise ConfigError("權重不得為負值")
    weight_total = float(np.sum(weight_array))
    if weight_total == 0:
        raise ConfigError("權重總和不得為 0")

    if pool_array.shape[0] == 0:
        return []

    z_sample = _robust_normalize(sample_array, pool_array)
    z_pool = _robust_normalize(pool_array, pool_array)
    distances = (
        np.sum(weight_array * np.abs(z_pool - z_sample), axis=1) / np.sum(weight_array)
    )
    scores = 1.0 / (1.0 + distances)

    order = np.lexsort((np.arange(pool_array.shape[0]), -scores))
    return [
        Match(
            index=int(index),
            score=float(scores[index]),
            feature_distance=float(distances[index]),
        )
        for index in order
    ]
