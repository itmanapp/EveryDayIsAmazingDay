"""台股除權息還原（AC-034）。

除權息當天價格會直接跳空（配息 2 元 → 價格掉約 2 元），未還原的序列會讓偵測器把這個
跳空**誤判為「向下跌破」**。本模組以 TWSE `TWT49U` 的官方欄位還原：

- 事件來源：`TWT49U?startDate=&endDate=`（**只有**這組參數可用；`strDate`／`endDate`
  會回誤導性錯誤、`date=` 被忽略，見 ADR-003 與 `PROJECT.md` 的實測表）。
- 還原方式（方案 B）：事件日**之前**的價格乘上「除權息參考價 ÷ 除權息前收盤價」，
  事件日與之後不動——事件日當天交易的已經是除息後的價格。
- 保底（方案 A）：事件無法還原時（前收盤價非正數等）不改動序列，但把該日放進
  `AdjustResult.unavailable_dates`，讓呼叫端可以標記該日不可用於規律判定。
"""

from __future__ import annotations

import datetime as dt
import json
import math
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from ..data import PRICE_COLUMNS
from ..errors import ConfigError, DataFormatError, SourceError
from .base import parse_iso_day

__all__ = [
    "EX_RIGHTS_URL",
    "ExRightsEvent",
    "AdjustResult",
    "adjust_series",
    "fetch_ex_rights",
]

EX_RIGHTS_URL = "https://www.twse.com.tw/exchangeReport/TWT49U"
HTTP_TIMEOUT = 10.0

#: `權值+息值 = 除權息前收盤價 - 除權息參考價`（TWSE 表附註）。價格為兩位小數，
#: 因此允許半個 tick 的進位誤差；超出即代表解析到的欄位或表結構有問題。
VALUE_TOLERANCE = 0.02

HttpClient = Callable[[str], Any]

_FIELD_TO_ATTRIBUTE: dict[str, str] = {
    "資料日期": "date",
    "股票代號": "symbol",
    "除權息前收盤價": "pre_close",
    "除權息參考價": "reference_price",
    "權值+息值": "value",
}

_OPTIONAL_FIELD_TO_ATTRIBUTE: dict[str, str] = {"權/息": "kind"}


@dataclass(frozen=True)
class ExRightsEvent:
    """一次除權息事件（欄位名對應 TWSE 表的官方欄位）。"""

    symbol: str
    date: dt.date
    pre_close: float
    """除權息前收盤價。"""
    reference_price: float
    """除權息參考價。"""
    value: float
    """權值+息值。"""
    kind: str = ""
    """`權`／`息`／`權息`（來源的「權/息」欄）。"""

    @property
    def factor(self) -> float:
        """事件日之前價格的縮放倍率（除權息參考價 ÷ 除權息前收盤價）。"""
        if not math.isfinite(self.pre_close) or self.pre_close <= 0:
            raise DataFormatError(
                f"除權息前收盤價必須是正數才能還原，收到 {self.pre_close!r}"
            )
        return self.reference_price / self.pre_close


@dataclass(frozen=True)
class AdjustResult:
    """還原結果：序列、成功套用的事件數、無法還原的日期與整體狀態。"""

    series: pd.DataFrame
    applied: int
    unavailable_dates: tuple[dt.date, ...]
    status: str
    """`adjusted`（全部成功）／`partial`（部分無法還原）／`unavailable`（全部無法還原）／
    `unchanged`（沒有可套用的事件）。"""


def _default_client(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _to_float(value: Any) -> float:
    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError as error:
        raise SourceError(f"TWSE 除權息表的數值欄無法解讀：{value!r}") from error


def _field_positions(fields: Any) -> dict[str, int]:
    if not isinstance(fields, list):
        raise SourceError(f"TWSE 除權息表缺少 fields 欄位清單，收到 {type(fields).__name__}")

    positions: dict[str, int] = {}
    wanted = {**_FIELD_TO_ATTRIBUTE, **_OPTIONAL_FIELD_TO_ATTRIBUTE}
    for name in _FIELD_TO_ATTRIBUTE:
        try:
            positions[name] = fields.index(name)
        except ValueError as error:
            raise SourceError(
                f"TWSE 除權息表缺少欄位 {name!r}；實際欄位：{fields}"
            ) from error
    for name in _OPTIONAL_FIELD_TO_ATTRIBUTE:
        if name in fields:
            positions[name] = fields.index(name)
    assert set(positions) <= set(wanted)
    return positions


def fetch_ex_rights(
    start: object,
    end: object,
    *,
    client: HttpClient | None = None,
    symbol: str | None = None,
) -> list[ExRightsEvent]:
    """取得 `start`～`end`（含頭尾）之間的除權息事件，依（日期, 代號）排序。

    查無事件時回傳空清單（當月沒有公司除權息是正常結果，不是錯誤）。
    """
    first = parse_iso_day(start)
    last = parse_iso_day(end)
    if last < first:
        # TWSE 對此會回誤導性的「查詢結束日期小於查詢開始日期」，因此先在本地擋下。
        raise ConfigError(f"結束日期 {last} 不得早於開始日期 {first}")

    getter = client if client is not None else _default_client
    url = (
        f"{EX_RIGHTS_URL}?response=json"
        f"&startDate={first.strftime('%Y%m%d')}&endDate={last.strftime('%Y%m%d')}"
    )
    try:
        payload = getter(url)
    except Exception as error:  # 注入的客戶端是外部邊界
        raise SourceError(f"TWSE 除權息請求失敗：{error}") from error

    if not isinstance(payload, dict):
        raise SourceError(
            f"TWSE 除權息回應必須是 JSON 物件，收到 {type(payload).__name__}"
        )

    rows = payload.get("data")
    if not rows:
        return []
    if not isinstance(rows, list):
        raise SourceError(f"TWSE 除權息回應的 data 必須是陣列，收到 {type(rows).__name__}")
    if payload.get("stat") != "OK":
        raise SourceError(f"TWSE 除權息回應的 stat 不是 OK：{payload.get('stat')!r}")

    positions = _field_positions(payload.get("fields"))
    wanted = symbol.strip().upper() if isinstance(symbol, str) else None

    events: list[ExRightsEvent] = []
    for index, row in enumerate(rows):
        widest = max(positions.values())
        if not isinstance(row, (list, tuple)) or len(row) <= widest:
            raise SourceError(f"TWSE 除權息表第 {index} 列欄位不足：{row!r}")

        values: dict[str, Any] = {}
        for name, attribute in _FIELD_TO_ATTRIBUTE.items():
            raw = row[positions[name]]
            if attribute == "date":
                from .twse import parse_roc_date

                values[attribute] = parse_roc_date(raw)
            elif attribute == "symbol":
                values[attribute] = str(raw).strip().upper()
            else:
                values[attribute] = _to_float(raw)
        if "權/息" in positions:
            values["kind"] = str(row[positions["權/息"]]).strip()

        difference = values["pre_close"] - values["reference_price"]
        if abs(difference - values["value"]) > VALUE_TOLERANCE:
            raise SourceError(
                f"TWSE 除權息表第 {index} 列不符「權值+息值 = 除權息前收盤價 - 除權息參考價」："
                f"{values['pre_close']} - {values['reference_price']} = {difference:.6f}，"
                f"但權值+息值為 {values['value']}"
            )

        if wanted is None or values["symbol"] == wanted:
            events.append(ExRightsEvent(**values))

    return sorted(events, key=lambda event: (event.date, event.symbol))


def adjust_series(series: pd.DataFrame, events: list[ExRightsEvent]) -> AdjustResult:
    """以事件還原序列；不改動輸入（回傳新物件），並回報無法還原的日期。

    呼叫端負責只傳入「這條序列的商品」的事件；本函式不從序列推斷商品代號。
    """
    if not events:
        return AdjustResult(series=series, applied=0, unavailable_dates=(), status="unchanged")

    frame = series.copy(deep=True)
    stamps = frame["time"].dt.date
    applied = 0
    unavailable: list[dt.date] = []

    for event in sorted(events, key=lambda item: item.date):
        try:
            factor = event.factor
        except DataFormatError:
            unavailable.append(event.date)
            continue
        mask = (stamps < event.date).to_numpy()
        if not mask.any():
            continue
        for column in PRICE_COLUMNS:
            if column in frame.columns:
                frame.loc[mask, column] = frame.loc[mask, column] * factor
        applied += 1

    if unavailable and applied:
        status = "partial"
    elif unavailable:
        status = "unavailable"
    elif applied:
        status = "adjusted"
    else:
        status = "unchanged"

    return AdjustResult(
        series=frame,
        applied=applied,
        unavailable_dates=tuple(unavailable),
        status=status,
    )
