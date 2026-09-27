"""規律模型：規格（`PatternSpec`）、ATR、偵測器與範例學習。

本檔目前收錄 TASK-007 交付的**規格模型**；`atr`／`detect`（TASK-008）與 `learn`
（TASK-009）會在同一檔案擴充。

**規格全是相對單位**：欄位只有 K 線根數、ATR 倍數、band 倍數與具名目標，**沒有任何
價格欄位**——這是尺度不變在資料結構層的保證（SPEC 第 5 節）。

**不合法規格無法被建構出來**：所有驗證都在 `__post_init__`（含交叉檢查，如
`range_bars_min <= range_bars_max`），因此「先建構、後驗證」的錯誤用法在型別層就
不可能發生。驗證失敗一律為 `ConfigError`。

本模組只做計算與資料驗證：不讀寫檔案、不連網、不輸出訊息（SPEC 第 5 節原則 1）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields

import numpy as np
import pandas as pd
from typing import Any

from .errors import ConfigError

__all__ = [
    "PatternSpec",
    "PatternEvent",
    "NAMED_PATTERNS",
    "RECOVERY_TARGETS",
    "atr",
    "detect",
    "learn",
    "to_json",
    "from_json",
]

RECOVERY_TARGETS: tuple[str, ...] = ("range_mean",)

#: 內建具名規律：名稱 → `PatternSpec` 的建構參數（SPEC 第 5 節的預設值）。
NAMED_PATTERNS: Mapping[str, dict[str, Any]] = {
    "range_fakeout_reversion": {
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
}


def _require_int(name: str, value: object, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} 必須是整數，收到 {value!r}")
    if value < minimum:
        raise ConfigError(f"{name} 必須 >= {minimum}，收到 {value}")


def _require_number(name: str, value: object, *, minimum: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} 必須是數值，收到 {value!r}")
    if minimum is not None and float(value) < minimum:
        raise ConfigError(f"{name} 必須 >= {minimum}，收到 {value}")


@dataclass(frozen=True)
class PatternSpec:
    """一組可序列化的相對門檻（見 SPEC 第 5 節的欄位契約）。"""

    pattern_id: str
    """規律識別名。"""

    range_bars_min: int
    """盤整相位最短根數。"""

    range_bars_max: int
    """盤整相位最長根數。"""

    band_atr_multiple_max: float
    """區間帶寬上限（ATR 倍數）。"""

    atr_period: int
    """ATR 週期。"""

    breakdown_bars_max: int
    """跌破必須在盤整結束後幾根內出現。"""

    breakdown_depth_band_min: float
    """跌破深度下限（band 倍數）。"""

    breakdown_depth_band_max: float
    """跌破深度上限（band 倍數）。"""

    recovery_bars_max: int
    """回歸必須在跌破後幾根內完成。"""

    recovery_target: str
    """回歸目標，目前只有 `range_mean`。"""

    def __post_init__(self) -> None:
        if not isinstance(self.pattern_id, str) or not self.pattern_id.strip():
            raise ConfigError(f"pattern_id 必須是非空字串，收到 {self.pattern_id!r}")
        _require_int("range_bars_min", self.range_bars_min, 1)
        _require_int("range_bars_max", self.range_bars_max, 1)
        if self.range_bars_min > self.range_bars_max:
            raise ConfigError(
                f"range_bars_min（{self.range_bars_min}）不得大於 "
                f"range_bars_max（{self.range_bars_max}）"
            )
        _require_number("band_atr_multiple_max", self.band_atr_multiple_max)
        if float(self.band_atr_multiple_max) <= 0:
            raise ConfigError(
                f"band_atr_multiple_max 必須大於 0，收到 {self.band_atr_multiple_max}"
            )
        _require_int("atr_period", self.atr_period, 1)
        _require_int("breakdown_bars_max", self.breakdown_bars_max, 1)
        _require_number("breakdown_depth_band_min", self.breakdown_depth_band_min, minimum=0)
        _require_number("breakdown_depth_band_max", self.breakdown_depth_band_max, minimum=0)
        if float(self.breakdown_depth_band_max) < float(self.breakdown_depth_band_min):
            raise ConfigError(
                "breakdown_depth_band_max "
                f"（{self.breakdown_depth_band_max}）不得小於 "
                f"breakdown_depth_band_min（{self.breakdown_depth_band_min}）"
            )
        _require_int("recovery_bars_max", self.recovery_bars_max, 0)
        if self.recovery_target not in RECOVERY_TARGETS:
            raise ConfigError(
                f"recovery_target 必須是 {list(RECOVERY_TARGETS)} 之一，"
                f"收到 {self.recovery_target!r}"
            )


#: 範例學習的常數（報告第 5.7 節）
LEARN_MIN_BARS = 12
RANGE_THRESHOLD_LADDER: tuple[float, ...] = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0)
LEARN_MIN_RANGE_BARS = 5
MTR_WINDOW = 5
LEARNED_PATTERN_ID = "learned_range_fakeout_reversion"

@dataclass(frozen=True)
class PatternEvent:
    """一次命中，含四個相位索引與信心值（見 SPEC 第 5 節的欄位契約）。"""

    pattern_id: str
    """命中的規律識別名。"""

    range_start_index: int
    """盤整相位起始索引。"""

    range_end_index: int
    """盤整相位結束索引。"""

    breakdown_index: int
    """跌破相位索引（第一次穿破區間下緣的 K 線）。"""

    recovery_index: int
    """回歸相位索引（第一次收盤回到區間均值之上），也是事件的結束位置。"""

    confidence: float
    """信心值 0～1（三個條件滿足度的平均，**不是機率**）。"""

    band: float
    """實測區間帶寬。"""

    breakdown_depth: float
    """實測跌破深度（band 倍數）。"""

    recovery_bars: int
    """實際回歸根數（`recovery_index - breakdown_index`）。"""


def atr(series: pd.DataFrame, period: int) -> pd.Series:
    """平均真實區間（Average True Range）。

    ```
    previous_close[0] = close[0]
    TR[i] = max(high[i]-low[i], |high[i]-previous_close[i]|, |low[i]-previous_close[i]|)
    ATR[i] = TR[i-period+1 .. i] 的平均     (i >= period-1)
           = NaN                            (i <  period-1)
    ```

    **「不引用未來」是硬性要求**：`ATR[i]` 只使用索引 `i`（含）以前的資料，因此把植入點
    之後的價格任意縮放，之前的 ATR 完全不變。滾動平均以 `cumsum` 實作，每個索引 O(1)。
    """
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ConfigError(f"period 必須是 >= 1 的整數，收到 {period!r}")

    high = series["high"].to_numpy(dtype=np.float64)
    low = series["low"].to_numpy(dtype=np.float64)
    close = series["close"].to_numpy(dtype=np.float64)
    bars = close.shape[0]

    previous_close = np.empty(bars, dtype=np.float64)
    previous_close[0] = close[0]
    previous_close[1:] = close[:-1]

    true_range = np.maximum.reduce(
        [
            high - low,
            np.abs(high - previous_close),
            np.abs(low - previous_close),
        ]
    )

    values = np.full(bars, np.nan, dtype=np.float64)
    if bars >= period:
        cumulative = np.concatenate(([0.0], np.cumsum(true_range)))
        values[period - 1 :] = (cumulative[period:] - cumulative[:-period]) / period
    return pd.Series(values, index=series.index, name="atr")


def _confidence(
    spec: PatternSpec, *, band: float, limit: float, depth: float, recovery_bars: int
) -> float:
    """三個條件滿足度的平均（SPEC 第 5.6 節）。**不是機率**。"""
    band_score = 1.0 - min(band / limit, 1.0) if limit > 0 else 1.0

    depth_min = float(spec.breakdown_depth_band_min)
    depth_max = float(spec.breakdown_depth_band_max)
    half_range = (depth_max - depth_min) / 2.0
    if half_range == 0:
        depth_score = 1.0
    else:
        midpoint = (depth_min + depth_max) / 2.0
        depth_score = 1.0 - abs(depth - midpoint) / half_range

    if spec.recovery_bars_max == 0:
        recovery_score = 1.0 if recovery_bars == 0 else 0.0
    else:
        recovery_score = 1.0 - recovery_bars / spec.recovery_bars_max

    return float(
        min(max((band_score + depth_score + recovery_score) / 3.0, 0.0), 1.0)
    )


def _longest_range_ending_at(
    high: np.ndarray,
    low: np.ndarray,
    j: int,
    limit: float,
    *,
    min_bars: int,
    max_bars: int,
) -> tuple[int, float, float] | None:
    """以 `j` 結尾、`band <= limit`、長度介於 `[min_bars, max_bars]` 的最長區間。

    回傳 `(start_index, band, range_low)`；找不到時回 `None`。`band` 對起始索引
    單調不減，因此由最短視窗往左擴張、一旦超限即停止，最後一個合法者即為最長區間。
    `detect` 與 `learn` 共用此搜尋，避免出現第二套區間判定邏輯。
    """
    if not np.isfinite(limit):
        return None
    longest_start = max(0, j - max_bars + 1)
    shortest_start = j - min_bars + 1
    if shortest_start < longest_start:
        return None

    best: tuple[int, float, float] | None = None
    running_high = float(np.max(high[shortest_start : j + 1]))
    running_low = float(np.min(low[shortest_start : j + 1]))
    for start in range(shortest_start, longest_start - 1, -1):
        if start < shortest_start:
            running_high = max(running_high, high[start])
            running_low = min(running_low, low[start])
        band = running_high - running_low
        if band <= limit:
            best = (start, band, running_low)
        else:
            break
    return best


def detect(series: pd.DataFrame, spec: PatternSpec) -> list[PatternEvent]:
    """在整份序列上找出所有符合 `spec` 的規律事件。

    判定條件（SPEC 第 5.5 節）：

    1. **盤整相位** `[i, j]`：長度落在 `[range_bars_min, range_bars_max]`，且
       `band = max(high[i..j]) - min(low[i..j]) <= band_atr_multiple_max × ATR[j]`
       （ATR 只用索引 `j` 以前的資料）。
    2. **假跌破** `k`：`j < k <= j + breakdown_bars_max`、`low[k] < min(low[i..j])`，
       且 `depth = (min(low[i..j]) - low[k]) / band` 落在深度區間內。
    3. **回歸** `m`：`k <= m <= k + recovery_bars_max`、`close[m] >= mean(close[i..j])`。
    4. **信心值**：三個條件滿足度的平均（`_confidence`）。

    **每個 `j` 取「最長可行區間」**：`band` 對起始索引單調不減，因此由短往長掃描，
    一旦超限即停止，最後一個合法者就是最長區間。
    """
    high = series["high"].to_numpy(dtype=np.float64)
    low = series["low"].to_numpy(dtype=np.float64)
    close = series["close"].to_numpy(dtype=np.float64)
    bars = close.shape[0]
    atr_values = atr(series, spec.atr_period).to_numpy(dtype=np.float64)

    events: list[PatternEvent] = []

    for j in range(bars):
        limit = spec.band_atr_multiple_max * atr_values[j]
        if not np.isfinite(limit):
            continue

        found = _longest_range_ending_at(
            high,
            low,
            j,
            float(limit),
            min_bars=spec.range_bars_min,
            max_bars=spec.range_bars_max,
        )
        if found is None:
            continue
        best_start, best_band, best_low = found
        if best_band <= 0:
            continue

        breakdown_index = None
        for candidate in range(
            j + 1, min(j + spec.breakdown_bars_max, bars - 1) + 1
        ):
            if low[candidate] < best_low:
                breakdown_index = candidate
                break
        if breakdown_index is None:
            continue

        depth = (best_low - float(low[breakdown_index])) / best_band
        if not (
            spec.breakdown_depth_band_min
            <= depth
            <= spec.breakdown_depth_band_max
        ):
            continue

        range_mean = float(np.mean(close[best_start : j + 1]))
        recovery_index = None
        for candidate in range(
            breakdown_index,
            min(breakdown_index + spec.recovery_bars_max, bars - 1) + 1,
        ):
            if close[candidate] >= range_mean:
                recovery_index = candidate
                break
        if recovery_index is None:
            continue

        # 反例防護：回歸之前若出現比 low[k] 更低的低點，該次跌破不成立
        # （「回歸之前」指嚴格早於回歸根，即 k+1 .. m-1）。
        if recovery_index > breakdown_index + 1:
            intervening_low = float(np.min(low[breakdown_index + 1 : recovery_index]))
            if intervening_low < low[breakdown_index]:
                continue

        recovery_bars = recovery_index - breakdown_index
        events.append(
            PatternEvent(
                pattern_id=spec.pattern_id,
                range_start_index=best_start,
                range_end_index=j,
                breakdown_index=breakdown_index,
                recovery_index=recovery_index,
                confidence=_confidence(
                    spec,
                    band=best_band,
                    limit=float(limit),
                    depth=depth,
                    recovery_bars=recovery_bars,
                ),
                band=best_band,
                breakdown_depth=float(depth),
                recovery_bars=recovery_bars,
            )
        )

    # 去重：同一段結構（相同的 breakdown_index 與 recovery_index）只保留**最長**的一次；
    # 長度相同時保留盤整相位較晚結束者（區間緊鄰跌破，較符合「盤整後跌破」的語意）。
    longest: dict[tuple[int, int], PatternEvent] = {}
    for event in events:
        key = (event.breakdown_index, event.recovery_index)
        current = longest.get(key)
        candidate_rank = (
            event.range_end_index - event.range_start_index,
            event.range_end_index,
        )
        if current is None:
            longest[key] = event
            continue
        current_rank = (
            current.range_end_index - current.range_start_index,
            current.range_end_index,
        )
        if candidate_rank > current_rank:
            longest[key] = event

    return sorted(
        longest.values(),
        key=lambda event: (
            -(event.range_end_index - event.range_start_index + 1),
            event.range_start_index,
        ),
    )


def _rolling_median_true_range(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int
) -> np.ndarray:
    """真實區間的滾動中位數。

    **為什麼用滾動中位數而不是平均 ATR 當尺**：範例裡若有一根振幅極大的 K 線，
    平均 ATR 會被單點拉高，讓緊鄰它的一段短視窗被誤判為「窄區間」。中位數對
    單點極值不敏感（報告第 5.7 節）。
    """
    bars = close.shape[0]
    previous_close = np.empty(bars, dtype=np.float64)
    previous_close[0] = close[0]
    previous_close[1:] = close[:-1]
    true_range = np.maximum.reduce(
        [
            high - low,
            np.abs(high - previous_close),
            np.abs(low - previous_close),
        ]
    )
    return (
        pd.Series(true_range)
        .rolling(window, min_periods=1)
        .median()
        .to_numpy(dtype=np.float64)
    )


def learn(sample: pd.DataFrame) -> PatternSpec:
    """由一段數值範例推估出可用的 `PatternSpec`（報告第 5.7 節）。

    1. 以**真實區間的滾動中位數** `mtr` 為尺，依門檻階梯 `(1.0, 1.5, 2.0, 3.0, 4.0, 6.0)`
       倍由嚴到鬆，取第一個能找到合法盤整區間的門檻，並在該門檻下取**最長**區間。
    2. 跌破相位 = 盤整區間之後的**最低點**；未低於區間下緣即無法推估。
    3. 回歸相位 = 跌破（含）之後第一根收盤回到區間均值；找不到即無法推估。
    4. 把實測相對量**放寬成容差區間**，確保推估出的規格一定能命中自己的範例。

    **容差全部朝「更容易命中範例」的方向放寬**；推估不出來時丟出 `ConfigError`，
    絕不回傳隨意參數。同一範例的結果完全可重現（沒有隨機、沒有搜尋）。
    """
    high = sample["high"].to_numpy(dtype=np.float64)
    low = sample["low"].to_numpy(dtype=np.float64)
    close = sample["close"].to_numpy(dtype=np.float64)
    bars = close.shape[0]

    if bars < LEARN_MIN_BARS:
        raise ConfigError(
            f"範例至少需要 {LEARN_MIN_BARS} 根 K 線才能推估規格，收到 {bars} 根"
        )

    mtr = _rolling_median_true_range(high, low, close, MTR_WINDOW)

    chosen: tuple[int, int, float, float] | None = None
    for multiple in RANGE_THRESHOLD_LADDER:
        candidate: tuple[int, int, float, float] | None = None
        for j in range(bars):
            found = _longest_range_ending_at(
                high,
                low,
                j,
                float(mtr[j] * multiple),
                min_bars=LEARN_MIN_RANGE_BARS,
                max_bars=bars,
            )
            if found is None:
                continue
            start, band, range_low = found
            if candidate is None or (j - start, -start) > (
                candidate[1] - candidate[0],
                -candidate[0],
            ):
                candidate = (start, j, band, range_low)
        if candidate is not None:
            chosen = candidate
            break

    if chosen is None:
        raise ConfigError(
            "範例中找不到任何盤整區間（已由嚴到鬆試過 "
            f"{list(RANGE_THRESHOLD_LADDER)} 倍的滾動中位數真實區間）"
        )

    range_start, range_end, band, range_low = chosen
    if band <= 0:
        raise ConfigError("範例的盤整區間帶寬為 0，無法推估規格")
    if range_end + 1 >= bars:
        raise ConfigError("範例在盤整區間之後沒有 K 線，無法判定跌破相位")

    tail = np.arange(range_end + 1, bars)
    breakdown_index = int(tail[int(np.argmin(low[tail]))])
    if float(low[breakdown_index]) >= range_low:
        raise ConfigError(
            "範例在盤整區間之後的最低點未低於區間下緣，無法判定跌破相位"
        )

    range_bars = range_end - range_start + 1
    depth = (range_low - float(low[breakdown_index])) / band
    range_mean = float(np.mean(close[range_start : range_end + 1]))

    recovery_index = None
    for candidate_index in range(breakdown_index, bars):
        if close[candidate_index] >= range_mean:
            recovery_index = candidate_index
            break
    if recovery_index is None:
        raise ConfigError("範例在跌破之後收盤未回到區間均值，無法判定回歸相位")

    recovery_bars = recovery_index - breakdown_index
    # ATR 週期上限為 14，並確保 ATR 在盤整區間結束處**有定義**（短範例不會是 NaN）。
    atr_period = max(1, min(14, range_end + 1))
    atr_at_range_end = float(atr(sample, atr_period).iloc[range_end])
    if not np.isfinite(atr_at_range_end) or atr_at_range_end <= 0:
        raise ConfigError("範例的 ATR 在盤整區間結束處無法定義，無法推估規格")

    return PatternSpec(
        pattern_id=LEARNED_PATTERN_ID,
        range_bars_min=round(range_bars * 0.5),
        range_bars_max=round(range_bars * 1.5),
        band_atr_multiple_max=min(6.0, max(1.0, band / atr_at_range_end * 1.2)),
        atr_period=atr_period,
        # 報告的容差清單未涵蓋此欄位：取範例實測的「盤整結束 → 跌破」間隔（至少 1），
        # 否則推估出的規格會找不到自己的跌破相位。
        breakdown_bars_max=max(1, breakdown_index - range_end),
        breakdown_depth_band_min=max(0.05, depth * 0.7),
        breakdown_depth_band_max=min(3.0, depth * 1.3),
        recovery_bars_max=recovery_bars + 2,
        recovery_target="range_mean",
    )


def _spec_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(PatternSpec))


def to_json(spec: PatternSpec) -> str:
    """把規格序列化為 JSON 字串（`sort_keys=True`，輸出穩定可比較）。"""
    return json.dumps(asdict(spec), sort_keys=True, ensure_ascii=False)


def from_json(payload: str | Mapping[str, Any]) -> PatternSpec:
    """由 JSON 字串或映射還原規格。

    **嚴格還原**：缺欄位、多欄位、型別不符都丟出 `ConfigError`，不用預設值補齊——
    悄悄補預設會讓「使用者以為自己設定的參數」與「實際生效的參數」不一致。
    """
    if isinstance(payload, str):
        try:
            data: Any = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ConfigError(f"無法解析規格 JSON：{error}") from error
    else:
        data = payload

    if not isinstance(data, Mapping):
        raise ConfigError(f"規格必須是 JSON 物件，收到 {type(data).__name__}")

    expected = set(_spec_field_names())
    provided = set(data)
    missing = sorted(expected - provided)
    if missing:
        raise ConfigError(f"規格缺少欄位：{'、'.join(missing)}")
    unknown = sorted(provided - expected)
    if unknown:
        raise ConfigError(f"規格含未知欄位：{'、'.join(unknown)}")

    return PatternSpec(**dict(data))
