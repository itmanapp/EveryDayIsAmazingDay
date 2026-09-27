"""K 線圖與三相位標註（TASK-022）。

觀察邊界：
1. **後端契約（自動）**：`GET /api/series` 與 `GET /api/patterns/events` 的 JSON，
   以及「端點回傳的四個相位索引與直接呼叫 `ediaad.patterns.detect` 完全相同」。
2. **幾何換算（自動，需 `node`）**：`chart.js` 的索引 → 像素換算，用 Node 載入該檔並以
   假 canvas context 驗證（標記的水平位置必須與 JSON 索引一致）。沒有 `node` 時跳過。
3. **外觀（人工）**：canvas 實際繪製的外觀無法在無瀏覽器自動化的環境驗證，依 SPEC 第 7 節
   以 Chrome（Wayland）目視核對——結果記於 TDD 紀錄。
"""

from __future__ import annotations

import http.client
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

# 與 TASK-008 相同的植入方式（索引 30 之前的深谷把盤整區間限制在 30～49）。
PROJECT_DIR = Path(__file__).resolve().parent.parent

RANGE_START = 30
RANGE_END = 49
BREAKDOWN_INDEX = 50
RECOVERY_INDEX = 51


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


def call(host: str, port: int, method: str, path: str) -> Response:
    connection = http.client.HTTPConnection(host, port, timeout=10)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return Response(
            status=response.status,
            headers={key.lower(): value for key, value in response.getheaders()},
            body=response.read(),
        )
    finally:
        connection.close()


def build_planted_series(*, scale: float = 1.0, shift: float = 0.0, tail_bars: int = 22) -> pd.DataFrame:
    """與 TASK-008 相同的植入方式：盤整 → 假跌破 → 回歸（索引 6／29／30／31）。

    `scale`／`shift` 用來產生尺度不同的同一段結構（呈現層的尺度不變對照）。
    """
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []

    for index in range(RANGE_END + 1):
        base = 100.0 if index % 2 == 0 else 100.4
        closes.append(base)
        highs.append(base + 1.0)
        lows.append(base - 1.0)
    lows[29] = 90.0  # 深谷：讓盤整區間無法往前延伸（盤整因此是 30～49）

    closes.append(98.5)
    highs.append(99.5)
    lows.append(97.0)
    closes.append(100.5)
    highs.append(101.0)
    lows.append(99.5)

    for index in range(tail_bars):
        base = 100.0 if index % 2 == 0 else 100.4
        closes.append(base)
        highs.append(base + 1.0)
        lows.append(base - 1.0)

    def transform(values: list[float]) -> list[float]:
        return [value * scale + shift for value in values]

    times = pd.date_range("2024-01-01T00:00:00Z", periods=len(closes), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "time": times,
            "open": transform([value - 0.1 for value in closes]),
            "high": transform(highs),
            "low": transform(lows),
            "close": transform(closes),
            "volume": [1000.0] * len(closes),
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
    seed_cache(app, "2330", "1d", build_planted_series())
    server = app.start(port=0)
    host, port = server.socket.getsockname()[:2]
    try:
        yield SimpleNamespace(app=app, server=server, host=host, port=port, home=tmp_path / "home")
    finally:
        app.stop()
        app.close()


def expected_spec(app):
    """端點應該使用的規格：設定（市場別預設 ＋ pattern_id）推導而來。"""
    from ediaad.markets.calendar import default_spec_for

    return default_spec_for(app.settings["market"], {"pattern_id": app.settings["pattern_id"]})


# ---- AC-043：序列端點 -------------------------------------------------------


def test_series_endpoint_returns_the_six_arrays(service):
    response = call(service.host, service.port, "GET", "/api/series?symbol=2330&interval=1d")

    assert response.status == 200
    payload = response.json()
    for name in ("time", "open", "high", "low", "close", "volume"):
        assert isinstance(payload[name], list), name
        assert len(payload[name]) == payload["count"], name
    assert payload["symbol"] == "2330"
    assert payload["interval"] == "1d"
    assert payload["source"] == "csv", "未指定來源時使用預設來源（自訂 CSV）"
    assert payload["time"][0].startswith("2024-01-01"), "時間必須是可讀的 ISO 字串"


def test_series_endpoint_matches_the_source_file(service):
    from ediaad.data import load_csv

    response = call(service.host, service.port, "GET", "/api/series?symbol=2330&interval=1d").json()
    frame = load_csv(Path(service.app.cache_dir) / "2330_1d.csv")

    assert response["close"] == [float(value) for value in frame["close"]]
    assert response["high"] == [float(value) for value in frame["high"]]
    assert response["volume"] == [float(value) for value in frame["volume"]]


def test_series_endpoint_honours_the_limit(service):
    payload = call(service.host, service.port, "GET", "/api/series?symbol=2330&interval=1d&limit=5").json()

    assert payload["count"] == 5
    assert len(payload["time"]) == 5


def test_series_endpoint_reports_a_missing_series(service):
    response = call(service.host, service.port, "GET", "/api/series?symbol=NOPE&interval=1d")

    assert response.status == 502, "來源失敗是本機服務之外的錯"
    assert response.json()["error"]["code"] == "source_failed"
    assert "NOPE_1d.csv" in response.json()["error"]["message"]
    assert "Traceback" not in response.text


def test_series_endpoint_rejects_an_unsupported_interval(service):
    """以支援週期受限的來源驗證：未支援的週期必須是可讀的 400，不是 500。"""
    response = call(service.host, service.port, "GET", "/api/series?symbol=2330&interval=1h&source=twse")

    assert response.status == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert "1h" in response.json()["error"]["message"]
    assert "Traceback" not in response.text


def test_series_endpoint_rejects_an_unknown_source(service):
    response = call(service.host, service.port, "GET", "/api/series?symbol=2330&interval=1d&source=nope")

    assert response.status == 400
    assert "nope" in response.json()["error"]["message"]
    assert "csv" in response.json()["error"]["message"], "訊息必須列出可用來源"


@pytest.mark.parametrize("value", ["0", "-5", "10001", "abc"])
def test_series_endpoint_rejects_a_bad_limit(service, value):
    response = call(service.host, service.port, "GET", f"/api/series?symbol=2330&interval=1d&limit={value}")

    assert response.status == 400
    assert "limit" in response.json()["error"]["message"]
    assert "Traceback" not in response.text


# ---- AC-043：事件端點與索引一致性 -------------------------------------------


def test_events_endpoint_matches_detect_exactly(service):
    from ediaad.patterns import detect

    payload = call(service.host, service.port, "GET", "/api/patterns/events?symbol=2330&interval=1d").json()

    frame = pd.read_csv(Path(service.app.cache_dir) / "2330_1d.csv", parse_dates=["time"])
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    expected = detect(frame, expected_spec(service.app))

    assert payload["status"] == "evaluated"
    assert len(payload["events"]) == len(expected)
    for got, want in zip(payload["events"], expected):
        assert got["range_start_index"] == want.range_start_index
        assert got["range_end_index"] == want.range_end_index
        assert got["breakdown_index"] == want.breakdown_index
        assert got["recovery_index"] == want.recovery_index
        assert got["pattern_id"] == want.pattern_id


def test_the_planted_event_is_the_one_the_chart_will_annotate(service):
    payload = call(service.host, service.port, "GET", "/api/patterns/events?symbol=2330&interval=1d").json()

    planted = [event for event in payload["events"] if event["range_end_index"] == RANGE_END]
    assert planted, f"植入的結構必須被找到：{payload['events']}"
    assert planted[0]["range_start_index"] == RANGE_START
    assert planted[0]["breakdown_index"] == BREAKDOWN_INDEX
    assert planted[0]["recovery_index"] == RECOVERY_INDEX


def test_events_endpoint_reports_insufficient_data_separately(service):
    seed_cache(service.app, "SHORT", "1d", build_planted_series().iloc[:12])

    payload = call(service.host, service.port, "GET", "/api/patterns/events?symbol=SHORT&interval=1d").json()

    assert payload["status"] == "insufficient", "「資料不足」不得與「評估後無命中」混為一談（F-003）"
    assert payload["events"] == []
    assert "資料不足" in payload["message"]
    assert payload["bars"] == 12


def test_events_endpoint_reports_no_hit_separately(service):
    import numpy as np

    flat = pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01T00:00:00Z", periods=60, freq="D", tz="UTC"),
            "open": [100.0] * 60,
            "high": [100.2] * 60,
            "low": [99.8] * 60,
            "close": [100.0] * 60,
            "volume": [10.0] * 60,
        }
    )
    assert np.isfinite(flat["close"]).all()
    seed_cache(service.app, "FLAT", "1d", flat)

    payload = call(service.host, service.port, "GET", "/api/patterns/events?symbol=FLAT&interval=1d").json()

    assert payload["status"] == "evaluated"
    assert payload["events"] == []
    assert "沒有命中" in payload["message"]
    assert "資料不足" not in payload["message"]


def test_events_carry_a_friendly_summary_for_the_text_alternative(service):
    payload = call(service.host, service.port, "GET", "/api/patterns/events?symbol=2330&interval=1d").json()

    planted = [event for event in payload["events"] if event["range_end_index"] == RANGE_END][0]
    for field in ("pattern_id", "confidence", "range_start_index", "range_end_index"):
        assert field in planted, f"文字摘要需要 {field}"
    assert 0.0 <= planted["confidence"] <= 1.0


def test_the_four_indices_survive_scaling(service):
    """呈現層的尺度不變對照：整段價格乘 0.5 或加常數後，相位索引不變。"""
    seed_cache(service.app, "HALF", "1d", build_planted_series(scale=0.5))
    seed_cache(service.app, "SHIFTED", "1d", build_planted_series(shift=1000.0))

    baseline = call(service.host, service.port, "GET", "/api/patterns/events?symbol=2330&interval=1d").json()
    halved = call(service.host, service.port, "GET", "/api/patterns/events?symbol=HALF&interval=1d").json()
    shifted = call(service.host, service.port, "GET", "/api/patterns/events?symbol=SHIFTED&interval=1d").json()

    def phases(payload):
        return [
            (event["range_start_index"], event["range_end_index"], event["breakdown_index"], event["recovery_index"])
            for event in payload["events"]
        ]

    assert phases(halved) == phases(baseline), "乘上正數不得改變相位"
    assert phases(shifted) == phases(baseline), "平移不得改變相位"


def test_an_out_of_range_event_is_dropped_with_a_warning(service, monkeypatch, caplog):
    """事件索引超出序列範圍時不得被畫出（前端只呈現，過濾在後端）。"""
    import logging

    from ediaad.patterns import PatternEvent
    from ediaad.web import routes

    def fake_detect(_series, _spec):
        return [
            PatternEvent(
                pattern_id="range_fakeout_reversion",
                range_start_index=0,
                range_end_index=999,
                breakdown_index=1000,
                recovery_index=1001,
                confidence=0.5,
                band=1.0,
                breakdown_depth=0.5,
                recovery_bars=1,
            )
        ]

    monkeypatch.setattr(routes, "detect", fake_detect)

    with caplog.at_level(logging.WARNING, logger="ediaad.web"):
        payload = call(service.host, service.port, "GET", "/api/patterns/events?symbol=2330&interval=1d").json()

    assert payload["events"] == [], "超出範圍的事件不得回給前端"
    assert payload["dropped"] == 1
    assert "超出" in caplog.text


def test_events_endpoint_rejects_a_bad_interval(service):
    response = call(service.host, service.port, "GET", "/api/patterns/events?symbol=2330&interval=2h&source=twse")

    assert response.status == 400
    assert "Traceback" not in response.text


# ---- AC-043：前端幾何（以 Node 載入 chart.js 驗證；沒有 node 時跳過） --------

NODE = shutil.which("node")

CHART_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const context = {console: console};
context.window = context;
vm.createContext(context);
// `node -e <script> <arg>` 的 process.argv 是 [execPath, arg]，沒有 script 名稱。
vm.runInContext(fs.readFileSync(process.argv[process.argv.length - 1], "utf8"), context);

const chart = context.ediaadChart;
if (!chart) {
  throw new Error("chart.js 必須在 window.ediaadChart 上匯出功能");
}

const bars = {
  time: [], open: [], high: [], low: [], close: [], volume: [],
};
for (let index = 0; index < 74; index += 1) {
  const base = index % 2 === 0 ? 100.0 : 100.4;
  bars.time.push("2024-01-01T00:00:00+00:00");
  bars.open.push(base - 0.1);
  bars.high.push(index === 55 ? 120.0 : base + 1.0);
  bars.low.push(index === 29 ? 90.0 : base - 1.0);
  bars.close.push(base);
  bars.volume.push(1000);
}

const viewport = chart.makeViewport(bars, 800, 400, {top: 10, right: 20, bottom: 30, left: 40});
const event = {
  pattern_id: "range_fakeout_reversion",
  range_start_index: 30,
  range_end_index: 49,
  breakdown_index: 50,
  recovery_index: 51,
  confidence: 0.75,
  band: 2.4,
  breakdown_depth: 0.8,
  recovery_bars: 1,
};

// 同一段結構但價格全部縮放＋平移：x 只由索引決定，因此必須完全相同。
const scaled = {time: bars.time, open: [], high: [], low: [], close: [], volume: bars.volume};
bars.open.forEach(function (value, index) {
  scaled.open.push(value * 0.5 + 1000);
  scaled.high.push(bars.high[index] * 0.5 + 1000);
  scaled.low.push(bars.low[index] * 0.5 + 1000);
  scaled.close.push(bars.close[index] * 0.5 + 1000);
});
const scaledViewport = chart.makeViewport(scaled, 800, 400, {top: 10, right: 20, bottom: 30, left: 40});

const markers = chart.phaseMarkers(event, bars, viewport);
const summaryLines = chart.summaryLines(event);
const report = {
  viewport: viewport,
  x: [0, 29, 30, 49, 50, 51, 73].map((index) => chart.xFor(index, viewport)),
  xScaled: [0, 29, 30, 49, 50, 51, 73].map((index) => chart.xFor(index, scaledViewport)),
  y: [90.0, 100.0, 120.0].map((price) => chart.yFor(price, viewport)),
  markers: markers,
  summary: summaryLines,
  candlesDrawn: chart.candleGeometry(bars, viewport).length,
  firstCandleX: chart.candleGeometry(bars, viewport)[0].x,
  lastCandleX: chart.candleGeometry(bars, viewport)[bars.close.length - 1].x,
};
process.stdout.write(JSON.stringify(report));
"""


def chart_geometry() -> dict:
    """以 Node 執行 chart.js 的幾何換算並取回結果。"""
    script = PROJECT_DIR / "ediaad" / "web" / "static" / "chart.js"
    completed = subprocess.run(
        [NODE, "-e", CHART_HARNESS, str(script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def geometry():
    if NODE is None:
        pytest.skip("需要 node 才能驗證 chart.js 的幾何換算（僅測試期依賴）")
    return chart_geometry()


def test_chart_js_is_served(service):
    response = call(service.host, service.port, "GET", "/static/chart.js")

    assert response.status == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "ediaadChart" in response.text


def test_the_chart_page_is_served_and_linked_from_the_index(service):
    page = call(service.host, service.port, "GET", "/static/chart_page.html")
    index = call(service.host, service.port, "GET", "/").text

    assert page.status == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "canvas" in page.text
    assert 'for="' in page.text, "控制項必須有 label（SPEC 第 6 節可及性）"
    assert "chart_page.html" in index, "首頁必須連到 K 線圖頁"
    assert "chart.js" in page.text


def test_x_for_maps_indices_monotonically_inside_the_plot(geometry):
    viewport = geometry["viewport"]
    xs = geometry["x"]

    assert xs == sorted(xs), "索引越大，x 必須越大"
    assert xs[0] > viewport["padding"]["left"], "第一根的標記必須在左邊界內"
    assert xs[-1] < viewport["padding"]["left"] + viewport["plotWidth"]
    assert len(set(xs)) == len(xs), "不同索引必須落在不同的 x"


def test_x_positions_are_linear_in_the_index_and_independent_of_price(geometry):
    """x 只由索引決定：相鄰索引差一格，且價格縮放不得左右移動標記。"""
    viewport = geometry["viewport"]
    slot = viewport["plotWidth"] / viewport["count"]

    assert geometry["x"][2] - geometry["x"][1] == pytest.approx(slot), "索引 29 → 30 相差一格"
    assert geometry["x"][-1] - geometry["x"][-2] == pytest.approx(22 * slot), "索引 51 → 73 相差 22 格"
    assert geometry["xScaled"] == pytest.approx(geometry["x"]), "價格縮放不得改變標記的 x"


def test_y_for_maps_prices_inverted_and_inside_the_plot(geometry):
    viewport = geometry["viewport"]
    low, middle, high = geometry["y"]

    assert low > middle > high, "價格越高，y 越小（螢幕座標向下）"
    assert high >= viewport["padding"]["top"] - 1e-9
    assert low <= viewport["padding"]["top"] + viewport["plotHeight"] + 1e-9


def test_the_three_phases_are_marked_with_distinct_shapes_and_the_event_indices(geometry):
    markers = geometry["markers"]

    assert [marker["phase"] for marker in markers] == ["range", "breakdown", "recovery"]
    assert [marker["shape"] for marker in markers] == ["rect", "triangle-down", "triangle-up"], (
        "三個相位必須用不同形狀（不得只靠顏色）"
    )
    assert markers[0]["from"] == RANGE_START and markers[0]["to"] == RANGE_END
    assert markers[1]["index"] == BREAKDOWN_INDEX
    assert markers[2]["index"] == RECOVERY_INDEX


def test_every_marker_x_matches_the_candle_of_that_index(geometry):
    """AC-043 的核心：標記的水平位置與 JSON 事件索引一致。"""
    xs = dict(zip([0, 29, 30, 49, 50, 51, 73], geometry["x"]))

    for marker in geometry["markers"]:
        if "index" in marker:
            assert marker["x"] == pytest.approx(xs[marker["index"]]), marker
        else:
            assert marker["x"] == pytest.approx(xs[marker["from"]]), marker
            assert marker["x2"] == pytest.approx(xs[marker["to"]]), marker

    assert geometry["candlesDrawn"] == 74
    assert geometry["firstCandleX"] == pytest.approx(geometry["x"][0])
    assert geometry["lastCandleX"] == pytest.approx(geometry["x"][-1])


def test_the_text_summary_states_every_phase(geometry):
    summary = "\n".join(geometry["summary"])

    assert "盤整" in summary
    assert "假跌破" in summary or "跌破" in summary
    assert "回歸" in summary
    assert str(RANGE_START) in summary and str(RANGE_END) in summary
    assert str(BREAKDOWN_INDEX) in summary and str(RECOVERY_INDEX) in summary
    assert "信心" in summary


def test_events_endpoint_echoes_the_effective_spec(service):
    import dataclasses as dc

    payload = call(service.host, service.port, "GET", "/api/patterns/events?symbol=2330&interval=1d").json()

    assert payload["spec"] == dc.asdict(expected_spec(service.app))
    assert payload["pattern_id"] == service.app.settings["pattern_id"]


def test_a_stock_market_uses_the_stock_defaults(service):
    """設定裡的市場別必須真的改變使用的規格（AC-035 的市場別預設接進服務）。"""
    import dataclasses as dc

    from ediaad.markets.calendar import default_spec_for

    service.app.settings = {**service.app.settings, "market": "stock"}

    payload = call(service.host, service.port, "GET", "/api/patterns/events?symbol=2330&interval=1d").json()

    stock = dc.asdict(default_spec_for("stock", {"pattern_id": "range_fakeout_reversion"}))
    crypto = dc.asdict(default_spec_for("crypto", {"pattern_id": "range_fakeout_reversion"}))
    assert payload["spec"] == stock
    assert payload["spec"] != crypto


def test_an_explicit_pattern_spec_from_settings_is_used(service, tmp_path):
    import dataclasses as dc

    from ediaad.patterns import NAMED_PATTERNS, PatternSpec

    override = PatternSpec(
        **{**NAMED_PATTERNS["range_fakeout_reversion"], "range_bars_min": 5, "range_bars_max": 20}
    )
    service.app.settings = {
        **service.app.settings,
        "pattern_spec": dc.asdict(override),
        "pattern_id": override.pattern_id,
    }

    payload = call(service.host, service.port, "GET", "/api/patterns/events?symbol=2330&interval=1d").json()

    assert payload["spec"] == dc.asdict(override)
    assert payload["spec"]["range_bars_max"] == 20


def test_the_catalog_resolves_the_source_for_a_symbol(tmp_path):
    """catalog 是「哪個商品該問哪個來源」的權威對照：命中時就用它，不必明示 source。"""
    from ediaad.app import Application
    from ediaad.config import DEFAULT_SETTINGS, save_settings_atomic
    from ediaad.markets.catalog import Catalog, save_catalog
    from ediaad.markets.base import Instrument

    home = tmp_path / "home"
    save_settings_atomic(home / "settings.json", DEFAULT_SETTINGS)
    save_catalog(
        Catalog(
            catalog_version="2026-10-01",
            instruments=(
                Instrument(symbol="2330", interval="1d", source_id="twse", display_name="台積電"),
            ),
        ),
        home / "catalog.json",
    )
    app = Application.create(home=home)
    assert app.catalog is not None, "有 catalog 檔時必須載入"
    server = app.start(port=0)
    host, port = server.socket.getsockname()[:2]
    try:
        # catalog 說 2330 屬於 twse（只支援日線）；要求 1h 必須在**連網之前**被擋下。
        response = call(host, port, "GET", "/api/series?symbol=2330&interval=1h")
        assert response.status == 400, "來源由 catalog 決定，因此 twse 的週期限制適用"
        assert "1h" in response.json()["error"]["message"]
    finally:
        app.stop()
        app.close()
