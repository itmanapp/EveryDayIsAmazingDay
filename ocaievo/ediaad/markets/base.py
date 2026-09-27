"""市場來源的介面、registry 與共用結構。

**單一來源真相**：每個來源自行宣告 `supported_intervals`，設定的週期驗證一律查 registry
（`get_source(source_id).supported_intervals`）。本模組**不提供全域的「可用週期」清單**
作為驗證依據——`INTERVAL_ORDER` 只是訊息排序用的固定順序（報告第 7.1 節、AC-030）。

**依賴方向（SPEC 第 5 節原則 1）**：本模組只依賴 `errors` 與 `pandas`，不做 I/O、不連網、
不輸出訊息；各來源的實際取得行為在 `crypto.py`／`twse.py`／`us.py`／`custom.py`。
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd

from ..errors import ConfigError

__all__ = [
    "DEFAULT_SOURCE_ID",
    "INTERVAL_ORDER",
    "Instrument",
    "Source",
    "all_sources",
    "get_source",
    "parse_iso_day",
    "register",
    "unregister",
]

#: 週期的固定排序（僅用於訊息與清單的穩定順序，**不是**驗證用的白名單）。
INTERVAL_ORDER: tuple[str, ...] = (
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
    "1d",
    "1w",
)

#: 設定未指定 `source_id` 時使用的來源：本機 CSV 不需要金鑰，是唯一隨時可用的來源。
DEFAULT_SOURCE_ID = "csv"


@dataclass(frozen=True)
class Instrument:
    """商品與週期。`source_id` 為空字串表示「尚未指定來源」。"""

    symbol: str
    interval: str
    source_id: str = ""
    display_name: str = ""


@runtime_checkable
class Source(Protocol):
    """資料來源的結構化介面（AC-030 的六項成員）。"""

    id: str
    display_name: str
    supported_intervals: tuple[str, ...]
    needs_api_key: bool

    def search(self, query: str, limit: int = 20) -> list[Instrument]:
        """以關鍵字查詢商品；無結果時回傳空清單。"""
        ...

    def fetch(self, symbol: str, interval: str) -> pd.DataFrame:
        """取得符合 Series 契約的序列；失敗時丟出 `SourceError`。"""
        ...


#: 已註冊來源，鍵為 `source.id`。
_SOURCES: dict[str, Source] = {}


def _validate(source: Source) -> None:
    """在進入 registry 前先驗證結構，避免半殘的來源被後續查詢用到。"""
    for member in ("id", "display_name"):
        value = getattr(source, member, None)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"來源的 {member} 必須是非空字串，收到 {value!r}")

    intervals = getattr(source, "supported_intervals", None)
    if not isinstance(intervals, Sequence) or isinstance(intervals, (str, bytes)):
        raise ConfigError(
            f"來源 {source.id!r} 的 supported_intervals 必須是序列，"
            f"收到 {type(intervals).__name__}"
        )
    if len(intervals) == 0:
        raise ConfigError(f"來源 {source.id!r} 的 supported_intervals 不得為空")
    for item in intervals:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(
                f"來源 {source.id!r} 的 supported_intervals 只能是字串，收到 {item!r}"
            )

    if not isinstance(getattr(source, "needs_api_key", None), bool):
        raise ConfigError(f"來源 {source.id!r} 的 needs_api_key 必須是布林值")

    for member in ("search", "fetch"):
        if not callable(getattr(source, member, None)):
            raise ConfigError(f"來源 {source.id!r} 缺少可呼叫的 {member}")


def register(source: Source, *, replace: bool = False) -> None:
    """註冊來源；id 重複時預設丟出 `ConfigError`（`replace=True` 才覆寫）。"""
    _validate(source)
    if source.id in _SOURCES and not replace:
        raise ConfigError(
            f"來源 id {source.id!r} 已註冊；如需覆寫請使用 replace=True"
            f"（已註冊：{sorted(_SOURCES)}）"
        )
    _SOURCES[source.id] = source


def unregister(source_id: str) -> None:
    """移除來源；未註冊的 id 丟出 `ConfigError`。"""
    if source_id not in _SOURCES:
        raise ConfigError(
            f"找不到來源 {source_id!r}；可用來源：{sorted(_SOURCES)}"
        )
    del _SOURCES[source_id]


def get_source(source_id: str) -> Source:
    """查詢來源；未註冊時丟出可讀的 `ConfigError`（訊息含查詢的 id 與可用 id）。"""
    try:
        return _SOURCES[source_id]
    except KeyError as error:
        raise ConfigError(
            f"找不到來源 {source_id!r}；可用來源：{sorted(_SOURCES)}"
        ) from error


def all_sources() -> tuple[Source, ...]:
    """列出已註冊來源，以 `id` 排序讓輸出穩定。"""
    return tuple(_SOURCES[key] for key in sorted(_SOURCES))


def parse_iso_day(value: object) -> dt.date:
    """把西元日期解析成 `date`：接受 `date`／`datetime`／`YYYY-MM-DD`／`YYYYMMDD`。

    民國年日期是台灣特有的格式，由 `markets.twse.parse_roc_date` 負責；本函式只處理
    西元格式，供 `markets.adjust`（除權息區間）與 `markets.calendar`（開休市日期）共用。
    """
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        text = value.strip().replace("-", "").replace("/", "")
        if len(text) == 8 and text.isdigit():
            try:
                return dt.date(int(text[:4]), int(text[4:6]), int(text[6:8]))
            except ValueError as error:
                raise ConfigError(f"日期無法解讀：{value!r}（{error}）") from error
    raise ConfigError(f"日期必須是 date 或 YYYY-MM-DD／YYYYMMDD 字串，收到 {value!r}")
