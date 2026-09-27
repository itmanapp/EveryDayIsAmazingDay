"""滑動視窗掃描與重疊抑制。

流程（規格第 5.3 節）：

1. 抽出範例特徵，並以 `features.extract_matrix` 抽出全部候選特徵 `(M, 10)`。
2. 以 `similarity.rank` 取得分數由高到低的候選順序。
3. **依分數順序貪婪接受互不衝突者**：對每個候選，檢查它與「已接受的所有片段」的
   重疊比例；`> overlap` 者丟棄，否則接受，累計達 `top` 筆即停止。
4. 為每筆補上時間界線。

重疊比例（閉區間，含頭尾）：

```
重疊比例 = max(0, min(e1, e2) - max(s1, s2) + 1) / window
```

**「恰好等於門檻」必須保留**：比較使用嚴格大於（`> overlap`），因此重疊恰好 50%
的兩個候選都會被保留。這是刻意的邊界定義。

**為什麼用貪婪而不是全域最佳化**：貪婪是 O(M·K)、結果可預期，且第一版不需要
「最大化總分」這種目標；代價是可能不是理論最佳解，但換來可預測性（報告第 5.3 節）。

**效能設計**：候選特徵矩陣形狀固定為 `(M, 10)`，不隨視窗長度成長。

本模組只做計算：不讀寫檔案、不連網、不輸出訊息（SPEC 第 5 節原則 1）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np
import pandas as pd

from .errors import ConfigError
from .features import extract, extract_matrix
from .similarity import DEFAULT_WEIGHTS, rank

__all__ = ["ScanMatch", "scan_similar"]


@dataclass(frozen=True)
class ScanMatch:
    """一筆通過重疊抑制的相似片段。"""

    start_index: int
    """片段在序列中的起始索引（含）。"""

    end_index: int
    """片段在序列中的結束索引（含），等於 `start_index + window - 1`。"""

    score: float
    """相似度分數，`1 / (1 + 距離)`。"""

    time_start: Any
    """`time` 欄位在 `start_index` 的時間。"""

    time_end: Any
    """`time` 欄位在 `end_index` 的時間。"""


def _overlap_ratio(
    start_a: int, end_a: int, start_b: int, end_b: int, window: int
) -> float:
    """兩個閉區間片段的重疊比例。"""
    return max(0, min(end_a, end_b) - max(start_a, start_b) + 1) / window


def scan_similar(
    series: pd.DataFrame,
    sample: pd.DataFrame,
    window: int,
    top: int,
    step: int = 1,
    overlap: float = 0.5,
    weights: Sequence[float] | np.ndarray = DEFAULT_WEIGHTS,
) -> list[ScanMatch]:
    """在序列上滑動掃描，回傳不超過 `top` 筆互不衝突的相似片段。

    參數不合法時一律丟出 `ConfigError` 並指出不合法處（對應 CLI exit 2），
    不外洩 `ValueError`／`KeyError`。
    """
    if not isinstance(window, (int, np.integer)) or window < 1:
        raise ConfigError(f"window 必須 >= 1，收到 {window!r}")
    if len(series) < window:
        raise ConfigError(f"序列長度 {len(series)} 短於 window={window}，無法掃描")
    if "time" not in series.columns:
        raise ConfigError("序列缺少必要欄位 time，無法回報片段的時間界線")
    if len(sample) != window:
        raise ConfigError(f"範例長度必須等於 window={window}，收到 {len(sample)}")
    if top < 1:
        raise ConfigError(f"top 必須 >= 1，收到 {top}")
    if step < 1:
        raise ConfigError(f"step 必須 >= 1，收到 {step}")
    if not 0 <= overlap < 1:
        raise ConfigError(f"overlap 必須落在 [0, 1)，收到 {overlap}")

    candidate_starts = list(range(0, len(series) - window + 1, step))
    sample_features = extract(sample)
    pool = extract_matrix(series, window, step)
    ranked = rank(sample_features, pool, weights)

    accepted: list[tuple[int, int, float]] = []
    for match in ranked:
        start = candidate_starts[match.index]
        end = start + window - 1
        if any(
            _overlap_ratio(start, end, kept_start, kept_end, window) > overlap
            for kept_start, kept_end, _ in accepted
        ):
            continue
        accepted.append((start, end, match.score))
        if len(accepted) >= top:
            break

    times = series["time"]
    return [
        ScanMatch(
            start_index=start,
            end_index=end,
            score=score,
            time_start=times.iloc[start],
            time_end=times.iloc[end],
        )
        for start, end, score in accepted
    ]
