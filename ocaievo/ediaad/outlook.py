"""後續走勢統計。

某個命中片段**結束之後**緊接的 H 根 K 線稱為該片段的**後續走勢**，H 稱為 horizon。
本模組只回答一個統計問題：歷史上規律出現後，接下來 H 根的報酬分佈與上漲機率。
**這是統計，不是預測**（報告第 2.10、5.8 節）。

```
對每個片段：
  end    = getattr(fragment, end_attr)          # ScanMatch 用 end_index，PatternEvent 用 recovery_index
  若 end + H >= 序列長度 → 排除（不足 H 根）
  報酬   = close[end + H] / close[end] - 1

彙總：
  samples        = 納入的片段數
  up_probability = mean(報酬 > 0)        ← 恰好為 0 不算上漲
  mean_return    = 平均
  median_return  = 中位數
  std_return     = 母體標準差（ddof=0）
  無樣本時 → samples=0，其餘欄位為 None（而非 0）
```

**「不足 H 根就排除」很重要**：若把尾端納入，會系統性偏向某些結果（因為最近的片段
還沒走完）。**`None` 而非 0**：0 會被誤讀為「報酬為 0」，`None` 明確表示「沒有樣本」。

**`end_attr` 的由來（F-002）**：相似度路線的 `ScanMatch` 用 `end_index`，規律路線的
`PatternEvent` 用 `recovery_index`。兩者共用本函式，以參數指名結束欄位；本模組因此
不必匯入 `scan` 或 `patterns`，維持依賴方向單向（報告第 4.2 節）。

**已知的統計偏誤**：相似片段之間可能時間相近、高度相關，使上漲機率被重複計數影響。
第一版只揭露樣本數，不做獨立性處理（報告第 5.8 節）。

本模組只做計算：不讀寫檔案、不連網、不輸出訊息（SPEC 第 5 節原則 1）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

import numpy as np
import pandas as pd

from .errors import ConfigError

__all__ = ["OutlookStats", "HasEndIndex", "forward_stats"]


@runtime_checkable
class HasEndIndex(Protocol):
    """描述「有結束索引欄位」的片段；`ScanMatch` 與 `PatternEvent` 都符合此形狀。"""

    end_index: int


@dataclass(frozen=True)
class OutlookStats:
    """後續走勢的彙總結果。無樣本時除 `samples` 外皆為 `None`。"""

    samples: int
    up_probability: float | None
    mean_return: float | None
    median_return: float | None
    std_return: float | None


def _end_index(fragment: object, end_attr: str) -> int:
    """取得片段的結束索引；缺欄位時給出可讀錯誤（F-002 的失敗模式）。"""
    if not hasattr(fragment, end_attr):
        raise ConfigError(
            f"片段 {type(fragment).__name__} 缺少結束索引欄位 {end_attr!r}；"
            "相似度路線（ScanMatch）用 end_index，規律路線（PatternEvent）用 recovery_index"
        )
    return int(getattr(fragment, end_attr))


def forward_stats(
    fragments: Sequence[object],
    series: pd.DataFrame,
    horizon: int,
    end_attr: str = "end_index",
) -> OutlookStats:
    """計算片段群之後 H 根的報酬統計。

    `end_attr` 指名「片段結束位置」的欄位名：相似度路線用預設的 `end_index`，
    規律路線傳入 `recovery_index`。
    """
    closes = series["close"].to_numpy(dtype=np.float64)
    length = closes.shape[0]

    returns: list[float] = []
    for fragment in fragments:
        end = _end_index(fragment, end_attr)
        if end + horizon >= length:
            continue
        base = closes[end]
        if not np.isfinite(base) or base == 0:
            raise ConfigError(
                f"close[{end}] 不是可用的基準價格（{base!r}），無法計算後續報酬"
            )
        returns.append(float(closes[end + horizon] / base - 1.0))

    if not returns:
        return OutlookStats(
            samples=0,
            up_probability=None,
            mean_return=None,
            median_return=None,
            std_return=None,
        )

    values = np.asarray(returns, dtype=np.float64)
    return OutlookStats(
        samples=int(values.size),
        up_probability=float(np.count_nonzero(values > 0) / values.size),
        mean_return=float(np.mean(values)),
        median_return=float(np.median(values)),
        std_return=float(np.std(values)),
    )
