"""交易日曆與市場別規律預設（AC-035）。

**為什麼需要日曆**：報告第 7.4 節——「盤整 20 根」在加密貨幣是 20 小時，在台股日線是
20 個交易日 ≈ 4 週，語意完全不同；且股票有週末、國定假日、停牌，v0.2 的「連續等距 K 線」
假設在股票市場不成立。因此：

1. `TradingCalendar`／`is_trading_day`：判斷某一天是否為交易日（週末一定不是；TWSE
   `holidaySchedule` 的休市日也不是）。
2. `apply_calendar`：把序列過濾成「只有交易日」，確保交給 `detect` 的每一根都是交易日。
3. `MARKET_PATTERN_DEFAULTS`／`default_spec_for`：台股日線與加密貨幣使用不同的規律預設
   參數，且可被設定覆寫。

**日曆的來源限制（如實記載）**：`holidaySchedule` 只列出「值得公告的日期」，不是完整的
交易日清單——平日若不在休市清單中，本模組就視為交易日。另外春節等連續假期在回應中只有
**一列**，範圍寫在說明文字裡（例如「依規定於2月15日至2月19日放假5日」），因此本模組會
解析說明中的「N月N日至N月N日」並把區間內每一天都標為休市；解析不到時至少會標記該列
自己的日期。
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..errors import ConfigError, SourceError
from ..patterns import NAMED_PATTERNS, PatternSpec
from .base import parse_iso_day

__all__ = [
    "MARKET_PATTERN_DEFAULTS",
    "TradingCalendar",
    "apply_calendar",
    "default_spec_for",
    "is_trading_day",
    "load_twse_calendar",
]

#: 說明或名稱出現這些字樣即代表「這一天休市」。
CLOSED_MARKERS: tuple[str, ...] = ("放假", "無交易", "停止交易", "休市", "補假")

_MONTH_DAY = re.compile(r"(\d{1,2})月(\d{1,2})日")


@dataclass(frozen=True)
class TradingCalendar:
    """交易日曆：以「休市日集合」表示，週末一律不是交易日。"""

    closed_dates: frozenset[dt.date] = field(default_factory=frozenset)
    year: int | None = None

    def is_trading_day(self, day: dt.date) -> bool:
        """週一至週五且不在休市清單中即為交易日。"""
        if day.weekday() >= 5:
            return False
        return day not in self.closed_dates


def is_trading_day(calendar: TradingCalendar, day: dt.date) -> bool:
    """`TradingCalendar.is_trading_day` 的模組層寫法（SPEC 第 5 節列出的公開名稱）。"""
    return calendar.is_trading_day(day)


def _closed_days_for(own_date: dt.date, text: str) -> set[dt.date]:
    """由一列的說明文字決定它涵蓋哪些休市日。"""
    if not any(marker in text for marker in CLOSED_MARKERS):
        return set()

    days = {own_date}
    tokens = _MONTH_DAY.findall(text)
    if len(tokens) < 2:
        return days

    try:
        first = dt.date(own_date.year, int(tokens[0][0]), int(tokens[0][1]))
        last = dt.date(own_date.year, int(tokens[-1][0]), int(tokens[-1][1]))
    except ValueError:
        return days

    # 只展開同一年的遞增區間；跨年或反向區間保守地只標記該列自己的日期。
    if last < first:
        return days
    day = first
    while day <= last:
        days.add(day)
        day += dt.timedelta(days=1)
    return days


def _field_positions(fields: Any) -> dict[str, int]:
    if not isinstance(fields, list):
        raise SourceError(f"TWSE 開休市表缺少 fields 欄位清單，收到 {type(fields).__name__}")

    positions: dict[str, int] = {}
    for name in ("日期",):
        if name not in fields:
            raise SourceError(f"TWSE 開休市表缺少欄位 {name!r}；實際欄位：{fields}")
        positions[name] = fields.index(name)
    for name in ("名稱", "說明"):
        if name in fields:
            positions[name] = fields.index(name)
    return positions


def load_twse_calendar(payload: Any) -> TradingCalendar:
    """由 TWSE `holidaySchedule` 回應建立日曆。

    注意：該端點的 `stat` 是小寫 `ok`（與其他端點不同），因此**不檢查** `stat`，
    只驗證結構；`data` 為空時代表沒有公告任何休市日。
    """
    if not isinstance(payload, Mapping):
        raise SourceError(
            f"TWSE 開休市回應必須是 JSON 物件，收到 {type(payload).__name__}"
        )

    rows = payload.get("data")
    if rows is None:
        raise SourceError("TWSE 開休市回應缺少 data")
    if not isinstance(rows, list):
        raise SourceError(f"TWSE 開休市回應的 data 必須是陣列，收到 {type(rows).__name__}")

    positions = _field_positions(payload.get("fields"))
    widest = max(positions.values())
    closed: set[dt.date] = set()

    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) <= widest:
            raise SourceError(f"TWSE 開休市表第 {index} 列欄位不足：{row!r}")

        raw_date = row[positions["日期"]]
        try:
            own_date = parse_iso_day(raw_date)
        except ConfigError as error:
            raise SourceError(f"TWSE 開休市表第 {index} 列日期無法解讀：{error}") from error

        text = "".join(
            str(row[positions[name]]) for name in ("名稱", "說明") if name in positions
        )
        closed |= _closed_days_for(own_date, text)

    year = payload.get("queryYear")
    return TradingCalendar(
        closed_dates=frozenset(closed),
        year=year if isinstance(year, int) else None,
    )


def apply_calendar(series: pd.DataFrame, calendar: TradingCalendar) -> pd.DataFrame:
    """只保留交易日的 K 線（回傳新物件，不改動輸入）。

    這確保交給 `patterns.detect` 的每個時間戳都是交易日——「連續 N 根」的語意在台股
    才與加密貨幣一致（都是 N 個交易日）。
    """
    stamps = series["time"].dt.date
    keep = [calendar.is_trading_day(day) for day in stamps]
    filtered = series.loc[keep].reset_index(drop=True)
    return filtered


#: 市場別規律預設。`crypto` 沿用既有 `NAMED_PATTERNS`（不改變既有行為）；
#: `stock` 只在「日線的一根 ≈ 小時線的 24 倍」有意義的欄位上不同：
#: 回歸與跌破允許更多天、盤整上限從半年縮到一季。
_STOCK_OVERRIDES: dict[str, Any] = {
    "range_bars_max": 60,
    "breakdown_bars_max": 3,
    "recovery_bars_max": 10,
}

MARKET_PATTERN_DEFAULTS: dict[str, dict[str, Any]] = {
    "crypto": dict(NAMED_PATTERNS["range_fakeout_reversion"]),
    "stock": {**dict(NAMED_PATTERNS["range_fakeout_reversion"]), **_STOCK_OVERRIDES},
}


def default_spec_for(
    market_id: str, overrides: Mapping[str, Any] | None = None
) -> PatternSpec:
    """取得市場別預設規格；`overrides` 可覆寫任何欄位（未覆寫者維持市場別預設）。"""
    try:
        base = MARKET_PATTERN_DEFAULTS[market_id]
    except KeyError as error:
        raise ConfigError(
            f"未知的市場別 {market_id!r}；可用市場別：{sorted(MARKET_PATTERN_DEFAULTS)}"
        ) from error

    params = {**base, **dict(overrides or {})}
    try:
        return PatternSpec(**params)
    except (TypeError, ValueError, ConfigError) as error:
        raise ConfigError(
            f"規律參數不合法（市場別 {market_id}）：{error}"
        ) from error
