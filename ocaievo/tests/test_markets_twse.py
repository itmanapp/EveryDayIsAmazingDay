"""`ediaad.markets.twse`：TWSE 日線來源與商品搜尋（TASK-014）。

觀察邊界：只呼叫模組級 `parse_roc_date`／`to_float`、模組常數 `STOCK_DAY_URL` 等，以及
`get_source("twse").fetch`／`search`；HTTP 以假客戶端注入，全程離線。假回應的欄位名與
樣本值照 `docs/workflow/evidence/twse-probe/twse-endpoints.json`（2026-09-24 實測存證）
建立，但**不直接讀取該檔**（依 `PROJECT.md`，它是存證而非測試輸入）。
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from ediaad.data import SERIES_COLUMNS
from ediaad.errors import ConfigError, DataFormatError, SourceError
from ediaad.markets.base import get_source

STOCK_DAY_FIELDS = [
    "日期",
    "成交股數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌價差",
    "成交筆數",
    "註記",
]


class FakeHttp:
    """假 HTTP 客戶端：依 URL 片段分派不同 payload，並記錄請求。"""

    def __init__(self, routes: dict[str, object] | None = None, error: Exception | None = None):
        self.routes = routes or {}
        self.error = error
        self.calls: list[str] = []

    def __call__(self, url: str):
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        for fragment, payload in self.routes.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"假客戶端沒有對應的 route：{url}")

    @property
    def count(self) -> int:
        return len(self.calls)


def stock_day_row(date: str, volume: str, open_: str, high: str, low: str, close: str) -> list[str]:
    return [date, volume, "0", open_, high, low, close, "+0.00", "0", ""]


def stock_day_payload(
    rows: list[list[str]] | None = None,
    *,
    stat: str = "OK",
    total: int | str | None = None,
    fields: list[str] | None = None,
) -> dict:
    if rows is None:
        rows = [
            stock_day_row("113/07/01", "20,936,005", "968.00", "977.00", "965.00", "968.00"),
            stock_day_row("113/07/02", "27,992,930", "967.00", "971.00", "959.00", "960.00"),
        ]
    payload = {
        "stat": stat,
        "date": "20240701",
        "title": "113年07月 2330 台積電           各日成交資訊",
        "fields": STOCK_DAY_FIELDS if fields is None else fields,
        "data": rows,
        "notes": ["符號說明:+/-/X表示漲/跌/不比價"],
    }
    payload["total"] = len(rows) if total is None else total
    return payload


# ---- AC-032：STOCK_DAY 解析 -------------------------------------------------


def test_fetch_converts_roc_dates_and_thousands_separators():
    source = get_source("twse")
    http = FakeHttp({"STOCK_DAY": stock_day_payload()})

    series = source.fetch("2330", "1d", client=http)

    assert list(series.columns) == list(SERIES_COLUMNS)
    assert str(series["time"].dtype) == "datetime64[ns, UTC]"
    assert series["time"].iloc[0] == pd.Timestamp("2024-07-01", tz="UTC")
    assert series["time"].iloc[1] == pd.Timestamp("2024-07-02", tz="UTC")
    assert series["volume"].iloc[0] == pytest.approx(20_936_005.0)
    assert series["open"].iloc[0] == pytest.approx(968.0)
    assert series["high"].iloc[0] == pytest.approx(977.0)
    assert series["low"].iloc[0] == pytest.approx(965.0)
    assert series["close"].iloc[0] == pytest.approx(968.0)


def test_fetch_maps_every_price_column_from_its_named_field():
    rows = [stock_day_row("113/07/01", "1,000", "10.00", "12.00", "9.50", "11.00")]
    http = FakeHttp({"STOCK_DAY": stock_day_payload(rows)})

    series = get_source("twse").fetch("2330", "1d", client=http)

    row = series.iloc[0]
    assert (row["open"], row["high"], row["low"], row["close"]) == (10.0, 12.0, 9.5, 11.0)
    assert row["volume"] == pytest.approx(1000.0)


def test_fetch_requests_stock_day_for_the_symbol_and_month():
    from ediaad.markets.twse import STOCK_DAY_URL

    http = FakeHttp({"STOCK_DAY": stock_day_payload()})

    get_source("twse").fetch("2330", "1d", date="2024-07-15", client=http)

    assert http.count == 1
    url = http.calls[0]
    assert url.startswith(STOCK_DAY_URL)
    assert "stockNo=2330" in url
    assert "date=20240701" in url, "無論指定月中的哪一天，都查該月的第一天"


def test_fetch_defaults_to_the_month_of_the_injected_clock():
    http = FakeHttp({"STOCK_DAY": stock_day_payload()})

    get_source("twse").fetch("2330", "1d", client=http, now=lambda: dt.date(2025, 3, 20))

    assert "date=20250301" in http.calls[0]


def test_fetch_sorts_ascending_by_time():
    rows = [
        stock_day_row("113/07/03", "1,000", "10.00", "12.00", "9.50", "11.00"),
        stock_day_row("113/07/01", "1,000", "10.00", "12.00", "9.50", "11.00"),
        stock_day_row("113/07/02", "1,000", "10.00", "12.00", "9.50", "11.00"),
    ]
    series = get_source("twse").fetch("2330", "1d", client=FakeHttp({"STOCK_DAY": stock_day_payload(rows)}))

    assert series["time"].is_monotonic_increasing
    assert [str(stamp.date()) for stamp in series["time"]] == [
        "2024-07-01",
        "2024-07-02",
        "2024-07-03",
    ]


def test_the_source_is_registered_and_declares_daily_only():
    source = get_source("twse")

    assert source.id == "twse"
    assert source.display_name.strip()
    assert source.needs_api_key is False
    assert tuple(source.supported_intervals) == ("1d",)
    for member in ("search", "fetch"):
        assert callable(getattr(source, member))


# ---- 民國年與千分位輔助函式 -------------------------------------------------


def test_parse_roc_date_accepts_slash_compact_and_chinese_forms():
    from ediaad.markets.twse import parse_roc_date

    assert parse_roc_date("113/07/01") == dt.date(2024, 7, 1)
    assert parse_roc_date("1150923") == dt.date(2026, 9, 23)
    assert parse_roc_date(" 113/07/01 ") == dt.date(2024, 7, 1)
    # 除權息表（TASK-015）用的是「113年07月01日」
    assert parse_roc_date("113年07月01日") == dt.date(2024, 7, 1)
    assert parse_roc_date("113年12月31日") == dt.date(2024, 12, 31)


def test_to_float_strips_thousands_separators_and_signs():
    from ediaad.markets.twse import to_float

    assert to_float("20,936,005") == pytest.approx(20_936_005.0)
    assert to_float("+2.00") == pytest.approx(2.0)
    assert to_float(" -8.00 ") == pytest.approx(-8.0)
    assert to_float("0.0800") == pytest.approx(0.08)


# ---- AC-032：錯誤與邊界 -----------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(stock_day_payload(stat="很抱歉，沒有符合條件的資料!"), id="stat 非 OK"),
        pytest.param(stock_day_payload([]), id="data 為空"),
        pytest.param({"stat": "OK", "fields": STOCK_DAY_FIELDS}, id="缺 data"),
        pytest.param({"stat": "OK", "data": []}, id="缺 fields"),
        pytest.param([], id="回應是陣列"),
        pytest.param("not json", id="回應是字串"),
        pytest.param(None, id="回應是 None"),
    ],
)
def test_a_bad_stock_day_response_is_a_readable_source_error(payload):
    source = get_source("twse")

    with pytest.raises(SourceError) as excinfo:
        source.fetch("2330", "1d", client=FakeHttp({"STOCK_DAY": payload}))

    assert "TWSE" in str(excinfo.value)


def test_a_total_mismatch_is_a_truncated_response_error():
    payload = stock_day_payload(total=21)  # 只有 2 列卻宣稱 21 列

    with pytest.raises(SourceError) as excinfo:
        get_source("twse").fetch("2330", "1d", client=FakeHttp({"STOCK_DAY": payload}))

    assert "21" in str(excinfo.value), "訊息必須同時指出宣稱與實際的筆數"
    assert "2" in str(excinfo.value)


def test_a_total_that_matches_is_accepted():
    payload = stock_day_payload(total="2")  # 字串型別的 total 也要能比對

    series = get_source("twse").fetch("2330", "1d", client=FakeHttp({"STOCK_DAY": payload}))

    assert len(series) == 2


def test_a_missing_chinese_field_is_reported_by_name():
    fields = [name for name in STOCK_DAY_FIELDS if name != "成交股數"]
    payload = stock_day_payload(fields=fields)

    with pytest.raises(SourceError) as excinfo:
        get_source("twse").fetch("2330", "1d", client=FakeHttp({"STOCK_DAY": payload}))

    assert "成交股數" in str(excinfo.value)


def test_a_row_shorter_than_the_field_list_is_reported():
    payload = stock_day_payload([["113/07/01", "1,000", "0"]])

    with pytest.raises(SourceError) as excinfo:
        get_source("twse").fetch("2330", "1d", client=FakeHttp({"STOCK_DAY": payload}))

    assert "113/07/01" in str(excinfo.value) or "第 0 列" in str(excinfo.value)


def test_a_non_numeric_price_is_a_source_error_not_a_format_error():
    rows = [stock_day_row("113/07/01", "1,000", "N/A", "12.00", "9.50", "11.00")]
    payload = stock_day_payload(rows)

    with pytest.raises(SourceError):
        get_source("twse").fetch("2330", "1d", client=FakeHttp({"STOCK_DAY": payload}))


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(OSError("network down"), id="網路錯誤"),
        pytest.param(ValueError("invalid JSON"), id="解碼失敗"),
        pytest.param(RuntimeError("HTTP 500"), id="非預期例外"),
    ],
)
def test_any_exception_from_the_injected_client_is_a_source_error(error):
    with pytest.raises(SourceError, match="TWSE"):
        get_source("twse").fetch("2330", "1d", client=FakeHttp(error=error))


@pytest.mark.parametrize("interval", ["1h", "1m", "1w", ""])
def test_an_unsupported_interval_names_the_source_and_the_interval(interval):
    with pytest.raises(ConfigError) as excinfo:
        get_source("twse").fetch("2330", interval, client=FakeHttp())

    message = str(excinfo.value)
    assert "twse" in message, "訊息必須指出來源"
    assert repr(interval) in message or interval == "", "訊息必須指出週期"
    assert "1d" in message, "訊息必須指出該來源可用的週期"


@pytest.mark.parametrize(
    ("kwargs", "mentions"),
    [
        pytest.param({"symbol": ""}, "symbol", id="空商品代號"),
        pytest.param({"symbol": "   "}, "symbol", id="空白商品代號"),
        pytest.param({"limit": 0}, "limit", id="limit 為 0"),
        pytest.param({"limit": -3}, "limit", id="limit 為負"),
        pytest.param({"limit": True}, "limit", id="limit 為布林"),
        pytest.param({"date": "2024/07/01"}, "date", id="date 用斜線"),
        pytest.param({"date": 20240701}, "date", id="date 是數字"),
    ],
)
def test_invalid_arguments_are_config_errors(kwargs, mentions):
    arguments = {"symbol": "2330", "interval": "1d", **kwargs}

    with pytest.raises(ConfigError, match=mentions):
        get_source("twse").fetch(client=FakeHttp({"STOCK_DAY": stock_day_payload()}), **arguments)


def test_limit_none_returns_the_whole_month():
    # 刻意用 7 列：若有任何預設截斷（例如 5 筆）就會被抓到。
    rows = [
        stock_day_row(f"113/07/{day:02d}", "1,000", "10.00", "12.00", "9.50", "11.00")
        for day in range(1, 8)
    ]

    series = get_source("twse").fetch(
        "2330", "1d", limit=None, client=FakeHttp({"STOCK_DAY": stock_day_payload(rows)})
    )

    assert len(series) == 7
    assert str(series["time"].iloc[0].date()) == "2024-07-01"
    assert str(series["time"].iloc[-1].date()) == "2024-07-07"


def test_limit_keeps_the_most_recent_rows_in_ascending_order():
    rows = [
        stock_day_row(f"113/07/{day:02d}", "1,000", "10.00", "12.00", "9.50", "11.00")
        for day in range(1, 6)
    ]

    series = get_source("twse").fetch(
        "2330", "1d", limit=2, client=FakeHttp({"STOCK_DAY": stock_day_payload(rows)})
    )

    assert [str(stamp.date()) for stamp in series["time"]] == ["2024-07-04", "2024-07-05"]
    assert series["time"].is_monotonic_increasing


# ---- AC-033：以代號或中文名搜尋 ---------------------------------------------

# 照存證的欄位名建立的小型假回應：`STOCK_DAY_ALL` 是當日全體上市證券（含 ETF），
# `t18707_L` 是上市公司目錄（有公司簡稱，但不含 ETF）。
STOCK_DAY_ALL_SAMPLE = [
    {
        "Date": "1150923",
        "Code": "1101",
        "Name": "台泥",
        "TradeVolume": "27029269",
        "TradeValue": "420875551",
        "OpeningPrice": "15.58",
        "HighestPrice": "15.63",
        "LowestPrice": "15.51",
        "ClosingPrice": "15.57",
        "Change": "0.0800",
        "Transaction": "5522",
    },
    {
        "Date": "1150923",
        "Code": "2330",
        "Name": "台積電",
        "TradeVolume": "20936005",
        "TradeValue": "20320957284",
        "OpeningPrice": "968.00",
        "HighestPrice": "977.00",
        "LowestPrice": "965.00",
        "ClosingPrice": "968.00",
        "Change": "2.0000",
        "Transaction": "38293",
    },
    {
        "Date": "1150923",
        "Code": "0050",
        "Name": "元大台灣50",
        "TradeVolume": "1000",
        "TradeValue": "1000",
        "OpeningPrice": "150.00",
        "HighestPrice": "151.00",
        "LowestPrice": "149.00",
        "ClosingPrice": "150.50",
        "Change": "0.5000",
        "Transaction": "10",
    },
    {"Date": "1150923", "Name": "沒有代號的項目"},
]

LISTED_COMPANIES_SAMPLE = [
    {
        "出表日期": "1150923",
        "公司代號": "1101",
        "公司名稱": "臺灣水泥股份有限公司",
        "公司簡稱": "台泥",
        "產業別": "01",
    },
    {
        "出表日期": "1150923",
        "公司代號": "2330",
        "公司名稱": "台灣積體電路製造股份有限公司",
        "公司簡稱": "台積電",
        "產業別": "24",
    },
    {
        "出表日期": "1150923",
        "公司代號": "9999",
        "公司名稱": "僅在目錄出現的股份有限公司",
        "公司簡稱": "目錄公司",
        "產業別": "99",
    },
    {"出表日期": "1150923", "公司簡稱": "沒有代號"},
]


def directory_http(*, stock_day_all=None, listed=None) -> FakeHttp:
    if isinstance(stock_day_all, Exception) or isinstance(listed, Exception):
        return FakeHttp(
            {
                "STOCK_DAY_ALL": stock_day_all if isinstance(stock_day_all, Exception) else STOCK_DAY_ALL_SAMPLE,
                "t187ap03_L": listed if isinstance(listed, Exception) else LISTED_COMPANIES_SAMPLE,
            }
        )
    return FakeHttp(
        {
            "STOCK_DAY_ALL": STOCK_DAY_ALL_SAMPLE if stock_day_all is None else stock_day_all,
            "t187ap03_L": LISTED_COMPANIES_SAMPLE if listed is None else listed,
        }
    )


def test_search_matches_by_code():
    results = get_source("twse").search("2330", client=directory_http())

    assert [item.symbol for item in results] == ["2330"]
    assert results[0].source_id == "twse"
    assert results[0].interval == ""
    assert results[0].display_name == "台積電"


def test_search_matches_by_chinese_short_name():
    results = get_source("twse").search("台泥", client=directory_http())

    assert [item.symbol for item in results] == ["1101"]
    assert results[0].display_name == "台泥"


def test_search_matches_by_chinese_full_name():
    """「臺灣水泥」只在 `t18707_L` 的公司名稱裡——證明目錄端點真的有被查。"""
    results = get_source("twse").search("臺灣水泥", client=directory_http())

    assert [item.symbol for item in results] == ["1101"]


def test_search_finds_an_etf_that_only_exists_in_stock_day_all():
    """ETF 不在上市公司目錄裡——證明 `STOCK_DAY_ALL` 真的有被查。"""
    results = get_source("twse").search("0050", client=directory_http())

    assert [item.symbol for item in results] == ["0050"]
    assert results[0].display_name == "元大台灣50"


def test_search_finds_a_company_that_only_exists_in_the_directory():
    results = get_source("twse").search("目錄公司", client=directory_http())

    assert [item.symbol for item in results] == ["9999"]


def test_search_dedups_by_code_and_prefers_the_short_name():
    """`台積` 同時命中兩個端點的 2330；結果只出現一次，且顯示名稱用公司簡稱。"""
    results = get_source("twse").search("台積", client=directory_http())

    assert [item.symbol for item in results] == ["2330"]
    assert results[0].display_name == "台積電"


def test_search_returns_matches_sorted_by_code():
    results = get_source("twse").search("台", client=directory_http())

    assert [item.symbol for item in results] == ["0050", "1101", "2330"]




def test_search_matches_letter_codes_case_insensitively():
    payload = STOCK_DAY_ALL_SAMPLE + [
        {"Date": "1150923", "Code": "00400A", "Name": "主動國泰動能高息"}
    ]
    results = get_source("twse").search("00400a", client=directory_http(stock_day_all=payload))

    assert [item.symbol for item in results] == ["00400A"]


def test_search_strips_the_query():
    results = get_source("twse").search("  2330  ", client=directory_http())

    assert [item.symbol for item in results] == ["2330"]


def test_search_returns_nothing_for_an_empty_query_without_any_request():
    http = directory_http()

    assert get_source("twse").search("", client=http) == []
    assert get_source("twse").search("   ", client=http) == []
    assert get_source("twse").search("", limit=5, client=http) == []
    assert http.count == 0, "空查詢不應發出請求"


def test_search_respects_the_limit():
    source = get_source("twse")

    assert source.search("台", limit=0, client=directory_http()) == []
    assert [item.symbol for item in source.search("台", limit=1, client=directory_http())] == [
        "0050"
    ], "limit 取排序後的前 N 筆"
    assert len(source.search("台", limit=2, client=directory_http())) == 2


def test_search_requests_both_directory_endpoints():
    from ediaad.markets.twse import LISTED_COMPANIES_URL, STOCK_DAY_ALL_URL

    http = directory_http()
    get_source("twse").search("台泥", client=http)

    assert http.count == 2
    assert any(url.startswith(STOCK_DAY_ALL_URL) for url in http.calls)
    assert any(url.startswith(LISTED_COMPANIES_URL) for url in http.calls)


@pytest.mark.parametrize(
    ("stock_day_all", "listed"),
    [
        pytest.param(OSError("down"), None, id="STOCK_DAY_ALL 失敗"),
        pytest.param(None, OSError("down"), id="公司目錄失敗"),
        pytest.param("not json", None, id="STOCK_DAY_ALL 不是陣列"),
        pytest.param(None, {"symbols": []}, id="公司目錄不是陣列"),
    ],
)
def test_a_directory_failure_is_a_readable_source_error(stock_day_all, listed):
    with pytest.raises(SourceError) as excinfo:
        get_source("twse").search("台泥", client=directory_http(stock_day_all=stock_day_all, listed=listed))

    assert "TWSE" in str(excinfo.value)


# ---- 補測：任務計畫列出的邊界 -----------------------------------------------


def test_the_change_and_note_columns_never_break_parsing():
    """`漲跌價差` 可能是 `X`（不比價）、`註記` 可能是 `**` 或空字串——本張不讀這三欄。"""
    rows = [
        ["113/07/01", "20,936,005", "0", "968.00", "977.00", "965.00", "968.00", "X", "0", ""],
        ["113/07/02", "1,000", "0", "967.00", "971.00", "959.00", "960.00", "-8.00", "0", "**"],
        ["113/07/03", "2,000", "0", "960.00", "965.00", "955.00", "957.00", "+3.00", "0", "  "],
    ]

    series = get_source("twse").fetch(
        "2330", "1d", client=FakeHttp({"STOCK_DAY": stock_day_payload(rows)})
    )

    assert list(series["volume"]) == [20_936_005.0, 1000.0, 2000.0]
    assert list(series["close"]) == [968.0, 960.0, 957.0]


@pytest.mark.parametrize(
    "date",
    [
        pytest.param("2024-07-15", id="含連字號的字串"),
        pytest.param("20240715", id="緊湊字串"),
        pytest.param(dt.date(2024, 7, 15), id="date 物件"),
        pytest.param(dt.datetime(2024, 7, 15, 23, 30), id="datetime 物件"),
    ],
)
def test_fetch_accepts_several_date_forms(date):
    http = FakeHttp({"STOCK_DAY": stock_day_payload()})

    get_source("twse").fetch("2330", "1d", date=date, client=http)

    assert "date=20240701" in http.calls[0]


def test_search_dedups_a_code_repeated_inside_one_endpoint():
    payload = STOCK_DAY_ALL_SAMPLE + [
        {"Date": "1150923", "Code": "2330", "Name": "台積電"},
    ]

    results = get_source("twse").search("2330", client=directory_http(stock_day_all=payload))

    assert [item.symbol for item in results] == ["2330"]
