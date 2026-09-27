"""歷史回看的共用流程：一份序列 ＋ 一段範例 → 五鍵報表（AC-046）。

CLI 的 `match` 子命令（TASK-011）與 `POST /api/match`（TASK-024）**都呼叫這裡**，
因此兩條路徑產生的報表必然相同——不是「兩份實作剛好一致」。本模組只做組裝：
相似度掃描交給 `scan.scan_similar`、後續走勢統計交給 `outlook.forward_stats`，
不重寫任何計算，也不碰 I/O（讀檔與連網由呼叫端負責，SPEC 第 5 節原則 1／2）。

預設值定義在這裡，讓 CLI 的 argparse 預設與網頁端點的預設來自同一個常數
（否則「兩邊預設不同」會是另一個不明確的表達）。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .errors import ConfigError
from .outlook import forward_stats
from .scan import scan_similar

__all__ = [
    "DEFAULT_TOP",
    "DEFAULT_HORIZON",
    "DEFAULT_STEP",
    "DEFAULT_OVERLAP",
    "run_match",
]

DEFAULT_TOP = 10
DEFAULT_HORIZON = 20
DEFAULT_STEP = 1
DEFAULT_OVERLAP = 0.5


def iso(value: Any) -> str:
    """時間欄位的 ISO 字串（CLI 與網頁共用同一種寫法）。"""
    return pd.Timestamp(value).isoformat()


def run_match(
    series: pd.DataFrame,
    sample: pd.DataFrame,
    *,
    top: int = DEFAULT_TOP,
    horizon: int = DEFAULT_HORIZON,
    step: int = DEFAULT_STEP,
    overlap: float = DEFAULT_OVERLAP,
    data_source: str = "csv",
) -> dict[str, Any]:
    """掃描 `series` 中與 `sample` 相似的片段並統計其後續走勢。

    `window` 就是範例長度（與 CLI 的 `--sample` 語意相同）；其餘參數不合法時由
    `scan_similar`／本函式以 `ConfigError` 指出不合法處。

    `horizon` 的下限在**這裡**擋（`forward_stats` 對 0 會回一組無意義但看似正常的
    統計：每個片段的報酬都恰好是 0），因此兩個入口都必須經過這一行。
    """
    if horizon < 1:
        raise ConfigError(f"horizon 必須 >= 1，收到 {horizon}")

    window = len(sample)
    matches = scan_similar(series, sample, window, top=top, step=step, overlap=overlap)
    stats = forward_stats(matches, series, horizon)

    return {
        "sample": {
            "length": window,
            "time_start": iso(sample["time"].iloc[0]),
            "time_end": iso(sample["time"].iloc[-1]),
        },
        "params": {
            "window": window,
            "top": top,
            "horizon": horizon,
            "step": step,
            "overlap": overlap,
        },
        "data_source": data_source,
        "matches": [
            {
                "start_index": match.start_index,
                "end_index": match.end_index,
                "score": match.score,
                "time_start": iso(match.time_start),
                "time_end": iso(match.time_end),
            }
            for match in matches
        ],
        "outlook": {
            "samples": stats.samples,
            "up_probability": stats.up_probability,
            "mean_return": stats.mean_return,
            "median_return": stats.median_return,
            "std_return": stats.std_return,
        },
    }
