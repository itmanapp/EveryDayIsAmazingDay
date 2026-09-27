"""台股除權息還原與交易日曆（TASK-015）。

觀察邊界：`fetch_ex_rights`／`adjust_series`／`load_twse_calendar`／
`TradingCalendar.is_trading_day`／`apply_calendar`／`default_spec_for` 的公開結果，
以及 AC-034 要求的 **`patterns.detect` 命中差異**（還原後不命中、未還原會假命中）。
假回應的欄位名照 `docs/workflow/evidence/twse-probe/twse-endpoints.json` 的實測存證
建立，但**不讀取該檔**。全程離線。
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from ediaad.data import SERIES_COLUMNS, from_rows
from ediaad.errors import ConfigError, SourceError
from ediaad.patterns import NAMED_PATTERNS, PatternSpec, detect

EXRIGHTS_FIELDS = [
    "資料日期",
    "股票代號",
    "股票名稱",
    "除權息前收盤價",
    "除權息參考價",
    "權值+息值",
    "權/息",
    "漲停價格",
    "跌停價格",
    "開盤競價基準",
    "減除股利參考價",
    "詳細資料",
]


class FakeHttp:
    """假 HTTP 客戶端：依 URL 片段分派 payload。"""

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


def exrights_row(
    date: str = "113年07月01日",
    code: str = "1101",
    name: str = "台泥",
    pre_close: str = "34.20",
    reference: str = "33.20",
    value: str = "1.000000",
    kind: str = "息",
) -> list[str]:
    return [date, code, name, pre_close, reference, value, kind, "36.50", "29.90", reference, reference]


def exrights_payload(rows: list[list[str]] | None = None, *, stat: str = "OK") -> dict:
    return {
        "stat": stat,
        "title": "113年07月01日 至 113年07月31日 除權除息計算結果表",
        "fields": EXRIGHTS_FIELDS,
        "data": [exrights_row()] if rows is None else rows,
        "extraNotes": [],
        "notes": ["權值+息值=除權息前收盤價-除權息參考價"],
        "formula": [
            "除權息參考價 = (除權息前收盤價-息值+現金增資認購價*現金增資配股率)/(1+無償配股率+現金增資配股率)"
        ],
        "strDate": "20240701",
        "endDate": "20240731",
    }


def build_series(pairs: list[tuple[str, float]], *, spread: float = 0.5) -> pd.DataFrame:
    """由 `(ISO 日期, 收盤價)` 建立序列；開高低以 `spread` 對稱展開。"""
    rows = []
    for text, close in pairs:
        rows.append(
            {
                "time": dt.date.fromisoformat(text),
                "open": close,
                "high": close + spread,
                "low": close - spread,
                "close": close,
                "volume": 1000.0,
            }
        )
    return from_rows(rows)


def dividend_series() -> tuple[pd.DataFrame, list]:
    """盤整 → 除權息跳空 → 回歸均值：未還原時會被 `detect` 誤判為跌破。"""
    from ediaad.markets.adjust import ExRightsEvent

    rows = []
    day = dt.date(2024, 6, 3)
    for index in range(30):
        close = 99.0 if index % 2 == 0 else 100.5
        rows.append(
            {
                "time": day,
                "open": close - 0.2,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1000.0,
            }
        )
        day += dt.timedelta(days=1)

    ex_date = day
    rows.append({"time": ex_date, "open": 98.0, "high": 98.2, "low": 97.0, "close": 97.5, "volume": 1000.0})
    day += dt.timedelta(days=1)
    for close in (98.0, 99.2, 99.8, 100.3, 100.6):
        rows.append(
            {"time": day, "open": close, "high": close + 0.3, "low": close - 0.3, "close": close, "volume": 1000.0}
        )
        day += dt.timedelta(days=1)

    event = ExRightsEvent(
        symbol="1101",
        date=ex_date,
        pre_close=100.5,
        reference_price=98.5,
        value=2.0,
        kind="息",
    )
    return from_rows(rows), [event]


# ---- AC-034：除權息事件與還原 -----------------------------------------------


def test_fetch_ex_rights_parses_the_three_required_fields():
    from ediaad.markets.adjust import fetch_ex_rights

    events = fetch_ex_rights(
        "2024-07-01", "2024-07-31", client=FakeHttp({"TWT49U": exrights_payload()})
    )

    assert len(events) == 1
    event = events[0]
    assert event.symbol == "1101"
    assert event.date == dt.date(2024, 7, 1)
    assert event.pre_close == pytest.approx(34.20)
    assert event.reference_price == pytest.approx(33.20)
    assert event.value == pytest.approx(1.0)
    assert event.kind == "息"
    assert event.factor == pytest.approx(33.20 / 34.20)


def test_fetch_ex_rights_requests_the_documented_range_parameters():
    from ediaad.markets.adjust import EX_RIGHTS_URL, fetch_ex_rights

    http = FakeHttp({"TWT49U": exrights_payload()})
    fetch_ex_rights("2024-07-01", "2024-07-31", client=http)

    assert http.count == 1
    url = http.calls[0]
    assert url.startswith(EX_RIGHTS_URL)
    assert "startDate=20240701" in url
    assert "endDate=20240731" in url
    assert "strDate" not in url, "TWT49U 只認 startDate／endDate（ADR-003）"


def test_adjust_series_closes_the_dividend_gap():
    from ediaad.markets.adjust import adjust_series

    series = build_series([("2024-07-01", 100.0), ("2024-07-02", 98.5), ("2024-07-03", 98.6)])
    from ediaad.markets.adjust import ExRightsEvent

    event = ExRightsEvent(
        symbol="1101", date=dt.date(2024, 7, 2), pre_close=100.0, reference_price=98.5, value=1.5
    )

    result = adjust_series(series, [event])

    closes = list(result.series["close"])
    assert closes[0] == pytest.approx(98.5), "事件之前的價格要按參考價／前收盤價縮放"
    assert abs(closes[1] - closes[0]) < 1e-9, "除權息日不得再出現跳空"
    assert closes[2] == pytest.approx(98.6), "事件當日與之後的價格不動"
    assert result.applied == 1
    assert result.unavailable_dates == ()
    assert result.status == "adjusted"


def test_detect_hits_the_unadjusted_series_on_the_ex_date():
    """對照組：未還原的除權息跳空會被誤判為「向下跌破」。"""
    raw, events = dividend_series()
    spec = PatternSpec(**NAMED_PATTERNS["range_fakeout_reversion"])
    ex_date = events[0].date
    ex_index = int(raw.index[raw["time"].dt.date == ex_date][0])

    hits = detect(raw, spec)

    assert hits, "未還原序列必須產生假命中（這是本 AC 的對照）"
    assert any(hit.breakdown_index == ex_index for hit in hits)


def test_detect_does_not_hit_the_adjusted_series():
    from ediaad.markets.adjust import adjust_series

    raw, events = dividend_series()
    spec = PatternSpec(**NAMED_PATTERNS["range_fakeout_reversion"])

    adjusted = adjust_series(raw, events).series
    hits = detect(adjusted, spec)

    assert hits == [], f"還原後不得在除權息日產生假跌破；實際命中：{hits}"


def test_adjust_series_leaves_the_input_untouched():
    from ediaad.markets.adjust import ExRightsEvent, adjust_series

    series = build_series([("2024-07-01", 100.0), ("2024-07-02", 98.5)])
    before = series.copy(deep=True)
    event = ExRightsEvent(
        symbol="1101", date=dt.date(2024, 7, 2), pre_close=100.0, reference_price=98.5, value=1.5
    )

    adjust_series(series, [event])

    pd.testing.assert_frame_equal(series, before)
    assert list(series.columns) == list(SERIES_COLUMNS)


def test_an_event_before_every_bar_leaves_the_series_unchanged():
    """事件日早於第一根時沒有任何「事件之前的價格」要縮放。"""
    from ediaad.markets.adjust import ExRightsEvent, adjust_series

    series = build_series([("2024-07-01", 100.0), ("2024-07-02", 100.5)])
    event = ExRightsEvent(
        symbol="1101", date=dt.date(2023, 1, 1), pre_close=100.0, reference_price=90.0, value=10.0
    )

    result = adjust_series(series, [event])

    assert result.applied == 0
    assert result.status == "unchanged"
    assert list(result.series["close"]) == [100.0, 100.5]


def test_an_event_after_every_bar_scales_the_whole_series():
    """事件日晚於所有 K 線時，每一根都在事件之前，因此全部都要縮放。"""
    from ediaad.markets.adjust import ExRightsEvent, adjust_series

    series = build_series([("2024-07-01", 100.0), ("2024-07-02", 100.5)])
    event = ExRightsEvent(
        symbol="1101", date=dt.date(2025, 1, 1), pre_close=100.0, reference_price=90.0, value=10.0
    )

    result = adjust_series(series, [event])

    assert result.applied == 1
    assert result.status == "adjusted"
    assert list(result.series["close"]) == [pytest.approx(90.0), pytest.approx(90.45)]


def test_without_events_the_series_is_returned_unchanged():
    from ediaad.markets.adjust import adjust_series

    series = build_series([("2024-07-01", 100.0), ("2024-07-02", 100.5)])

    result = adjust_series(series, [])

    assert result.status == "unchanged"
    assert result.applied == 0
    assert result.unavailable_dates == ()
    pd.testing.assert_frame_equal(result.series, series)


# ---- AC-034：多次事件、無法還原的事件與錯誤路徑 -----------------------------


def test_two_events_compound_on_the_bars_before_both():
    from ediaad.markets.adjust import ExRightsEvent, adjust_series

    series = build_series(
        [("2024-07-01", 100.0), ("2024-07-02", 100.0), ("2024-07-03", 100.0), ("2024-07-04", 100.0)]
    )
    first = ExRightsEvent(
        symbol="1101", date=dt.date(2024, 7, 3), pre_close=100.0, reference_price=90.0, value=10.0
    )
    second = ExRightsEvent(
        symbol="1101", date=dt.date(2024, 7, 4), pre_close=90.0, reference_price=81.0, value=9.0
    )

    result = adjust_series(series, [first, second])

    closes = list(result.series["close"])
    assert closes[0] == pytest.approx(81.0), "兩次事件之前的價格要乘上兩個倍率"
    assert closes[1] == pytest.approx(81.0)
    assert closes[2] == pytest.approx(90.0), "只在前一次事件之前的價格乘一個倍率"
    assert closes[3] == pytest.approx(100.0), "事件當日不動"
    assert result.applied == 2
    assert result.status == "adjusted"


def test_events_are_applied_in_a_canonical_order_regardless_of_input_order():
    """SPEC 可重現性：「同一輸入與參數必須得到位元相同的結果」。

    浮點乘法不滿足交換律到最後一位：`100.5 × 0.9 × 0.8 = 72.36`，但
    `100.5 × 0.8 × 0.9 = 72.36000000000001`。因此事件必須先依日期排序再套用，
    否則同一組事件用不同順序傳入會得到**不同的位元**。這裡用精確比較（不是 approx）。
    """
    from ediaad.markets.adjust import ExRightsEvent, adjust_series

    series = build_series([("2024-07-01", 100.5), ("2024-07-02", 100.5), ("2024-07-03", 100.5)])
    earlier = ExRightsEvent(
        symbol="1101", date=dt.date(2024, 7, 2), pre_close=100.0, reference_price=90.0, value=10.0
    )
    later = ExRightsEvent(
        symbol="1101", date=dt.date(2024, 7, 3), pre_close=100.0, reference_price=80.0, value=20.0
    )

    forward = adjust_series(series, [earlier, later]).series
    backward = adjust_series(series, [later, earlier]).series

    assert list(forward["close"]) == list(backward["close"]), (
        "不同輸入順序必須得到位元相同的結果"
    )
    closes = list(forward["close"])
    assert closes[0] == pytest.approx(100.5 * 0.9 * 0.8)
    assert closes[1] == pytest.approx(100.5 * 0.8)
    assert closes[2] == 100.5


def test_an_event_with_a_non_positive_pre_close_is_marked_unavailable():
    from ediaad.markets.adjust import ExRightsEvent, adjust_series

    series = build_series([("2024-07-01", 100.0), ("2024-07-02", 100.0)])
    broken = ExRightsEvent(
        symbol="1101", date=dt.date(2024, 7, 2), pre_close=0.0, reference_price=0.0, value=0.0
    )

    result = adjust_series(series, [broken])

    assert result.applied == 0
    assert result.unavailable_dates == (dt.date(2024, 7, 2),)
    assert result.status == "unavailable"
    assert list(result.series["close"]) == [100.0, 100.0], "無法還原時保留原序列（方案 A）"


def test_a_mix_of_applicable_and_unavailable_events_is_partial():
    from ediaad.markets.adjust import ExRightsEvent, adjust_series

    series = build_series([("2024-07-01", 100.0), ("2024-07-02", 100.0), ("2024-07-03", 100.0)])
    good = ExRightsEvent(
        symbol="1101", date=dt.date(2024, 7, 2), pre_close=100.0, reference_price=90.0, value=10.0
    )
    broken = ExRightsEvent(
        symbol="1101", date=dt.date(2024, 7, 3), pre_close=-1.0, reference_price=90.0, value=10.0
    )

    result = adjust_series(series, [good, broken])

    assert result.applied == 1
    assert result.status == "partial"
    assert result.unavailable_dates == (dt.date(2024, 7, 3),)
    assert list(result.series["close"]) == [pytest.approx(90.0), 100.0, 100.0]


def test_an_event_without_a_kind_still_parses():
    from ediaad.markets.adjust import fetch_ex_rights

    fields = [name for name in EXRIGHTS_FIELDS if name != "權/息"]
    row = [value for name, value in zip(EXRIGHTS_FIELDS, exrights_row()) if name != "權/息"]
    payload = exrights_payload([row])
    payload["fields"] = fields

    events = fetch_ex_rights("2024-07-01", "2024-07-31", client=FakeHttp({"TWT49U": payload}))

    assert len(events) == 1
    assert events[0].kind == ""


def test_no_events_in_the_range_is_an_empty_list():
    from ediaad.markets.adjust import fetch_ex_rights

    for payload in (
        exrights_payload([]),
        {"stat": "很抱歉，沒有符合條件的資料!", "fields": EXRIGHTS_FIELDS, "data": []},
    ):
        events = fetch_ex_rights("2024-07-01", "2024-07-31", client=FakeHttp({"TWT49U": payload}))
        assert events == []


def test_fetch_ex_rights_filters_and_sorts_by_symbol():
    from ediaad.markets.adjust import fetch_ex_rights

    rows = [
        exrights_row(date="113年07月02日", code="2330", name="台積電", pre_close="1000.00", reference="996.00", value="4.00"),
        exrights_row(date="113年07月01日", code="1101", name="台泥"),
        exrights_row(date="113年07月01日", code="2330", name="台積電", pre_close="1000.00", reference="996.00", value="4.00"),
    ]
    http = FakeHttp({"TWT49U": exrights_payload(rows)})

    everything = fetch_ex_rights("2024-07-01", "2024-07-31", client=http)
    assert [(event.date, event.symbol) for event in everything] == [
        (dt.date(2024, 7, 1), "1101"),
        (dt.date(2024, 7, 1), "2330"),
        (dt.date(2024, 7, 2), "2330"),
    ]

    only_tsmc = fetch_ex_rights("2024-07-01", "2024-07-31", client=http, symbol=" 2330 ")
    assert [(event.date, event.symbol) for event in only_tsmc] == [
        (dt.date(2024, 7, 1), "2330"),
        (dt.date(2024, 7, 2), "2330"),
    ]


def test_a_reversed_range_is_rejected_without_a_request():
    from ediaad.markets.adjust import fetch_ex_rights

    http = FakeHttp({"TWT49U": exrights_payload()})

    with pytest.raises(ConfigError, match="結束日期"):
        fetch_ex_rights("2024-07-31", "2024-07-01", client=http)

    assert http.count == 0, "本地就能擋下的錯誤不應發出請求"


@pytest.mark.parametrize(
    ("payload", "mentions"),
    [
        pytest.param([], "物件", id="回應不是物件"),
        pytest.param({"stat": "error", "fields": EXRIGHTS_FIELDS, "data": [exrights_row()]}, "stat", id="stat 非 OK"),
        pytest.param({"stat": "OK", "data": [exrights_row()]}, "fields", id="缺 fields"),
        pytest.param(
            {"stat": "OK", "fields": [n for n in EXRIGHTS_FIELDS if n != "除權息參考價"], "data": [[1]]},
            "除權息參考價",
            id="缺必要欄位",
        ),
        pytest.param({"stat": "OK", "fields": EXRIGHTS_FIELDS, "data": "x"}, "data", id="data 不是陣列"),
        pytest.param({"stat": "OK", "fields": EXRIGHTS_FIELDS, "data": [["113年07月01日"]]}, "列", id="列長度不足"),
        pytest.param(
            {"stat": "OK", "fields": EXRIGHTS_FIELDS, "data": [exrights_row(pre_close="N/A")]},
            "數值",
            id="非數值欄位",
        ),
    ],
)
def test_a_bad_ex_rights_response_is_a_readable_source_error(payload, mentions):
    from ediaad.markets.adjust import fetch_ex_rights

    with pytest.raises(SourceError, match=mentions):
        fetch_ex_rights("2024-07-01", "2024-07-31", client=FakeHttp({"TWT49U": payload}))


def test_an_inconsistent_row_is_rejected_by_the_twse_formula():
    """TWSE 表附註：權值+息值 = 除權息前收盤價 - 除權息參考價。不符即代表解析錯欄。"""
    from ediaad.markets.adjust import fetch_ex_rights

    payload = exrights_payload([exrights_row(pre_close="34.20", reference="33.20", value="5.000000")])

    with pytest.raises(SourceError, match="權值"):
        fetch_ex_rights("2024-07-01", "2024-07-31", client=FakeHttp({"TWT49U": payload}))


@pytest.mark.parametrize(("value", "accepted"), [("1.010000", True), ("1.050000", False)])
def test_the_formula_tolerance_allows_cent_rounding(value, accepted):
    from ediaad.markets.adjust import fetch_ex_rights

    payload = exrights_payload([exrights_row(pre_close="34.20", reference="33.20", value=value)])
    http = FakeHttp({"TWT49U": payload})

    if accepted:
        assert len(fetch_ex_rights("2024-07-01", "2024-07-31", client=http)) == 1
    else:
        with pytest.raises(SourceError):
            fetch_ex_rights("2024-07-01", "2024-07-31", client=http)


@pytest.mark.parametrize(
    "error",
    [pytest.param(OSError("down"), id="網路"), pytest.param(ValueError("bad"), id="解碼"), pytest.param(RuntimeError("500"), id="非預期")],
)
def test_any_client_exception_is_a_source_error(error):
    from ediaad.markets.adjust import fetch_ex_rights

    with pytest.raises(SourceError, match="TWT49U|除權息"):
        fetch_ex_rights("2024-07-01", "2024-07-31", client=FakeHttp(error=error))


@pytest.mark.parametrize("value", ["2024-13-45", "113年07月01日", 7, None, "20240701x"])
def test_invalid_range_arguments_are_config_errors(value):
    from ediaad.markets.adjust import fetch_ex_rights

    with pytest.raises(ConfigError):
        fetch_ex_rights(value, "2024-07-31", client=FakeHttp({"TWT49U": exrights_payload()}))


@pytest.mark.parametrize("value", ["2024-07-01", "20240701", "2024/07/01", dt.date(2024, 7, 1), dt.datetime(2024, 7, 1, 9)])
def test_several_western_date_forms_are_accepted(value):
    """`parse_iso_day` 只處理西元格式；民國年由 `twse.parse_roc_date` 負責。"""
    from ediaad.markets.adjust import fetch_ex_rights

    http = FakeHttp({"TWT49U": exrights_payload()})
    fetch_ex_rights(value, "2024-07-31", client=http)

    assert "startDate=20240701" in http.calls[0]


# ---- AC-035：交易日曆與市場別預設 -------------------------------------------

HOLIDAY_FIELDS = ["日期", "名稱", "說明"]
HOLIDAY_ROWS = [
    ["2026-01-01", "中華民國開國紀念日", "依規定放假1日。"],
    ["2026-01-02", "國曆新年開始交易日", "國曆新年開始交易。"],
    ["2026-02-11", "農曆春節前最後交易日", "農曆春節前最後交易。\r\n"],
    ["2026-02-12", "市場無交易，僅辦理結算交割作業", ""],
    ["2026-02-13", "市場無交易，僅辦理結算交割作業", ""],
    ["2026-02-15", "農曆除夕及春節", "依規定於2月15日至2月19日放假5日。"],
    ["2026-02-23", "農曆春節後開始交易日", "農曆春節後開始交易。"],
]


def holiday_payload(rows: list[list[str]] | None = None, *, stat: str = "ok") -> dict:
    return {
        "stat": stat,
        "date": "20260101",
        "title": "115 年市場開休市日期",
        "fields": HOLIDAY_FIELDS,
        "data": HOLIDAY_ROWS if rows is None else rows,
        "queryYear": 2026,
        "total": len(HOLIDAY_ROWS if rows is None else rows),
    }


def test_load_twse_calendar_classifies_holidays_and_trading_days():
    from ediaad.markets.calendar import load_twse_calendar

    calendar = load_twse_calendar(holiday_payload())

    assert calendar.year == 2026
    assert dt.date(2026, 1, 1) in calendar.closed_dates
    assert dt.date(2026, 2, 12) in calendar.closed_dates
    assert dt.date(2026, 2, 13) in calendar.closed_dates
    assert dt.date(2026, 1, 2) not in calendar.closed_dates, "「開始交易日」不是休市日"
    assert dt.date(2026, 2, 11) not in calendar.closed_dates, "「最後交易日」不是休市日"
    assert dt.date(2026, 2, 23) not in calendar.closed_dates


def test_the_calendar_expands_a_holiday_range():
    """春節的說明寫成「2月15日至2月19日放假5日」，區間內的每一天都必須休市。

    否則 2/16～2/19 會被誤認為交易日（它們在回應中沒有各自的資料列）。
    """
    from ediaad.markets.calendar import load_twse_calendar

    calendar = load_twse_calendar(holiday_payload())

    for day in range(15, 20):
        assert dt.date(2026, 2, day) in calendar.closed_dates, f"2026-02-{day} 應為休市"


def test_is_trading_day_excludes_weekends_and_holidays():
    from ediaad.markets.calendar import load_twse_calendar

    calendar = load_twse_calendar(holiday_payload())

    assert calendar.is_trading_day(dt.date(2026, 2, 10)) is True  # 週二
    assert calendar.is_trading_day(dt.date(2026, 2, 11)) is True  # 週三（最後交易日）
    assert calendar.is_trading_day(dt.date(2026, 2, 12)) is False  # 市場無交易
    assert calendar.is_trading_day(dt.date(2026, 2, 14)) is False  # 週六
    assert calendar.is_trading_day(dt.date(2026, 2, 15)) is False  # 週日＋春節
    assert calendar.is_trading_day(dt.date(2026, 2, 16)) is False  # 春節區間（週一）
    assert calendar.is_trading_day(dt.date(2026, 2, 23)) is True  # 春節後開始交易日


def test_the_module_level_is_trading_day_matches_the_method():
    from ediaad.markets.calendar import is_trading_day, load_twse_calendar

    calendar = load_twse_calendar(holiday_payload())

    for text in ("2026-02-10", "2026-02-12", "2026-02-14", "2026-02-16", "2026-02-23"):
        day = dt.date.fromisoformat(text)
        assert is_trading_day(calendar, day) == calendar.is_trading_day(day)


def test_apply_calendar_drops_non_trading_days():
    from ediaad.markets.calendar import apply_calendar, load_twse_calendar

    calendar = load_twse_calendar(holiday_payload())
    series = build_series(
        [
            ("2026-02-10", 100.0),
            ("2026-02-11", 101.0),
            ("2026-02-12", 102.0),
            ("2026-02-13", 103.0),
            ("2026-02-14", 104.0),
            ("2026-02-15", 105.0),
            ("2026-02-16", 106.0),
            ("2026-02-23", 107.0),
        ]
    )

    filtered = apply_calendar(series, calendar)

    kept = [str(stamp.date()) for stamp in filtered["time"]]
    assert kept == ["2026-02-10", "2026-02-11", "2026-02-23"]
    assert list(filtered.index) == list(range(len(filtered))), "回傳的序列必須重新編號"
    assert all(calendar.is_trading_day(stamp.date()) for stamp in filtered["time"]), (
        "提供給 detect 的每個時間戳都必須是交易日"
    )
    assert list(filtered.columns) == list(SERIES_COLUMNS)


def test_apply_calendar_keeps_a_series_that_is_already_all_trading_days():
    from ediaad.markets.calendar import apply_calendar, load_twse_calendar

    calendar = load_twse_calendar(holiday_payload())
    series = build_series([("2026-02-10", 100.0), ("2026-02-11", 101.0), ("2026-02-23", 102.0)])

    filtered = apply_calendar(series, calendar)

    pd.testing.assert_frame_equal(filtered, series)
    assert filtered is not series, "回傳新物件，不改動輸入"


def test_apply_calendar_does_not_touch_the_input_frame():
    from ediaad.markets.calendar import apply_calendar, load_twse_calendar

    calendar = load_twse_calendar(holiday_payload())
    series = build_series([("2026-02-10", 100.0), ("2026-02-14", 104.0), ("2026-02-23", 107.0)])
    before = series.copy(deep=True)

    apply_calendar(series, calendar)

    pd.testing.assert_frame_equal(series, before)
    assert list(series.columns) == list(SERIES_COLUMNS), "不得在輸入序列上加欄位"


@pytest.mark.parametrize(
    ("payload", "mentions"),
    [
        pytest.param([], "物件", id="不是物件"),
        pytest.param({"stat": "ok", "fields": HOLIDAY_FIELDS}, "data", id="缺 data"),
        pytest.param({"stat": "ok", "data": HOLIDAY_ROWS}, "fields", id="缺 fields"),
        pytest.param(
            {"stat": "ok", "fields": ["名稱", "說明"], "data": [["x", "y"]]}, "日期", id="缺日期欄"
        ),
        pytest.param(
            {"stat": "ok", "fields": HOLIDAY_FIELDS, "data": [["not-a-date", "x", "y"]]},
            "not-a-date",
            id="日期無法解讀",
        ),
        pytest.param({"stat": "ok", "fields": HOLIDAY_FIELDS, "data": "x"}, "data", id="data 不是陣列"),
    ],
)
def test_a_bad_calendar_payload_is_a_readable_error(payload, mentions):
    from ediaad.markets.calendar import load_twse_calendar

    with pytest.raises(SourceError, match=mentions):
        load_twse_calendar(payload)


def test_market_defaults_differ_between_stock_and_crypto():
    from ediaad.markets.calendar import MARKET_PATTERN_DEFAULTS

    assert set(MARKET_PATTERN_DEFAULTS) == {"crypto", "stock"}
    crypto = MARKET_PATTERN_DEFAULTS["crypto"]
    stock = MARKET_PATTERN_DEFAULTS["stock"]

    assert crypto == NAMED_PATTERNS["range_fakeout_reversion"], "加密貨幣沿用既有預設，不動既有行為"
    assert stock["pattern_id"] == crypto["pattern_id"]
    assert stock["atr_period"] == crypto["atr_period"]
    assert stock["band_atr_multiple_max"] == crypto["band_atr_multiple_max"]
    assert stock["recovery_bars_max"] > crypto["recovery_bars_max"], "日線回歸較慢"
    assert stock["breakdown_bars_max"] > crypto["breakdown_bars_max"], "日線跌破較慢"
    assert stock["range_bars_max"] < crypto["range_bars_max"], "日線的盤整上限較短"
    assert stock["range_bars_min"] == crypto["range_bars_min"]


def test_default_spec_for_returns_the_market_preset():
    from ediaad.markets.calendar import MARKET_PATTERN_DEFAULTS, default_spec_for

    stock = default_spec_for("stock")
    crypto = default_spec_for("crypto")

    assert isinstance(stock, PatternSpec)
    assert stock == PatternSpec(**MARKET_PATTERN_DEFAULTS["stock"])
    assert crypto == PatternSpec(**MARKET_PATTERN_DEFAULTS["crypto"])
    assert stock != crypto


def test_default_spec_for_applies_overrides_on_top_of_the_market_defaults():
    from ediaad.markets.calendar import default_spec_for

    spec = default_spec_for("stock", {"recovery_bars_max": 3, "pattern_id": "custom"})

    assert spec.recovery_bars_max == 3
    assert spec.pattern_id == "custom"
    assert spec.breakdown_bars_max == default_spec_for("stock").breakdown_bars_max, (
        "未覆寫的欄位必須維持市場別預設"
    )


def test_default_spec_for_rejects_unknown_markets_and_bad_overrides():
    from ediaad.markets.calendar import default_spec_for

    with pytest.raises(ConfigError) as excinfo:
        default_spec_for("nasdaq")
    assert "nasdaq" in str(excinfo.value)
    assert "stock" in str(excinfo.value), "訊息必須列出可用的市場別"

    with pytest.raises(ConfigError, match="unknown_field"):
        default_spec_for("stock", {"unknown_field": 1})

    with pytest.raises(ConfigError, match="atr_period"):
        default_spec_for("stock", {"atr_period": 0})

    with pytest.raises(ConfigError, match="recovery_bars_max"):
        default_spec_for("stock", {"recovery_bars_max": -1})


def test_zero_recovery_bars_is_a_legal_override():
    """`recovery_bars_max = 0` 是 TASK-007 明訂的合法值（回歸必須在跌破當根完成）。"""
    from ediaad.markets.calendar import default_spec_for

    assert default_spec_for("stock", {"recovery_bars_max": 0}).recovery_bars_max == 0
