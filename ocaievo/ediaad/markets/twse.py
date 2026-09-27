"""臺灣證券交易所（TWSE）日線來源與商品搜尋（AC-032、AC-033）。

**台股只有日線**（報告第 7.3 節），因此 `supported_intervals` 固定為 `("1d",)`；要求其他
週期一律是設定錯誤（`ConfigError`），訊息指出來源與該來源可用的週期。

TWSE 的兩個公開端點各有怪癖，解析集中在本模組：

- `STOCK_DAY`：回應是 `{stat, date, title, fields, data, notes, total}`，**欄位是中文名、
  資料是位置陣列**，日期為民國年（`113/07/01`），數字帶千分位（`20,936,005`）。因此解析先
  以 `fields` 找出中文欄名的位置，再逐列取值——不寫死欄序。
- `STOCK_DAY_ALL`／`t18707_L`：商品目錄，用來支援「以中文名或代號搜尋」。

只用公開端點、不需要金鑰；HTTP 客戶端與時鐘皆可注入（SPEC 第 5 節原則 2），測試全程離線。
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.request
from typing import Any, Callable

import pandas as pd

from ..data import from_rows
from ..errors import ConfigError, DataFormatError, SourceError
from .base import Instrument, register

__all__ = [
    "LISTED_COMPANIES_URL",
    "STOCK_DAY_ALL_URL",
    "STOCK_DAY_URL",
    "TwseSource",
    "parse_roc_date",
    "to_float",
]

STOCK_DAY_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
STOCK_DAY_ALL_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL"
LISTED_COMPANIES_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"

#: TWSE 支援的週期（只有日線）。
SUPPORTED_INTERVALS: tuple[str, ...] = ("1d",)

DEFAULT_LIMIT = 31  # 一個月的交易日上限
HTTP_TIMEOUT = 10.0

HttpClient = Callable[[str], Any]

#: `STOCK_DAY` 的中文欄位名 → 序列契約欄位。
_FIELD_TO_COLUMN: dict[str, str] = {
    "日期": "time",
    "成交股數": "volume",
    "開盤價": "open",
    "最高價": "high",
    "最低價": "low",
    "收盤價": "close",
}


def _default_client(url: str) -> Any:
    """標準庫 HTTP 客戶端：取得 JSON（不引入 `requests` 等新依賴）。"""
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_roc_date(value: Any) -> dt.date:
    """把民國年日期轉成西元 `date`。

    支援 `113/07/01`（`STOCK_DAY`）、`1150923`（`STOCK_DAY_ALL`，七碼無分隔）與
    `113年07月01日`（除權息表）三種格式；民國年 + 1911 = 西元年。
    """
    text = str(value).strip()
    digits = text.replace("/", "").replace("-", "").replace("年", "").replace("月", "").replace("日", "")
    if not digits.isdigit():
        raise DataFormatError(f"民國年日期格式無法解讀：{value!r}")

    if len(digits) == 7:  # 1150923 → 115 年 09 月 23 日
        year, month, day = int(digits[:3]), int(digits[3:5]), int(digits[5:7])
    elif len(digits) == 8:  # 1130701 → 113 年 07 月 01 日
        year, month, day = int(digits[:3]), int(digits[3:5]), int(digits[5:7])
    elif len(digits) == 9:  # 113/07/01 → 113 年 07 月 01 日
        year, month, day = int(digits[:3]), int(digits[3:5]), int(digits[5:7])
    else:
        raise DataFormatError(f"民國年日期長度無法解讀：{value!r}")

    try:
        return dt.date(year + 1911, month, day)
    except ValueError as error:
        raise DataFormatError(f"民國年日期無法解讀：{value!r}（{error}）") from error


def to_float(value: Any) -> float:
    """把 TWSE 的數字字串轉成 float：去除千分位與空白，保留正負號。"""
    text = str(value).strip().replace(",", "")
    if not text:
        raise DataFormatError("數值欄位是空字串，無法轉換")
    try:
        return float(text)
    except ValueError as error:
        raise DataFormatError(f"數值欄位無法轉換：{value!r}") from error


def _require_interval(interval: str) -> str:
    if interval not in SUPPORTED_INTERVALS:
        raise ConfigError(
            f"來源 'twse' 不支援週期 {interval!r}；"
            f"可用週期：{list(SUPPORTED_INTERVALS)}（台股只有日線）"
        )
    return interval


def _require_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ConfigError(f"limit 必須是 >= 1 的整數或 None，收到 {limit!r}")
    return limit


def _require_symbol(symbol: str) -> str:
    if not isinstance(symbol, str) or not symbol.strip():
        raise ConfigError(f"symbol 必須是非空字串，收到 {symbol!r}")
    return symbol.strip().upper()


def _utc_today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def _month_stamp(day: dt.date) -> str:
    return f"{day.year:04d}{day.month:02d}01"


def _coerce_date(value: Any, clock: Callable[[], dt.date]) -> dt.date:
    if value is None:
        return clock()
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        text = value.strip().replace("-", "")
        try:
            return dt.datetime.strptime(text, "%Y%m%d").date()
        except ValueError as error:
            raise ConfigError(f"date 必須是 YYYY-MM-DD 或 YYYYMMDD，收到 {value!r}") from error
    raise ConfigError(f"date 必須是日期或字串，收到 {type(value).__name__}")


def _field_positions(fields: Any) -> dict[str, int]:
    """以中文欄名找出各欄位置；缺欄位時指出是哪一個（不寫死欄序）。"""
    if not isinstance(fields, list):
        raise SourceError(f"TWSE 回應缺少 fields 欄位清單，收到 {type(fields).__name__}")

    positions: dict[str, int] = {}
    for name, column in _FIELD_TO_COLUMN.items():
        try:
            positions[column] = fields.index(name)
        except ValueError as error:
            raise SourceError(
                f"TWSE 回應缺少欄位 {name!r}；實際欄位：{fields}"
            ) from error
    return positions


def _parse_stock_day(payload: Any) -> pd.DataFrame:
    """把 `STOCK_DAY` 回應轉成序列。

    任何「來源給了無法使用的內容」都化為 `SourceError`（exit 1 的來源失敗），而不是
    `DataFormatError`（exit 2 的輸入錯誤）——這樣監控迴圈才能把它當成單一商品的失敗，
    與 TASK-013 對 Binance 的選擇一致。
    """
    if not isinstance(payload, dict):
        raise SourceError(f"TWSE 回應必須是 JSON 物件，收到 {type(payload).__name__}")

    stat = payload.get("stat")
    if stat != "OK":
        raise SourceError(f"TWSE 回應狀態不是 OK：{stat!r}")

    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise SourceError("TWSE 回應沒有資料列（data 為空或不存在）")

    declared = payload.get("total")
    if declared is not None:
        try:
            expected = int(declared)
        except (TypeError, ValueError):
            expected = None
        if expected is not None and expected != len(rows):
            raise SourceError(
                f"TWSE 回應疑似被截斷：宣稱 {expected} 列，實際 {len(rows)} 列"
            )

    positions = _field_positions(payload.get("fields"))
    widest = max(positions.values())

    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) <= widest:
            raise SourceError(f"TWSE 第 {index} 列欄位不足：{row!r}")
        record: dict[str, Any] = {}
        for column, position in positions.items():
            value = row[position]
            try:
                record[column] = (
                    parse_roc_date(value) if column == "time" else to_float(value)
                )
            except DataFormatError as error:
                raise SourceError(f"TWSE 第 {index} 列無法解讀：{error}") from error
        records.append(record)
    return from_rows(records)


def _get_json(getter: HttpClient, url: str, label: str) -> Any:
    try:
        return getter(url)
    except Exception as error:  # 注入的客戶端是外部邊界
        raise SourceError(f"TWSE {label}請求失敗：{error}") from error


def _require_records(payload: Any, label: str) -> list[Any]:
    if not isinstance(payload, list):
        raise SourceError(
            f"TWSE {label}回應必須是 JSON 陣列，收到 {type(payload).__name__}"
        )
    return payload


def _merge_directory(records: Any, listed: Any) -> dict[str, dict[str, Any]]:
    """合併「當日行情」與「上市公司目錄」，鍵為代號。

    兩個端點互補：`STOCK_DAY_ALL` 含 ETF 等非公司證券，`t18707_L` 有公司簡稱（搜尋
    「台泥」這種簡稱才找得到）。顯示名稱的優先序為 公司簡稱 ＞ 當日行情的名稱 ＞ 公司全名。
    """
    entries: dict[str, dict[str, Any]] = {}

    def record_for(code: str) -> dict[str, Any]:
        return entries.setdefault(code, {"names": set(), "display": "", "priority": 99})

    def offer(record: dict[str, Any], candidate: str, priority: int) -> None:
        if candidate and priority < record["priority"]:
            record["display"] = candidate
            record["priority"] = priority

    for item in records:
        if not isinstance(item, dict):
            continue
        code = str(item.get("Code", "")).strip()
        if not code:
            continue
        name = str(item.get("Name", "")).strip()
        record = record_for(code)
        if name:
            record["names"].add(name)
        offer(record, name, 1)

    for item in listed:
        if not isinstance(item, dict):
            continue
        code = str(item.get("公司代號", "")).strip()
        if not code:
            continue
        full = str(item.get("公司名稱", "")).strip()
        short = str(item.get("公司簡稱", "")).strip()
        record = record_for(code)
        for name in (full, short):
            if name:
                record["names"].add(name)
        offer(record, short, 0)
        offer(record, full, 2)

    return entries


class TwseSource:
    """`Source` 協定的 TWSE 實作（只有日線、不需要金鑰）。"""

    id = "twse"
    display_name = "臺灣證券交易所（上市日線）"
    supported_intervals = SUPPORTED_INTERVALS
    needs_api_key = False

    def fetch(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int | None = DEFAULT_LIMIT,
        date: Any = None,
        client: HttpClient | None = None,
        now: Callable[[], dt.date] | None = None,
    ) -> pd.DataFrame:
        """取得 `symbol` 在指定月份（預設為 `now()` 當月）的日線。"""
        code = _require_symbol(symbol)
        _require_interval(interval)
        wanted = _require_limit(limit)
        clock = now if now is not None else _utc_today
        day = _coerce_date(date, clock)
        getter = client if client is not None else _default_client

        url = f"{STOCK_DAY_URL}?response=json&date={_month_stamp(day)}&stockNo={code}"
        try:
            payload = getter(url)
        except Exception as error:
            raise SourceError(f"TWSE 請求失敗：{error}") from error

        series = _parse_stock_day(payload)
        if wanted is None:
            return series
        # 與 Binance 的 limit 語意一致：取最近 N 根，維持時間升冪。
        return series.iloc[-wanted:].reset_index(drop=True)

    def search(
        self, query: str, limit: int = 20, *, client: HttpClient | None = None
    ) -> list[Instrument]:
        """以代號或中文名（公司簡稱／公司全名）搜尋，回傳含代號與名稱的清單。

        同時查「當日行情」（含 ETF）與「上市公司目錄」（有公司簡稱），合併後以代號去重、
        依代號排序。兩個端點都必須成功——搜尋結果不完整卻不告知，比直接失敗更糟。
        """
        text = query.strip().upper()
        if not text or limit < 1:
            return []

        getter = client if client is not None else _default_client
        listed = _require_records(
            _get_json(getter, LISTED_COMPANIES_URL, "公司目錄"), "公司目錄"
        )
        quotes = _require_records(
            _get_json(getter, STOCK_DAY_ALL_URL, "當日行情"), "當日行情"
        )
        entries = _merge_directory(quotes, listed)

        results: list[Instrument] = []
        for code in sorted(entries):
            record = entries[code]
            if text in code.upper() or any(text in name.upper() for name in record["names"]):
                results.append(
                    Instrument(
                        symbol=code,
                        interval="",
                        source_id=self.id,
                        display_name=record["display"] or code,
                    )
                )
                if len(results) >= limit:
                    break
        return results


register(TwseSource())
