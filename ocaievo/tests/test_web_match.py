"""歷史回看頁（表單化 match，TASK-024／AC-046）。

觀察邊界：
1. **後端契約（自動）**：`POST /api/match` 的 JSON 與狀態碼，以及「與 CLI `match` 的
   報表**同一份**」——兩條路徑都呼叫 `ediaad.match.run_match`，因此以同一組輸入
   比較整份報表（不是比幾個欄位）。
2. **與核心函式一致（自動）**：`matches` 必須等於直接呼叫 `scan_similar` 的結果；
   `outlook.samples` 以「結束索引 + horizon < 序列長度」獨立重算。
3. **前端（自動，需 `node`）**：`match.js` 的純函式（表單轉型、列格式化、樣本數文字）。
4. **表單操作與表格外觀（人工）**：以 Chrome（Wayland）檢查一次，見 TDD 紀錄。
"""

from __future__ import annotations

import dataclasses
import http.client
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from ediaad import cli
from ediaad.outlook import forward_stats
from ediaad.scan import scan_similar

PROJECT_DIR = Path(__file__).resolve().parent.parent

#: 表單預設值（與 CLI 的預設一致：top=10、horizon=20、step=1、overlap=0.5）。
WINDOW = 12
TOP = 5
HORIZON = 10
TOTAL = 240


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    def json(self):
        return json.loads(self.body)


def call(host: str, port: int, method: str, path: str, body: object = None) -> Response:
    connection = http.client.HTTPConnection(host, port, timeout=30)
    try:
        payload = None
        headers = {}
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        return Response(
            status=response.status,
            headers={key.lower(): value for key, value in response.getheaders()},
            body=response.read(),
        )
    finally:
        connection.close()


def build_history_frame(total: int = TOTAL, *, offset: int = 50, range_bars: int = 12):
    """與 TASK-011 同一種夾具：背景帶週期性變異，並在 `offset` 植入完整結構。

    背景刻意有變異（週期 7 的小階梯）：若完全平坦，穩健正規化會把所有候選退化為 0，
    於是所有視窗同分 1.0，「完全相同者拿第一」就不再是可觀察的性質。
    """
    closes = [100.0 + (index % 7) * 0.3 for index in range(total)]
    highs = [value + 1.0 for value in closes]
    lows = [value - 1.0 for value in closes]

    lows[offset - 1] = 90.0
    for step in range(range_bars):
        base = 100.0 if step % 2 == 0 else 100.4
        closes[offset + step] = base
        highs[offset + step] = base + 1.0
        lows[offset + step] = base - 1.0

    breakdown = offset + range_bars
    closes[breakdown] = 98.5
    highs[breakdown] = 99.5
    lows[breakdown] = 97.0

    recovery = breakdown + 1
    closes[recovery] = 100.5
    highs[recovery] = 101.0
    lows[recovery] = 99.5

    times = pd.date_range("2024-01-01T00:00:00Z", periods=total, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "time": times,
            "open": [value - 0.1 for value in closes],
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [10.0 + (index % 5) for index in range(total)],
        }
    )


def seed_cache(app, symbol: str, interval: str, frame: pd.DataFrame) -> Path:
    directory = Path(app.cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{symbol}_{interval}.csv"
    frame.to_csv(path, index=False)
    return path


@pytest.fixture
def service(tmp_path):
    from ediaad.app import Application

    app = Application.create(home=tmp_path / "home")
    seed_cache(app, "HIST", "1h", build_history_frame())
    server = app.start(port=0)
    host, port = server.socket.getsockname()[:2]
    try:
        yield SimpleNamespace(
            app=app, server=server, host=host, port=port, home=tmp_path / "home"
        )
    finally:
        app.stop()
        app.close()


def match_body(**overrides) -> dict:
    body: dict = {
        "symbol": "HIST",
        "interval": "1h",
        "window": WINDOW,
        "top": TOP,
        "horizon": HORIZON,
    }
    body.update(overrides)
    return body


def post_match(service, body: dict) -> Response:
    return call(service.host, service.port, "POST", "/api/match", body)


def last_window_sample(frame: pd.DataFrame, window: int = WINDOW) -> pd.DataFrame:
    """端點採用的範例：序列（可先被 start／end 篩選）的最後 `window` 根。"""
    return frame.iloc[-window:].reset_index(drop=True)


# ---- AC-046：表單化 match ---------------------------------------------------


def test_match_scores_the_identical_window_one(service):
    """第一個失敗行為：端點不存在（404）；實作後完全相同者必須拿 1.0 且不超過 top。"""
    response = post_match(service, match_body())

    assert response.status == 200, response.text
    payload = response.json()
    assert payload["matches"][0]["score"] == 1.0
    assert len(payload["matches"]) <= TOP

    # 範例本身（時間範圍內最後 `window` 根）與自己完全相同，分數必為 1.0；
    # 週期性背景會產生多個 1.0，因此要放寬 top 才看得到排在後面的那一個。
    wide = post_match(service, match_body(top=60)).json()
    perfect = [match["start_index"] for match in wide["matches"] if match["score"] == 1.0]
    assert TOTAL - WINDOW in perfect
    assert wide["matches"][0]["start_index"] == perfect[0]


def test_match_report_is_the_same_report_as_the_cli(service, tmp_path):
    """「與 CLI `match` 同構」以同一份報表比對：兩條路徑共用同一個流程函式。"""
    frame = build_history_frame()
    data_path = tmp_path / "data.csv"
    sample_path = tmp_path / "sample.csv"
    report_path = tmp_path / "report.json"
    frame.to_csv(data_path, index=False)
    last_window_sample(frame).to_csv(sample_path, index=False)

    exit_code = cli.main(
        [
            "match",
            "--data",
            str(data_path),
            "--sample",
            str(sample_path),
            "--top",
            str(TOP),
            "--horizon",
            str(HORIZON),
            "--out",
            str(report_path),
        ]
    )

    assert exit_code == 0
    cli_report = json.loads(report_path.read_text(encoding="utf-8"))
    payload = post_match(service, match_body()).json()

    assert set(payload) == {"sample", "params", "data_source", "matches", "outlook"}
    assert payload == cli_report


def test_match_scores_are_ordered_and_ties_break_by_ascending_index(service):
    payload = post_match(service, match_body(top=20)).json()

    scores = [match["score"] for match in payload["matches"]]
    assert scores == sorted(scores, reverse=True)
    perfect = [match["start_index"] for match in payload["matches"] if match["score"] == 1.0]
    assert perfect == sorted(perfect)
    assert len(perfect) >= 2, "週期性背景應產生多個完全相同（1.0）的視窗"


def test_match_is_deterministic(service):
    first = post_match(service, match_body())
    second = post_match(service, match_body())

    assert first.status == 200, first.text
    assert first.body == second.body


def test_match_matches_the_core_scan(service):
    """`matches` 必須等於直接呼叫 `scan_similar` 的結果（索引、分數與時間界線）。"""
    frame = build_history_frame()
    expected = scan_similar(
        frame, last_window_sample(frame), WINDOW, top=TOP, step=1, overlap=0.5
    )
    payload = post_match(service, match_body()).json()

    assert [(m["start_index"], m["end_index"]) for m in payload["matches"]] == [
        (m.start_index, m.end_index) for m in expected
    ]
    assert [m["score"] for m in payload["matches"]] == [m.score for m in expected]
    assert [m["time_start"] for m in payload["matches"]] == [
        pd.Timestamp(m.time_start).isoformat() for m in expected
    ]
    assert payload["params"] == {
        "window": WINDOW,
        "top": TOP,
        "horizon": HORIZON,
        "step": 1,
        "overlap": 0.5,
    }


def test_match_parameters_change_the_result(service):
    """`top`／`step`／`overlap`／`horizon` 真的傳到核心，而不是被忽略。"""
    frame = build_history_frame()
    payload = post_match(
        service, match_body(top=2, step=4, overlap=0.0, horizon=3)
    ).json()
    expected = scan_similar(
        frame, last_window_sample(frame), WINDOW, top=2, step=4, overlap=0.0
    )

    assert payload["params"] == {
        "window": WINDOW,
        "top": 2,
        "horizon": 3,
        "step": 4,
        "overlap": 0.0,
    }
    assert len(payload["matches"]) == len(expected) <= 2
    assert [m["start_index"] for m in payload["matches"]] == [
        m.start_index for m in expected
    ]


def test_match_accepts_numeric_strings_from_a_form(service):
    """表單送出的值是字串；端點必須自行轉型，不能要求前端先轉。"""
    payload = post_match(
        service,
        {
            "symbol": "HIST",
            "interval": "1h",
            "window": str(WINDOW),
            "top": str(TOP),
            "horizon": str(HORIZON),
            "step": "1",
            "overlap": "0.5",
        },
    ).json()

    assert payload == post_match(service, match_body()).json()


def test_match_applies_the_documented_defaults(service):
    """只給 symbol／interval／window 時，其餘套用文件上的預設（top=10、horizon=20…）。"""
    from ediaad.match import (
        DEFAULT_HORIZON,
        DEFAULT_OVERLAP,
        DEFAULT_STEP,
        DEFAULT_TOP,
    )

    payload = post_match(
        service, {"symbol": "HIST", "interval": "1h", "window": WINDOW}
    ).json()

    assert (DEFAULT_TOP, DEFAULT_HORIZON, DEFAULT_STEP, DEFAULT_OVERLAP) == (10, 20, 1, 0.5)
    assert payload["params"] == {
        "window": WINDOW,
        "top": DEFAULT_TOP,
        "horizon": DEFAULT_HORIZON,
        "step": DEFAULT_STEP,
        "overlap": DEFAULT_OVERLAP,
    }


def test_match_outlook_counts_only_fragments_with_room_for_the_horizon(service):
    """樣本數以「結束索引 + horizon < 序列長度」獨立重算（尾端不足者排除）。"""
    for horizon in (3, 10, 50, TOTAL - 1):
        payload = post_match(service, match_body(top=20, horizon=horizon)).json()
        matches = payload["matches"]
        expected = len(
            [m for m in matches if m["end_index"] + horizon < TOTAL]
        )

        assert payload["outlook"]["samples"] == expected, horizon
        assert payload["params"]["horizon"] == horizon


def test_match_outlook_values_equal_the_core_statistics(service):
    """樣本 > 0 時，五個統計值必須與直接呼叫 `forward_stats` 完全相同。"""
    frame = build_history_frame()
    core_matches = scan_similar(
        frame, last_window_sample(frame), WINDOW, top=6, step=1, overlap=0.5
    )
    expected = forward_stats(core_matches, frame, 4)
    payload = post_match(service, match_body(top=6, horizon=4)).json()

    assert expected.samples > 0
    assert payload["outlook"] == {
        "samples": expected.samples,
        "up_probability": expected.up_probability,
        "mean_return": expected.mean_return,
        "median_return": expected.median_return,
        "std_return": expected.std_return,
    }


def test_match_reports_the_data_source_marked_by_the_source(service):
    """`data_source` 來自來源（`attrs`），不是把 `source_id` 抄一次。"""
    from ediaad.markets.base import register, unregister

    class FakeCachedSource:
        # id 與 attrs 的標示**刻意不同**：`data_source` 必須來自來源回報的
        # `attrs`，而不是把 `source_id` 抄一次（否則快取／即時／過期三態無從區分）。
        id = "fake-source"
        display_name = "假快取來源（測試用）"
        supported_intervals = ("1h",)
        needs_api_key = False

        def search(self, query, limit=20):
            return []

        def fetch(self, symbol, interval, limit=None):
            series = build_history_frame()
            if limit is not None:
                series = series.iloc[-limit:].reset_index(drop=True)
            series.attrs["data_source"] = "fake-cache"
            return series

    register(FakeCachedSource())
    try:
        payload = post_match(
            service, match_body(source="fake-source", interval="1h")
        ).json()
    finally:
        unregister("fake-source")

    assert payload["data_source"] == "fake-cache"
    assert payload["data_source"] != "fake-source"
    assert payload["matches"][0]["score"] == 1.0


def test_match_accepts_naive_timestamps_as_utc(service):
    """表單沒有時區時一律視為 UTC（序列契約是 UTC；否則比較會直接爆掉）。"""
    frame = build_history_frame()
    end = frame["time"].iloc[14]
    # 兩端都不帶時區：必須被當成 UTC，否則界線會落在別的時刻（例如台北時間就少 8 小時）
    payload = post_match(
        service,
        match_body(
            start="2024-01-01T10:00:00", end="2024-01-01T14:00:00", window=5, top=3
        ),
    ).json()

    assert payload["sample"]["length"] == 5
    assert payload["sample"]["time_end"] == end.isoformat() == "2024-01-01T14:00:00+00:00"
    assert payload["sample"]["time_start"] == frame["time"].iloc[10].isoformat()


def test_match_includes_the_boundary_bars_of_the_time_range(service):
    """時間範圍是**閉區間**：與界線同一時間的 K 線必須被納入。"""
    frame = build_history_frame()
    start = frame["time"].iloc[10]
    end = frame["time"].iloc[14]
    payload = post_match(
        service,
        match_body(start=start.isoformat(), end=end.isoformat(), window=5, top=3),
    ).json()

    assert payload["sample"]["length"] == 5
    assert payload["sample"]["time_start"] == start.isoformat()
    assert payload["sample"]["time_end"] == end.isoformat()


def test_match_reports_no_samples_as_null_not_zero(service):
    """`samples == 0` 時其餘統計必須是 `null`（不是 0，否則會被讀成「報酬為 0」）。"""
    payload = post_match(service, match_body(horizon=TOTAL)).json()

    assert payload["outlook"] == {
        "samples": 0,
        "up_probability": None,
        "mean_return": None,
        "median_return": None,
        "std_return": None,
    }


def test_match_filters_the_series_by_start_and_end(service):
    """時間範圍會先篩選序列，範例＝篩選後的最後 `window` 根。"""
    frame = build_history_frame()
    end = frame["time"].iloc[150]
    payload = post_match(
        service, match_body(end=end.isoformat(), top=20)
    ).json()

    assert payload["sample"]["time_end"] == end.isoformat()
    assert payload["sample"]["time_start"] == frame["time"].iloc[150 - WINDOW + 1].isoformat()
    for match in payload["matches"]:
        assert pd.Timestamp(match["time_start"]) <= end
        assert pd.Timestamp(match["time_end"]) <= end

    # 只留植入結構之前的區段：最後一個視窗與它自己相同（1.0），但時間界線在範圍內
    narrower = post_match(
        service,
        match_body(
            start=frame["time"].iloc[0].isoformat(),
            end=frame["time"].iloc[20].isoformat(),
            window=5,
            top=3,
        ),
    ).json()
    assert narrower["sample"]["length"] == 5
    assert pd.Timestamp(narrower["sample"]["time_end"]) == frame["time"].iloc[20]


def test_match_response_is_json(service):
    response = post_match(service, match_body())
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["data_source"] == "csv"


# ---- AC-046：不合法輸入 -----------------------------------------------------


def _assert_bad(response: Response, fragment: str) -> dict:
    assert response.status == 400, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert "Traceback" not in response.text
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"
    assert fragment in payload["error"]["message"]
    return payload


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"window": 0}, "window"),
        ({"window": -3}, "window"),
        ({"window": "abc"}, "window"),
        ({"window": 2.5}, "window"),
        ({"window": TOTAL + 1}, "window"),
        ({"top": 0}, "top"),
        ({"top": -1}, "top"),
        ({"horizon": 0}, "horizon"),
        ({"horizon": -5}, "horizon"),
        ({"step": 0}, "step"),
        ({"overlap": 1.5}, "overlap"),
        ({"overlap": -0.1}, "overlap"),
        ({"overlap": "abc"}, "overlap"),
    ],
)
def test_match_rejects_invalid_numbers_with_the_field_name(service, overrides, fragment):
    _assert_bad(post_match(service, match_body(**overrides)), fragment)


def test_match_rejects_a_reversed_or_unparsable_time_range(service):
    _assert_bad(
        post_match(
            service,
            match_body(start="2024-02-01T00:00:00+00:00", end="2024-01-01T00:00:00+00:00"),
        ),
        "start",
    )
    _assert_bad(post_match(service, match_body(start="not-a-time")), "start")
    _assert_bad(post_match(service, match_body(end="2024-13-45")), "end")


def test_match_requires_symbol_interval_and_window(service):
    _assert_bad(post_match(service, {"interval": "1h", "window": WINDOW}), "symbol")
    _assert_bad(post_match(service, {"symbol": "HIST", "window": WINDOW}), "interval")
    _assert_bad(post_match(service, {"symbol": "HIST", "interval": "1h"}), "window")
    _assert_bad(post_match(service, match_body(symbol="")), "symbol")


def test_match_rejects_unknown_fields_and_bodies_that_are_not_objects(service):
    _assert_bad(post_match(service, match_body(windows=WINDOW)), "windows")
    _assert_bad(post_match(service, match_body(limit=10_001)), "10000")
    _assert_bad(post_match(service, match_body(source="nope")), "nope")
    _assert_bad(post_match(service, ["HIST"]), "JSON 物件")
    empty = call(service.host, service.port, "POST", "/api/match")
    payload = _assert_bad(empty, "主體")
    assert "必填" in payload["error"]["message"]


def test_match_errors_never_leak_a_traceback(service):
    bad_bodies = [
        match_body(window=0),
        match_body(top="x"),
        match_body(overlap=2),
        match_body(start="nope"),
        match_body(),
    ]
    bad_bodies[-1].pop("window")
    for body in bad_bodies:
        response = post_match(service, body)
        assert response.status == 400, response.text
        assert "Traceback" not in response.text
        assert response.json()["error"]["message"].strip()


def test_match_uses_the_settings_derived_series_limit(service):
    """`limit` 與其他端點共用（決定載入幾根），且仍受上限政策保護。"""
    payload = post_match(service, match_body(limit=60, window=5, top=3)).json()

    assert payload["sample"]["length"] == 5
    for match in payload["matches"]:
        # 只載入最近 60 根，因此所有命中都落在尾端
        assert match["start_index"] <= 60 - 5


# ---- AC-046：前端歷史回看頁（以 Node 載入 match.js 驗證） --------------------

NODE = shutil.which("node")

MATCH_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const context = {console: console};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync("match.js", "utf8"), context);

const ui = context.ediaadMatch;
if (!ui) {
  throw new Error("match.js 必須在 window.ediaadMatch 上匯出功能");
}

function caught(fn) {
  try {
    fn();
  } catch (error) {
    return String(error.message || error);
  }
  return null;
}

const payload = {
  sample: {length: 12, time_start: "2024-01-01T00:00:00+00:00", time_end: "2024-01-01T11:00:00+00:00"},
  params: {window: 12, top: 2, horizon: 10, step: 1, overlap: 0.5},
  data_source: "csv",
  matches: [
    {start_index: 3, end_index: 14, score: 1.0, time_start: "2024-01-01T03:00:00+00:00", time_end: "2024-01-01T14:00:00+00:00"},
    {start_index: 20, end_index: 31, score: 0.9876543, time_start: "2024-01-01T20:00:00+00:00", time_end: "2024-01-02T07:00:00+00:00"}
  ],
  outlook: {samples: 2, up_probability: 0.5, mean_return: 0.0123, median_return: -0.004, std_return: 0.02}
};

const report = {
  body: ui.buildMatchBody({
    symbol: "  HIST  ", interval: " 1h ", window: "12", top: "5", horizon: "10",
    step: "", overlap: "0.5", start: "2024-01-01T00:00:00+00:00", end: ""
  }),
  bodyMinimal: ui.buildMatchBody({symbol: "HIST", interval: "1h", window: "12"}),
  errors: {
    symbol: caught(() => ui.buildMatchBody({symbol: "  ", interval: "1h", window: "12"})),
    interval: caught(() => ui.buildMatchBody({symbol: "HIST", interval: "", window: "12"})),
    windowText: caught(() => ui.buildMatchBody({symbol: "HIST", interval: "1h", window: "abc"})),
    windowZero: caught(() => ui.buildMatchBody({symbol: "HIST", interval: "1h", window: "0"})),
    windowFraction: caught(() => ui.buildMatchBody({symbol: "HIST", interval: "1h", window: "2.5"})),
    topZero: caught(() => ui.buildMatchBody({symbol: "HIST", interval: "1h", window: "12", top: "0"})),
    overlapOut: caught(() => ui.buildMatchBody({symbol: "HIST", interval: "1h", window: "12", overlap: "2"})),
    overlapText: caught(() => ui.buildMatchBody({symbol: "HIST", interval: "1h", window: "12", overlap: "x"})),
    windowMissing: caught(() => ui.buildMatchBody({symbol: "HIST", interval: "1h"}))
  },
  rows: ui.matchRows(payload),
  outlookLines: ui.describeOutlook(payload.outlook),
  noSamples: ui.describeOutlook({samples: 0, up_probability: null, mean_return: null, median_return: null, std_return: null}),
  summary: ui.describeResult(payload),
  error: ui.describeError({error: {code: "invalid_request", message: "序列長度 20 短於 window=30，無法掃描"}}),
  errorFallback: ui.describeError(null)
};
process.stdout.write(JSON.stringify(report));
"""


def match_report() -> dict:
    """以 Node 載入 `match.js` 的純函式並取回結果。"""
    static = PROJECT_DIR / "ediaad" / "web" / "static"
    completed = subprocess.run(
        [NODE, "-e", MATCH_HARNESS],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(static),
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def page():
    if NODE is None:
        pytest.skip("需要 node 才能驗證 match.js 的純函式（僅測試期依賴）")
    return match_report()


def test_match_js_is_served(service):
    response = call(service.host, service.port, "GET", "/static/match.js")

    assert response.status == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "ediaadMatch" in response.text
    assert "/api/match" in response.text


def test_match_page_wires_the_form_and_the_result_table(service):
    response = call(service.host, service.port, "GET", "/static/match_page.html")

    assert response.status == 200
    assert response.headers["content-type"].startswith("text/html")
    for marker in (
        'id="match-form"',
        'id="match-symbol"',
        'id="match-interval"',
        'id="match-window"',
        'id="match-top"',
        'id="match-horizon"',
        'id="match-start"',
        'id="match-end"',
        'id="match-table"',
        'id="match-rows"',
        'id="match-outlook"',
        'id="match-status"',
        'id="match-error"',
        "/static/match.js",
    ):
        assert marker in response.text, marker
    assert "/static/style.css" in response.text


def test_index_html_links_to_the_match_page(service):
    text = call(service.host, service.port, "GET", "/").text
    assert "/static/match_page.html" in text


def test_match_frontend_does_not_reimplement_the_engine(service):
    text = call(service.host, service.port, "GET", "/static/match.js").text
    for forbidden in ("scan_similar(", "forward_stats(", "rank(", "Math.exp"):
        assert forbidden not in text, forbidden


def test_match_form_builds_a_typed_body(page):
    assert page["body"] == {
        "symbol": "HIST",
        "interval": "1h",
        "window": 12,
        "top": 5,
        "horizon": 10,
        "overlap": 0.5,
        "start": "2024-01-01T00:00:00+00:00",
    }
    # 留空的欄位不送（由後端的預設值決定），避免前端另立一套預設
    assert page["bodyMinimal"] == {"symbol": "HIST", "interval": "1h", "window": 12}


def test_match_form_rejects_bad_values_with_the_field_name(page):
    errors = page["errors"]

    assert "symbol" in errors["symbol"]
    assert "interval" in errors["interval"]
    assert "window" in errors["windowText"]
    assert "window" in errors["windowZero"]
    assert "window" in errors["windowFraction"]
    assert "top" in errors["topZero"]
    assert "overlap" in errors["overlapOut"]
    assert "overlap" in errors["overlapText"]
    assert "window" in errors["windowMissing"]


def test_match_rows_carry_the_ranking_fields(page):
    rows = page["rows"]

    assert len(rows) == 2
    assert rows[0]["startIndex"] == 3 and rows[0]["endIndex"] == 14
    assert rows[0]["score"] == "1.0000"
    assert rows[1]["score"] == "0.9877"
    assert rows[0]["timeStart"] == "2024-01-01T03:00:00+00:00"


def test_match_outlook_text_states_the_sample_count(page):
    lines = "\n".join(page["outlookLines"])

    assert "樣本數：2" in lines
    assert "50" in lines  # 上漲機率 50%
    assert "%" in lines
    assert "平均" in lines and "中位數" in lines and "標準差" in lines

    no_samples = page["noSamples"]
    assert len(no_samples) == 1
    assert "樣本數：0" in no_samples[0]
    assert "無樣本，無法提供" in no_samples[0]
    assert "%" not in "\n".join(no_samples)


def test_match_summary_and_error_text(page):
    summary = "\n".join(page["summary"])

    assert "12" in summary  # window
    assert "2" in summary  # top 或命中數
    assert "csv" in summary
    assert "序列長度 20 短於 window=30，無法掃描" in page["error"]
    assert "無法" in page["errorFallback"]
