"""規律參數即時預覽與範例學習（TASK-023）。

觀察邊界：
1. **後端契約（自動）**：`POST /api/pattern/preview` 與 `POST /api/pattern/learn` 的
   JSON 回應與狀態碼，以及「端點回傳的命中次數與直接呼叫 `ediaad.patterns.detect`
   的事件數完全相同」。以合成序列與合成範例注入，完全離線。
2. **前端（自動，需 `node`）**：`params.js`／`learn.js` 的白話參數對應、輸入轉型與
   去抖動以 Node 載入該檔驗證（與 TASK-022 的 `chart.js` 相同作法）。
3. **感受（人工）**：在 Chrome（Wayland）實際拖動參數量的 1 秒內延遲，見 TDD 紀錄。
"""

from __future__ import annotations

import dataclasses
import http.client
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from ediaad.errors import ConfigError
from ediaad.patterns import (
    LEARN_MIN_BARS,
    NAMED_PATTERNS,
    PatternSpec,
    detect,
    from_json,
    learn,
    to_json,
)

# 與 TASK-008／TASK-022 相同的植入方式（索引 30 之前的深谷把盤整區間限制在 30～49）。
PROJECT_DIR = Path(__file__).resolve().parent.parent

RANGE_START = 30
RANGE_END = 49
BREAKDOWN_INDEX = 50
RECOVERY_INDEX = 51

#: 面板送出的白話參數＝ `PatternSpec` 欄位（標籤 ↔ 欄位的對應在 `params.js`）。
BASE_PARAMS: dict[str, object] = dict(NAMED_PATTERNS["range_fakeout_reversion"])


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
    connection = http.client.HTTPConnection(host, port, timeout=10)
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


def build_planted_series(*, bars: int | None = None) -> pd.DataFrame:
    """與 TASK-008 相同的植入方式：盤整（30～49）→ 假跌破（50）→ 回歸（51）。"""
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

    for index in range(22):
        base = 100.0 if index % 2 == 0 else 100.4
        closes.append(base)
        highs.append(base + 1.0)
        lows.append(base - 1.0)

    times = pd.date_range("2024-01-01T00:00:00Z", periods=len(closes), freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "time": times,
            "open": [value - 0.1 for value in closes],
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000.0] * len(closes),
        }
    )
    return frame if bars is None else frame.iloc[:bars].reset_index(drop=True)


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
    seed_cache(app, "SHORT", "1d", build_planted_series(bars=5))
    server = app.start(port=0)
    host, port = server.socket.getsockname()[:2]
    try:
        yield SimpleNamespace(
            app=app, server=server, host=host, port=port, home=tmp_path / "home"
        )
    finally:
        app.stop()
        app.close()


def preview_body(**overrides) -> dict:
    body: dict = {"symbol": "2330", "interval": "1d", "params": dict(BASE_PARAMS)}
    body.update(overrides)
    return body


def spec_for(params: dict) -> PatternSpec:
    return PatternSpec(**params)


def preview(service, body: dict) -> Response:
    return call(service.host, service.port, "POST", "/api/pattern/preview", body)


# ---- AC-044：參數即時預覽 ---------------------------------------------------


def test_preview_hits_equal_the_detect_event_count(service):
    """第一個失敗行為：端點不存在（404）；實作後次數必須與核心函式相同且可重現。"""
    first = preview(service, preview_body())
    second = preview(service, preview_body())

    assert first.status == 200
    assert second.status == 200
    assert first.json()["hits"] == second.json()["hits"]
    # 同一輸入重跑結果位元相同（無隨機性）
    assert first.body == second.body

    expected = len(detect(build_planted_series(), spec_for(dict(BASE_PARAMS))))
    assert expected == 1  # 夾具本身要先確認命中，否則斷言沒有意義
    assert first.json()["hits"] == expected


def test_preview_hits_track_a_parameter_and_return_to_the_original_value(service):
    """改動任一白話參數 → 次數改變；改回原值 → 回到原本次數（AC-044）。"""
    original = preview(service, preview_body()).json()
    tightened = preview(
        service, preview_body(params={**BASE_PARAMS, "range_bars_min": 21})
    ).json()
    restored = preview(service, preview_body()).json()

    assert original["hits"] == 1
    assert tightened["hits"] == 0
    assert restored["hits"] == original["hits"]


def test_preview_returns_the_effective_parameters(service):
    """回應要帶實際採用的參數（供面板顯示與「設定 → 規格」對照）。"""
    params = {**BASE_PARAMS, "recovery_bars_max": 7}
    payload = preview(service, preview_body(params=params)).json()

    assert payload["params"] == dataclasses.asdict(spec_for(params))
    assert set(payload["params"]) == {
        field.name for field in dataclasses.fields(PatternSpec)
    }
    assert payload["symbol"] == "2330"
    assert payload["interval"] == "1d"
    # 前後空白一律去除：送進來的商品代號與回應、查詢用的代號是同一個
    padded = preview(service, preview_body(symbol="  2330  ", interval=" 1d ")).json()
    assert padded["symbol"] == "2330" and padded["interval"] == "1d"
    assert padded["hits"] == payload["hits"]
    assert payload["source"] == "csv"
    assert payload["bars"] == len(build_planted_series())
    assert payload["status"] == "evaluated"


def test_preview_without_params_uses_the_settings_derived_spec(service):
    """省略參數時用「設定 → 市場別預設 ＋ pattern_id」的規格（不另立預設值）。"""
    from ediaad.markets.calendar import default_spec_for

    payload = preview(service, {"symbol": "2330", "interval": "1d"}).json()
    expected = default_spec_for(
        service.app.settings["market"], {"pattern_id": service.app.settings["pattern_id"]}
    )

    assert payload["params"] == dataclasses.asdict(expected)
    assert payload["hits"] == len(detect(build_planted_series(), expected))

def test_preview_accepts_parameters_at_the_top_level(service):
    """白話參數可以在頂層或 `params` 內；兩者結果相同。"""
    nested = preview(service, preview_body()).json()
    flat = preview(service, {"symbol": "2330", "interval": "1d", **BASE_PARAMS}).json()

    assert flat["hits"] == nested["hits"]
    assert flat["params"] == nested["params"]


def test_preview_partial_parameters_override_the_settings_default(service):
    """只送一個參數時，其餘沿用設定；被覆寫者真的生效。"""
    payload = preview(
        service, {"symbol": "2330", "interval": "1d", "params": {"range_bars_min": 21}}
    ).json()
    from ediaad.markets.calendar import default_spec_for

    expected = default_spec_for(
        service.app.settings["market"], {"pattern_id": service.app.settings["pattern_id"]}
    )
    assert payload["params"]["range_bars_min"] == 21
    assert payload["params"]["range_bars_max"] == expected.range_bars_max
    assert payload["hits"] == 0


def test_preview_answers_within_one_second(service):
    """AC-044 的「1 秒內」：整個請求往返（取序列 → `detect` → JSON）必須在 1 秒內。

    第一次請求要付出載入資料與暖機的成本，因此先暖機再計時；門檻與 SPEC 第 6 節一致。
    """
    preview(service, preview_body())  # 暖機

    start = time.perf_counter()
    response = preview(service, preview_body())
    elapsed = time.perf_counter() - start

    assert response.status == 200
    assert elapsed < 1.0, f"參數預覽往返耗時 {elapsed:.3f} 秒，超過 1 秒"


def test_preview_hits_match_the_events_endpoint_for_the_same_spec(service):
    """`hits` 與 `GET /api/patterns/events` 的事件數一致（同一組參數、同一份序列）。"""
    events = call(
        service.host, service.port, "GET", "/api/patterns/events?symbol=2330&interval=1d"
    ).json()
    payload = preview(service, preview_body()).json()

    assert events["status"] == "evaluated"
    assert payload["hits"] == len(events["events"]) == 1


def test_preview_response_is_json(service):
    response = preview(service, preview_body())
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["status"] == "evaluated"


def test_preview_honours_limit(service):
    """`limit` 決定評估的根數（與序列端點同一條路徑）：取最近 N 根。"""
    frame = build_planted_series()
    tail_52 = frame.iloc[-52:].reset_index(drop=True)  # 仍完整涵蓋盤整 30～49 與回歸 51
    limited = preview(service, preview_body(limit=52)).json()

    assert limited["bars"] == 52
    assert limited["status"] == "evaluated"
    assert limited["hits"] == len(detect(tail_52, spec_for(dict(BASE_PARAMS)))) == 1

    # 只看最近 25 根（結構的盤整相位已被切掉）→ 評估後沒有命中，而不是資料不足
    truncated = preview(service, preview_body(limit=25)).json()
    assert truncated["bars"] == 25
    assert truncated["status"] == "evaluated"
    assert truncated["hits"] == 0
    assert "沒有命中" in truncated["message"]

    short = preview(service, preview_body(limit=20)).json()
    assert short["bars"] == 20
    assert short["status"] == "insufficient"  # 20 根放不進 20 根的盤整（需要 min+1）
    assert short["hits"] == 0

    assert preview(service, preview_body()).json()["bars"] == len(frame)


# ---- AC-044：不合法輸入 -----------------------------------------------------


def _assert_bad(response: Response, fragment: str) -> dict:
    assert response.status == 400, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert "Traceback" not in response.text
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"
    assert fragment in payload["error"]["message"]
    return payload


def test_preview_rejects_inverted_range_bars(service):
    """`range_bars_min > range_bars_max` → 400 並指出兩個欄位名。"""
    payload = _assert_bad(
        preview(
            service,
            preview_body(params={**BASE_PARAMS, "range_bars_min": 30, "range_bars_max": 20}),
        ),
        "range_bars_min",
    )
    assert "range_bars_max" in payload["error"]["message"]


def test_preview_rejects_negative_and_non_numeric_parameters(service):
    _assert_bad(
        preview(service, preview_body(params={**BASE_PARAMS, "atr_period": -3})),
        "atr_period",
    )
    _assert_bad(
        preview(service, preview_body(params={**BASE_PARAMS, "range_bars_max": "abc"})),
        "range_bars_max",
    )
    _assert_bad(
        preview(service, preview_body(params={**BASE_PARAMS, "band_atr_multiple_max": ""})),
        "band_atr_multiple_max",
    )


def test_preview_rejects_unknown_recovery_target(service):
    payload = _assert_bad(
        preview(service, preview_body(params={**BASE_PARAMS, "recovery_target": "range_low"})),
        "recovery_target",
    )
    assert "range_mean" in payload["error"]["message"]


def test_preview_rejects_unknown_parameter_names(service):
    """打錯字的參數不得被默默忽略。"""
    payload = _assert_bad(
        preview(service, preview_body(params={**BASE_PARAMS, "range_bars_minn": 21})),
        "range_bars_minn",
    )
    assert "range_bars_min" in payload["error"]["message"]

    _assert_bad(
        preview(service, preview_body(params={**BASE_PARAMS, "recovery_bars": 3})),
        "recovery_bars",
    )


def test_preview_requires_symbol_and_interval(service):
    _assert_bad(preview(service, {"interval": "1d"}), "symbol")
    _assert_bad(preview(service, {"symbol": "2330"}), "interval")
    _assert_bad(preview(service, {"symbol": "  ", "interval": "1d"}), "symbol")
    _assert_bad(preview(service, {"symbol": 2330, "interval": "1d"}), "symbol")


def test_preview_rejects_a_body_that_is_not_an_object(service):
    _assert_bad(preview(service, ["symbol", "2330"]), "JSON 物件")
    _assert_bad(preview(service, "symbol=2330"), "JSON 物件")
    _assert_bad(
        preview(service, {"symbol": "2330", "interval": "1d", "params": [1, 2]}),
        "params",
    )
    # 沒有主體（Content-Length: 0）→ 訊息必須說「必填」，而不是含糊的型別錯誤
    empty = call(service.host, service.port, "POST", "/api/pattern/preview")
    payload = _assert_bad(empty, "主體")
    assert "必填" in payload["error"]["message"]


def test_preview_rejects_unknown_fields_and_bad_limit(service):
    _assert_bad(preview(service, preview_body(symobl="2330")), "symobl")
    payload = _assert_bad(preview(service, preview_body(limit="abc")), "limit")
    assert "整數" in payload["error"]["message"]
    _assert_bad(preview(service, preview_body(limit=10_001)), "10000")
    _assert_bad(preview(service, preview_body(source="no-such-source")), "no-such-source")


def test_preview_errors_never_leak_a_traceback(service):
    bad_bodies = [
        preview_body(params={**BASE_PARAMS, "range_bars_min": 0}),
        preview_body(params={**BASE_PARAMS, "band_atr_multiple_max": 0}),
        preview_body(params={**BASE_PARAMS, "recovery_target": ""}),
        preview_body(limit=-1),
    ]
    for body in bad_bodies:
        response = preview(service, body)
        assert response.status == 400, response.text
        assert "Traceback" not in response.text
        assert response.json()["error"]["message"].strip()


# ---- F-003：資料不足不得與「評估後沒有命中」混淆 -----------------------------


def test_preview_keeps_insufficient_and_no_hit_apart(service):
    insufficient = preview(service, {"symbol": "SHORT", "interval": "1d"}).json()
    no_hit = preview(
        service, preview_body(params={**BASE_PARAMS, "range_bars_min": 21})
    ).json()

    assert insufficient["status"] == "insufficient"
    assert insufficient["hits"] == 0
    assert "21" in insufficient["message"] and "5" in insufficient["message"]

    assert no_hit["status"] == "evaluated"
    assert no_hit["hits"] == 0
    assert "沒有命中" in no_hit["message"]
    assert insufficient["message"] != no_hit["message"]
    assert insufficient["bars"] == 5


# ---- AC-045：範例學習 -------------------------------------------------------


def build_example_series() -> pd.DataFrame:
    """範例＝目前商品上的一段（索引 25～55，含盤整 30～49、跌破 50、回歸 51）。"""
    return build_planted_series().iloc[25:56].reset_index(drop=True)


def example_csv() -> str:
    return build_example_series().to_csv(index=False)


def learned_spec() -> PatternSpec:
    return learn(build_example_series())


def learn_call(service, body: dict) -> Response:
    return call(service.host, service.port, "POST", "/api/pattern/learn", body)


def test_learn_returns_the_learned_spec_and_a_hit_preview(service):
    """第一個失敗行為：端點不存在（404）；實作後須回推估參數與命中預覽。"""
    response = learn_call(
        service, {"csv": example_csv(), "symbol": "2330", "interval": "1d"}
    )
    assert response.status == 200, response.text
    payload = response.json()
    expected = learned_spec()

    assert payload["spec"] == dataclasses.asdict(expected)
    assert payload["spec_json"] == to_json(expected)
    assert from_json(payload["spec_json"]) == expected
    assert set(payload["spec"]) == {
        field.name for field in dataclasses.fields(PatternSpec)
    }
    assert payload["sample_bars"] == len(build_example_series()) == 31
    assert payload["status"] == "evaluated"
    assert payload["symbol"] == "2330" and payload["interval"] == "1d"
    assert payload["source"] == "csv"
    assert payload["bars"] == len(build_planted_series())
    # 命中預覽＝以推估規格對目前商品呼叫 detect 的事件數
    assert payload["hits"] == len(detect(build_planted_series(), expected)) == 1


def test_learn_is_deterministic(service):
    """同一範例重跑兩次，推估結果完全相同（無隨機、無搜尋）。"""
    body = {"csv": example_csv(), "symbol": "2330", "interval": "1d"}
    first = learn_call(service, body)
    second = learn_call(service, body)

    assert first.body == second.body
    assert first.json()["spec_json"] == to_json(learned_spec())


def test_learn_without_an_instrument_returns_only_the_spec(service):
    """沒有目前商品時仍可學習，但必須明說沒有命中預覽（不得假裝有）。"""
    payload = learn_call(service, {"csv": example_csv()}).json()

    assert payload["spec"] == dataclasses.asdict(learned_spec())
    assert payload["hits"] is None
    assert payload["bars"] is None
    assert payload["status"] == "no_preview"
    assert "預覽" in payload["message"]


def test_learn_reports_a_short_sample_with_a_readable_reason(service):
    """範例不足 `LEARN_MIN_BARS` 根 → 400 附明確原因，且不得回傳隨意參數。"""
    short = build_planted_series(bars=5).to_csv(index=False)
    response = learn_call(service, {"csv": short})

    assert response.status == 400
    assert "spec" not in response.json()
    message = response.json()["error"]["message"]
    assert str(LEARN_MIN_BARS) in message and "5" in message
    assert "Traceback" not in response.text


def test_learn_reports_an_unlearnable_sample(service):
    """單調上升的範例沒有跌破相位 → 400 附原因，不得回傳隨意參數。"""
    frame = build_planted_series()
    ramp = frame.copy()
    ramp["close"] = [100.0 + index for index in range(len(ramp))]
    ramp["high"] = [value + 1.0 for value in ramp["close"]]
    ramp["low"] = [value - 1.0 for value in ramp["close"]]

    response = learn_call(service, {"csv": ramp.to_csv(index=False)})
    assert response.status == 400
    assert "spec" not in response.json()
    assert "跌破" in response.json()["error"]["message"]


def test_learn_reports_a_malformed_csv_with_the_column_name(service):
    """缺欄位的範例 → 400 指出欄位名，且訊息不洩漏伺服器暫存路徑。"""
    missing = build_example_series().drop(columns=["close"]).to_csv(index=False)
    response = learn_call(service, {"csv": missing})

    assert response.status == 400
    payload = response.json()
    assert "close" in payload["error"]["message"]
    assert "範例 CSV" in payload["error"]["message"]
    assert "/tmp/" not in payload["error"]["message"]
    assert "Traceback" not in response.text

    header_only = learn_call(service, {"csv": "time,open,high,low,close,volume"})
    assert header_only.status == 400
    assert "範例 CSV" in header_only.json()["error"]["message"]


def test_learn_requires_the_csv_field(service):
    _assert_bad(learn_call(service, {"symbol": "2330"}), "csv")
    _assert_bad(learn_call(service, {"csv": ""}), "csv")
    _assert_bad(learn_call(service, {"csv": "   "}), "csv")
    _assert_bad(learn_call(service, {"csv": [1, 2]}), "csv")
    _assert_bad(learn_call(service, ["csv"]), "JSON 物件")
    _assert_bad(learn_call(service, {"csv": example_csv(), "symobl": "2330"}), "symobl")


def test_learn_preview_uses_the_requested_source_and_limit(service):
    truncated = learn_call(
        service,
        {"csv": example_csv(), "symbol": "2330", "interval": "1d", "limit": 20},
    ).json()
    assert truncated["bars"] == 20
    # 推估規格的盤整下限為 10 → 需要 11 根；20 根足夠，但切掉盤整相位後沒有命中
    assert truncated["status"] == "evaluated"
    assert truncated["hits"] == 0

    short = learn_call(
        service, {"csv": example_csv(), "symbol": "SHORT", "interval": "1d"}
    ).json()
    assert short["bars"] == 5
    assert short["status"] == "insufficient"
    assert short["hits"] == 0
    assert "資料不足" in short["message"]
    # 需要幾根必須由「推估出的規格」決定（range_bars_min + 1），不是常數
    assert str(learned_spec().range_bars_min + 1) in short["message"]

    _assert_bad(
        learn_call(
            service,
            {"csv": example_csv(), "symbol": "2330", "interval": "1d", "source": "nope"},
        ),
        "nope",
    )
    _assert_bad(
        learn_call(service, {"csv": example_csv(), "symbol": "2330"}), "interval"
    )


def test_learn_errors_never_leak_a_traceback(service):
    bad_bodies = [
        {"csv": build_planted_series(bars=3).to_csv(index=False)},
        {"csv": "time,open\n2024-01-01,1\n"},
        {"csv": example_csv(), "limit": "abc"},
        {"csv": example_csv(), "symbol": 2330, "interval": "1d"},
    ]
    for body in bad_bodies:
        response = learn_call(service, body)
        assert response.status == 400, response.text
        assert "Traceback" not in response.text
        assert response.json()["error"]["message"].strip()


def test_learn_sample_errors_from_the_core_are_not_swallowed(service):
    """核心 `learn` 的 `ConfigError` 原樣呈現（不吞掉、不改寫成別的錯誤）。"""
    too_short = build_planted_series(bars=LEARN_MIN_BARS - 1).to_csv(index=False)
    try:
        learn(build_planted_series(bars=LEARN_MIN_BARS - 1))
    except ConfigError as error:
        expected = str(error)
    else:  # pragma: no cover - 夾具本身應該要失敗
        raise AssertionError("夾具應無法推估")

    response = learn_call(service, {"csv": too_short})
    assert response.status == 400
    assert response.json()["error"]["message"] == expected


# ---- AC-044／AC-045：前端面板（以 Node 載入 params.js／learn.js 驗證） --------

NODE = shutil.which("node")

PANEL_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const context = {console: console, setTimeout: setTimeout, clearTimeout: clearTimeout};
context.window = context;
vm.createContext(context);
["params.js", "learn.js"].forEach(function (name) {
  vm.runInContext(fs.readFileSync(name, "utf8"), context);
});

const params = context.ediaadParams;
const learnUi = context.ediaadLearn;
if (!params || !learnUi) {
  throw new Error("params.js／learn.js 必須在 window 上匯出功能");
}

function caught(fn) {
  try {
    fn();
  } catch (error) {
    return String(error.message || error);
  }
  return null;
}

const report = {
  labels: params.FIELD_LABELS,
  order: params.FIELD_ORDER,
  typed: params.toParams({
    pattern_id: "range_fakeout_reversion",
    range_bars_min: "21",
    range_bars_max: "120",
    band_atr_multiple_max: "3.5",
    atr_period: "14",
    breakdown_bars_max: "2",
    breakdown_depth_band_min: "0.2",
    breakdown_depth_band_max: "1.5",
    recovery_bars_max: "5",
    recovery_target: "range_mean"
  }),
  types: {},
  errors: {
    intText: caught(() => params.toParams({atr_period: "abc"})),
    intDecimal: caught(() => params.toParams({atr_period: "14.5"})),
    blank: caught(() => params.toParams({range_bars_min: "  "})),
    unknown: caught(() => params.toParams({range_bars_min: 20, range_bars_minn: 1})),
    notInteger: caught(() => params.parseValue("atr_period", 14.5)),
    badTarget: caught(() => params.parseValue("recovery_target", "range_low"))
  },
  hits: {
    some: params.describeHits({status: "evaluated", hits: 3, message: ""}),
    none: params.describeHits({status: "evaluated", hits: 0, message: "評估後沒有命中"}),
    insufficient: params.describeHits({status: "insufficient", hits: 0, message: "資料不足，無法評估：需要至少 21 根，實際 5 根"}),
    noPreview: params.describeHits({status: "no_preview", hits: null, message: ""})
  },
  body: params.buildBody("  2330  ", "1d", {range_bars_min: "21"}),
  learnBody: learnUi.buildLearnBody("time,close\n", "2330", "1d"),
  learnBodyNoInstrument: learnUi.buildLearnBody("time,close\n", "", ""),
  learnLines: learnUi.describeLearnResult({
    spec: {pattern_id: "learned_range_fakeout_reversion", range_bars_min: 10, range_bars_max: 30,
           band_atr_multiple_max: 1.44, atr_period: 14, breakdown_bars_max: 1,
           breakdown_depth_band_min: 0.58, breakdown_depth_band_max: 1.08,
           recovery_bars_max: 3, recovery_target: "range_mean"},
    spec_json: "{\"atr_period\": 14}",
    sample_bars: 31,
    status: "evaluated",
    hits: 1,
    message: ""
  }),
  learnLinesInsufficient: learnUi.describeLearnResult({
    spec: {pattern_id: "learned_range_fakeout_reversion", range_bars_min: 10},
    spec_json: "{}",
    sample_bars: 31,
    status: "insufficient",
    hits: 0,
    message: "資料不足，無法評估：需要至少 11 根，實際 5 根"
  }),
  learnError: learnUi.describeLearnError({error: {code: "invalid_request", message: "範例至少需要 12 根 K 線"}}),
  learnErrorFallback: learnUi.describeLearnError(null)
};
Object.keys(report.typed).forEach(function (name) {
  report.types[name] = typeof report.typed[name];
});

// 去抖動：以**假計時器**觀察排程（不用真實時間，避免負載造成不穩定）。
const timers = [];
let nextTimerId = 0;
context.setTimeout = function (fn, delay) {
  nextTimerId += 1;
  timers.push({id: nextTimerId, fn: fn, delay: delay, cleared: false});
  return nextTimerId;
};
context.clearTimeout = function (id) {
  timers.forEach(function (timer) {
    if (timer.id === id) {
      timer.cleared = true;
    }
  });
};

const calls = [];
const debounced = params.makeDebouncer(function (value) {
  calls.push(value);
});
debounced("a");
debounced("b");
debounced("c");
report.debounceMs = params.DEBOUNCE_MS;
report.debounceTimers = timers.map(function (timer) {
  return {delay: timer.delay, cleared: timer.cleared};
});
const pending = timers.filter(function (timer) {
  return !timer.cleared;
});
report.debouncePending = pending.length;
pending.forEach(function (timer) {
  timer.fn();
});
report.debounceCalls = calls.slice();

// 之後再一次輸入也必須被送出（不是「只送一次」）
const beforeD = timers.length;
debounced("d");
timers.slice(beforeD).forEach(function (timer) {
  timer.fn();
});
report.debounceCallsAfter = calls.slice();

process.stdout.write(JSON.stringify(report));
"""


def panel_report() -> dict:
    """以 Node 載入 `params.js`／`learn.js` 的純函式並取回結果。"""
    static = PROJECT_DIR / "ediaad" / "web" / "static"
    completed = subprocess.run(
        [NODE, "-e", PANEL_HARNESS],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(static),
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def panel():
    if NODE is None:
        pytest.skip("需要 node 才能驗證 params.js／learn.js 的純函式（僅測試期依賴）")
    return panel_report()


def test_params_js_is_served(service):
    response = call(service.host, service.port, "GET", "/static/params.js")

    assert response.status == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "ediaadParams" in response.text
    assert "/api/pattern/preview" in response.text


def test_learn_js_is_served(service):
    response = call(service.host, service.port, "GET", "/static/learn.js")

    assert response.status == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "ediaadLearn" in response.text
    assert "/api/pattern/learn" in response.text


def test_frontend_does_not_reimplement_the_engine(service):
    """判定與推估只在後端（`detect`／`learn`）；前端不得自己算。"""
    for name in ("params.js", "learn.js"):
        text = call(service.host, service.port, "GET", f"/static/{name}").text
        assert "detect(" not in text, name
        assert "atr(" not in text, name
        assert "Math.exp" not in text, name


def test_index_html_wires_the_panel_and_the_learn_form(service):
    text = call(service.host, service.port, "GET", "/").text

    assert "/static/params.js" in text and "/static/learn.js" in text
    assert 'id="param-panel"' in text and 'id="param-hits"' in text
    assert 'id="learn-form"' in text and 'id="learn-csv"' in text
    assert 'id="learn-file"' in text and 'id="learn-result"' in text
    for name in ("range_bars_min", "recovery_bars_max"):
        assert f'data-param="{name}"' in text


def test_field_labels_cover_every_spec_field(panel):
    fields = {
        field.name for field in dataclasses.fields(PatternSpec)
    }
    assert set(panel["labels"]) == fields
    assert set(panel["order"]) == fields
    assert all(label.strip() for label in panel["labels"].values())
    # 白話標籤必須真的是中文說明（不是英文欄位名照抄）
    assert panel["labels"]["range_bars_min"] != "range_bars_min"


def test_panel_converts_plain_values_to_typed_parameters(panel):
    typed = panel["typed"]

    assert typed["range_bars_min"] == 21 and panel["types"]["range_bars_min"] == "number"
    assert typed["band_atr_multiple_max"] == 3.5
    assert typed["pattern_id"] == "range_fakeout_reversion"
    assert typed["recovery_target"] == "range_mean"
    # 整數欄位不得變成浮點（`PatternSpec` 只收 int）
    assert float(typed["atr_period"]).is_integer()


def test_panel_rejects_bad_values_with_the_field_name(panel):
    errors = panel["errors"]

    assert "atr_period" in errors["intText"]
    assert "atr_period" in errors["intDecimal"]
    assert "range_bars_min" in errors["blank"]
    assert "range_bars_minn" in errors["unknown"]
    assert "atr_period" in errors["notInteger"]
    assert "recovery_target" in errors["badTarget"]
    assert "range_mean" in errors["badTarget"]


def test_panel_describes_hits_without_confusing_insufficient(panel):
    hits = panel["hits"]

    assert "3" in hits["some"]
    assert "沒有命中" in hits["none"]
    assert "資料不足" in hits["insufficient"]
    assert hits["insufficient"] != hits["none"]
    assert "預覽" in hits["noPreview"]


def test_panel_builds_the_request_bodies(panel):
    assert panel["body"] == {
        "symbol": "2330",
        "interval": "1d",
        "params": {"range_bars_min": 21},
    }
    assert panel["learnBody"] == {"csv": "time,close\n", "symbol": "2330", "interval": "1d"}
    assert panel["learnBodyNoInstrument"] == {"csv": "time,close\n"}


def test_panel_renders_the_learned_spec_and_reason(panel):
    lines = "\n".join(panel["learnLines"])

    assert "learned_range_fakeout_reversion" in lines
    for value in ("range_bars_min", "recovery_bars_max"):
        assert panel["labels"][value] in lines
    assert "1" in lines  # 命中數
    assert "無法評估" in "\n".join(panel["learnLinesInsufficient"])
    assert "資料不足" in "\n".join(panel["learnLinesInsufficient"])
    assert "範例至少需要 12 根 K 線" in panel["learnError"]
    assert "無法" in panel["learnErrorFallback"]


def test_panel_debounces_rapid_edits(panel):
    """連續輸入只送最後一次，且等待視窗必須是宣告的 `DEBOUNCE_MS`（不是 0）。"""
    assert panel["debounceMs"] > 0
    assert [timer["delay"] for timer in panel["debounceTimers"]] == [
        panel["debounceMs"]
    ] * 3
    assert [timer["cleared"] for timer in panel["debounceTimers"]] == [True, True, False]
    assert panel["debouncePending"] == 1
    assert panel["debounceCalls"] == ["c"]
    assert panel["debounceCallsAfter"] == ["c", "d"]
