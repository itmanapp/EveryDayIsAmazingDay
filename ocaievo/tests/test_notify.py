"""三管道通知（TASK-027／AC-051）。

觀察邊界：
1. **命令組裝與錯誤處理（自動）**：`DesktopNotifier` 以假 runner 觀察真正要執行的 argv、
   以假 `which`／`env` 觀察「命令不存在」與「沒有 session bus」的跳過與警告；runner
   回傳非 0 或丟出 `OSError` 都只記 warning，不得中斷監控迴圈。
2. **推播（自動）**：`WebNotifier`／`BrowserNotifier` 以假 hub 觀察 `publish` 的參數，
   並以**真的** `SSEHub` 驗證兩個事件型別都送達訂閱者、沒有訂閱者時仍然靜默。
3. **去重（自動）**：以 `monitor.run_once` 三輪（同一事件、同一事件、新事件）驗證通知
   次數為 1、0、1（AC-023 的去重不被通知層繞過）。
4. **前端（自動，需 `node`）**：`notify.js` 的純函式（支援判斷、權限、顯示）以假
   `Notification` 建構子驗證。
5. **Linux 實機（人工）**：`notify-send` 是否真的彈出、macOS／Windows 命令是否可用，
   依 SPEC 第 7 節人工檢查；自動測試**不執行**真的通知命令。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from ediaad.errors import EdiaadError
from ediaad.notify import build_notifiers
from ediaad.notify.browser import BrowserNotifier, notification_for
from ediaad.notify.desktop import DesktopNotifier, command_for
from ediaad.notify.message import notification_text
from ediaad.notify.web import WebNotifier
from ediaad.web.sse_hub import SSEHub, event_id_for

PROJECT_DIR = Path(__file__).resolve().parent.parent


def event_payload(**overrides) -> dict:
    """一筆命中事件（`monitor.EVENT_FIELDS` 的九個欄位）。"""
    payload = {
        "symbol": "2330",
        "interval": "1d",
        "pattern_id": "range_fakeout_reversion",
        "event_start_time": "2024-01-02T00:00:00+00:00",
        "event_end_time": "2024-01-04T00:00:00+00:00",
        "confidence": 0.8125,
        "detected_at": "2024-01-05T00:00:00+00:00",
        "history_up_probability": 0.5,
        "history_samples": 4,
    }
    payload.update(overrides)
    return payload


class FakeHub:
    """記錄 `publish` 呼叫的假 hub（不涉及任何執行緒或佇列）。"""

    def __init__(self, *, publish_result: str | None = "id") -> None:
        self.calls: list[tuple[dict, str]] = []
        self.publish_result = publish_result

    def publish(self, payload, *, event: str = "alert"):
        self.calls.append((dict(payload), event))
        return self.publish_result


class Recorder:
    """記錄 runner 的 argv 與警告；可指定回傳值或丟出例外。"""

    def __init__(self, *, returncode: int = 0, raises: BaseException | None = None) -> None:
        self.commands: list[list[str]] = []
        self.warnings: list[str] = []
        self.returncode = returncode
        self.raises = raises

    def run(self, argv, **_kwargs):
        self.commands.append(list(argv))
        if self.raises is not None:
            raise self.raises

        class Completed:
            returncode = self.returncode

        return Completed()

    def warn(self, message: str) -> None:
        self.warnings.append(message)


# ---- AC-051：桌面通知的命令組裝與錯誤處理 -----------------------------------


def test_command_for_linux_uses_notify_send():
    command = command_for("linux", "標題", "內容")

    assert command[0] == "notify-send"
    assert "標題" in command and "內容" in command


def test_desktop_notifier_runs_notify_send_with_the_event_fields():
    """第一個失敗行為：模組不存在（collection error）；實作後必須真的組出命令。"""
    recorder = Recorder()
    notifier = DesktopNotifier(
        platform="linux",
        runner=recorder.run,
        warn=recorder.warn,
        env={"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"},
    )

    notifier.notify(event_payload())

    assert len(recorder.commands) == 1
    argv = recorder.commands[0]
    title, body = notification_text(event_payload())
    assert argv[0] == "notify-send"
    assert argv[1] == title, "第二個參數必須是標題（notify-send 的介面順序）"
    assert argv[2] == body, "第三個參數必須是內容"
    assert "2330" in " ".join(argv)
    assert "2024-01-02T00:00:00+00:00" in " ".join(argv)
    assert recorder.warnings == []


def test_command_for_macos_and_windows_is_generated_but_never_run():
    macos = command_for("darwin", "標題", "內容")
    windows = command_for("win32", "標題", "內容")
    unsupported = command_for("freebsd", "標題", "內容")

    assert macos[0] == "osascript" and "display notification" in " ".join(macos)
    assert windows[0].lower().startswith("powershell")
    assert "Toast" in " ".join(windows)
    assert unsupported == []

    # 引號必須被跳脫，否則標題裡的引號會讓 AppleScript／PowerShell 語法壞掉
    quoted_macos = command_for("darwin", 'say "hi"', "b")
    assert '\\"hi\\"' in " ".join(quoted_macos)
    quoted_windows = command_for("win32", "it's", "b")
    assert "it''s" in " ".join(quoted_windows)


def test_desktop_notifier_warns_and_skips_when_the_command_is_missing():
    recorder = Recorder()
    notifier = DesktopNotifier(
        platform="linux",
        runner=recorder.run,
        warn=recorder.warn,
        which=lambda name: None,
        env={"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"},
    )

    notifier.notify(event_payload())

    assert recorder.commands == []
    assert len(recorder.warnings) == 1
    assert "notify-send" in recorder.warnings[0]


def test_desktop_notifier_never_raises_on_failure():
    """runner 非 0 或丟出 OSError 都只記 warning（不得中斷監控迴圈）。"""
    nonzero = Recorder(returncode=1)
    DesktopNotifier(
        platform="linux",
        runner=nonzero.run,
        warn=nonzero.warn,
        env={"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"},
    ).notify(event_payload())
    assert len(nonzero.commands) == 1
    assert len(nonzero.warnings) == 1

    broken = Recorder(raises=OSError("no bus"))
    DesktopNotifier(
        platform="linux",
        runner=broken.run,
        warn=broken.warn,
        env={"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"},
    ).notify(event_payload())
    assert len(broken.warnings) == 1
    assert "no bus" in broken.warnings[0]


def test_desktop_notifier_skips_without_a_session_bus():
    recorder = Recorder()
    notifier = DesktopNotifier(
        platform="linux",
        runner=recorder.run,
        warn=recorder.warn,
        env={},
    )

    notifier.notify(event_payload())

    assert recorder.commands == []
    assert len(recorder.warnings) == 1
    assert "DBUS_SESSION_BUS_ADDRESS" in recorder.warnings[0]


def test_notification_text_carries_the_fields_a_user_needs():
    title, body = notification_text(event_payload())

    assert "2330" in title and "1d" in title
    assert "2024-01-02T00:00:00+00:00" in body
    assert "0.8125" in body or "0.81" in body
    assert "50" in body and "4" in body

    # 沒有樣本時不得顯示 0%（會與「機率真的是 0」混淆）
    _title, no_samples = notification_text(
        event_payload(history_up_probability=None, history_samples=0)
    )
    assert "無樣本" in no_samples
    assert "0%" not in no_samples

    # 樣本數 0 卻帶著機率（上游不一致）時仍不得顯示百分比
    _title, inconsistent = notification_text(
        event_payload(history_up_probability=0.5, history_samples=0)
    )
    assert "無樣本" in inconsistent
    assert "%" not in inconsistent


# ---- AC-051：網頁內提示與瀏覽器原生通知 -------------------------------------


def test_web_notifier_publishes_the_alert_payload():
    hub = FakeHub()
    WebNotifier(hub).notify(event_payload())

    assert len(hub.calls) == 1
    payload, event = hub.calls[0]
    assert event == "alert"
    assert payload["symbol"] == "2330"


def test_browser_notifier_publishes_a_distinct_notification_payload():
    hub = FakeHub()
    payload = event_payload()
    BrowserNotifier(hub).notify(payload)

    assert len(hub.calls) == 1
    sent, event = hub.calls[0]
    assert event == "notification"
    assert set(sent) == {"title", "body", "tag"}
    assert sent["tag"] == event_id_for(payload)
    # 與網頁管道的事件 id 必須不同，否則 hub 會把第二個當成重複而抑制
    assert event_id_for(sent) != event_id_for(payload)
    assert sent == notification_for(payload)


def test_all_three_channels_fire_for_one_event():
    hub = SSEHub()
    subscriber = hub.subscribe()
    recorder = Recorder()
    notifiers = build_notifiers(
        hub,
        platform="linux",
        which=lambda name: "/usr/bin/notify-send" if name == "notify-send" else None,
        runner=recorder.run,
        env={"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"},
    )

    assert [type(notifier).__name__ for notifier in notifiers] == [
        "WebNotifier",
        "BrowserNotifier",
        "DesktopNotifier",
    ]
    for notifier in notifiers:
        notifier.notify(event_payload())

    frames = [subscriber.get_nowait(), subscriber.get_nowait()]
    assert [frame.split(b"\n")[1] for frame in frames] == [
        b"event: alert",
        b"event: notification",
    ]
    assert len(recorder.commands) == 1


def test_web_channel_is_silent_without_subscribers_but_desktop_still_fires():
    hub = SSEHub()
    recorder = Recorder()
    notifiers = build_notifiers(
        hub,
        platform="linux",
        which=lambda name: "/usr/bin/notify-send",
        runner=recorder.run,
        env={"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"},
    )

    for notifier in notifiers:
        notifier.notify(event_payload())

    assert hub.client_count == 0
    assert len(hub.seen_ids()) == 2, "兩個事件型別都仍會被記錄（去重靠它）"
    assert len(recorder.commands) == 1, "沒有頁面連線時桌面通知仍必須觸發"


def test_the_same_event_is_never_published_twice():
    """傳輸層的第二道防線：同一個事件（含瀏覽器通知）不會重複推播。"""
    hub = SSEHub()
    hub.subscribe()
    notifier = WebNotifier(hub)
    browser = BrowserNotifier(hub)

    notifier.notify(event_payload())
    notifier.notify(event_payload())
    browser.notify(event_payload())
    browser.notify(event_payload())

    assert len(hub.seen_ids()) == 2


def test_build_notifiers_selects_the_available_channels():
    present = lambda name: f"/usr/bin/{name}"
    missing = lambda name: None

    assert len(build_notifiers(FakeHub(), platform="linux", which=present)) == 3
    assert len(build_notifiers(FakeHub(), platform="linux", which=missing)) == 2
    assert len(build_notifiers(FakeHub(), platform="freebsd", which=present)) == 2
    assert len(build_notifiers(FakeHub(), platform="darwin", which=present)) == 3
    assert len(build_notifiers(FakeHub(), platform="win32", which=present)) == 3

    # 桌面通知被跳過時，網頁與瀏覽器兩個管道仍然存在
    names = [type(n).__name__ for n in build_notifiers(FakeHub(), platform="linux", which=missing)]
    assert names == ["WebNotifier", "BrowserNotifier"]


def test_notifications_happen_once_per_new_event_across_three_rounds(tmp_path):
    """沿用 AC-023 的三輪夾具：同一事件、同一事件、新事件 → 通知 1、0、1。"""
    import pandas as pd

    from ediaad.app import Application
    from ediaad.monitor import AlertState, run_once
    from ediaad.patterns import NAMED_PATTERNS, PatternSpec

    spec = PatternSpec(**dict(NAMED_PATTERNS["range_fakeout_reversion"]))

    def build_series(offset: int) -> pd.DataFrame:
        total = offset + 40
        closes = [100.0 + (index % 7) * 0.3 for index in range(total)]
        highs = [value + 1.0 for value in closes]
        lows = [value - 1.0 for value in closes]
        lows[offset - 1] = 90.0
        for step in range(20):
            base = 100.0 if step % 2 == 0 else 100.4
            closes[offset + step] = base
            highs[offset + step] = base + 1.0
            lows[offset + step] = base - 1.0
        closes[offset + 20] = 98.5
        highs[offset + 20] = 99.5
        lows[offset + 20] = 97.0
        closes[offset + 21] = 100.5
        highs[offset + 21] = 101.0
        lows[offset + 21] = 99.5
        times = pd.date_range("2024-01-01T00:00:00Z", periods=total, freq="1D", tz="UTC")
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

    from ediaad.markets.base import Instrument
    from ediaad.monitor import Watchlist

    watchlist = Watchlist(
        poll_interval_seconds=60,
        events_path=str(tmp_path / "events.jsonl"),
        cache_dir=str(tmp_path / "cache"),
        pattern_id="range_fakeout_reversion",
        pattern_spec=spec,
        horizon=5,
        instruments=(
            Instrument(symbol="2330", interval="1d", source_id="csv", display_name="2330"),
        ),
    )

    app = Application.create(home=tmp_path / "home")
    recorder = Recorder()
    app.enable_notifications(
        platform="linux",
        which=lambda name: "/usr/bin/notify-send",
        runner=recorder.run,
        env={"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"},
    )
    emit = app.make_emit()
    state = AlertState()
    holder = {"series": build_series(10)}

    def fetch(symbol: str, interval: str) -> pd.DataFrame:
        return holder["series"]

    try:
        results = []
        for series in (build_series(10), build_series(10), build_series(40)):
            holder["series"] = series
            results.append(
                run_once(watchlist, fetch, emit, recorder.warn, state=state)
            )
    finally:
        app.close()

    assert [result.alerted for result in results] == [1, 0, 1]
    assert len(recorder.commands) == 2, "只有兩次新事件該觸發桌面通知"
    assert len(app.hub.seen_ids()) == 4, "兩個事件 × 兩個事件型別"


# ---- 通知必須由服務明確啟用（避免測試或工具誤觸桌面通知） -------------------


def test_application_enables_notifications_explicitly(tmp_path):
    from ediaad.app import Application

    app = Application.create(home=tmp_path / "home")
    recorder = Recorder()
    try:
        assert app.notifiers == ()
        app.enable_notifications(
            platform="linux",
            which=lambda name: "/usr/bin/notify-send",
            runner=recorder.run,
            env={"DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus"},
        )
        assert len(app.notifiers) == 3

        subscriber = app.hub.subscribe()
        app.make_emit()("", event_payload())

        assert len(recorder.commands) == 1
        assert subscriber.get_nowait().startswith(b"id:")
    finally:
        app.close()


def test_make_emit_without_notifications_keeps_the_web_channel(tmp_path):
    """未啟用通知時，`make_emit` 的行為與 TASK-021 完全相同（只推播網頁管道）。"""
    from ediaad.app import Application

    app = Application.create(home=tmp_path / "home")
    try:
        subscriber = app.hub.subscribe()
        app.make_emit()("", event_payload())

        frame = subscriber.get_nowait()
        assert b"event: alert" in frame
        assert len(app.hub.seen_ids()) == 1
    finally:
        app.close()


def test_serve_enables_the_notification_channels(monkeypatch, tmp_path, capsys):
    """`--serve` 必須啟用通知，否則服務跑起來也只有網頁管道。"""
    from ediaad import launcher

    class FakeApp:
        running = False
        #: `_run_service` 現在也會讀 `problems`（設定檔損毀的警告）與 `settings`
        #: （租約 features 的更新分級），因此替身必須鏡射真正的 `Application` 介面。
        problems: dict = {}
        settings: dict = {"update_enabled": True}

        def __init__(self) -> None:
            self.calls: list[str] = []
            self.shutdown_event = threading.Event()

        def write_pid_file(self):
            self.calls.append("pid")

        def install_signal_handlers(self):
            self.calls.append("signals")

        def enable_notifications(self, **_kwargs):
            self.calls.append("notify")

        def start(self, **_kwargs):
            self.calls.append("start")

        def shutdown(self):
            self.calls.append("shutdown")

        def remove_pid_file(self):
            self.calls.append("remove")

        def close(self):
            self.calls.append("close")

    fake = FakeApp()
    fake.shutdown_event.set()  # 立刻要求關閉，讓服務迴圈馬上結束
    monkeypatch.setattr(
        launcher.Application, "create", classmethod(lambda cls, home=None: fake)
    )

    exit_code = launcher.serve_main(["--serve", "--home", str(tmp_path), "--port", "0"])

    assert exit_code == 0
    assert fake.calls == ["pid", "signals", "notify", "start", "shutdown"]
    capsys.readouterr()


# ---- AC-051：前端（以 Node 載入 notify.js 驗證） -----------------------------

NODE = shutil.which("node")

NOTIFY_HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const context = {console: console};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync("notify.js", "utf8"), context);

const ui = context.ediaadNotify;
if (!ui) {
  throw new Error("notify.js 必須在 window.ediaadNotify 上匯出功能");
}

function fakeWindow(permission) {
  const shown = [];
  function Notification(title, options) {
    shown.push({title: title, options: options});
  }
  Notification.permission = permission;
  Notification.requestPermission = function (callback) {
    Notification.permission = "granted";
    if (callback) { callback("granted"); }
    return Promise.resolve("granted");
  };
  return {Notification: Notification, shown: shown};
}

const payload = {title: "ediaad：2330 1d", body: "命中，信心 0.8125", tag: "2330|1d|x"};

const granted = fakeWindow("granted");
const denied = fakeWindow("denied");
const unsupported = {};
const noRequest = {Notification: function () {}};

const report = {
  supported: [ui.supported(granted), ui.supported(unsupported)],
  permission: [ui.permission(granted), ui.permission(denied), ui.permission(unsupported)],
  described: ui.describe(payload),
  shownGranted: ui.show(granted, payload),
  shownDenied: ui.show(denied, payload),
  shownUnsupported: ui.show(unsupported, payload),
  shownCounts: [granted.shown.length, denied.shown.length],
  shownFirst: granted.shown[0] || null,
  requestUnsupported: ui.requestPermission(unsupported),
  requestNoApi: ui.requestPermission(noRequest),
  requestGranted: ui.requestPermission(denied)
};
process.stdout.write(JSON.stringify(report));
"""


def notify_report() -> dict:
    static = PROJECT_DIR / "ediaad" / "web" / "static"
    completed = subprocess.run(
        [NODE, "-e", NOTIFY_HARNESS],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(static),
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def browser_notify():
    if NODE is None:
        pytest.skip("需要 node 才能驗證 notify.js 的純函式（僅測試期依賴）")
    return notify_report()


def test_notify_js_is_served(tmp_path):
    from ediaad.app import Application

    app = Application.create(home=tmp_path / "home")
    app.start(port=0)
    host, port = app._server.socket.getsockname()[:2]
    import http.client

    try:
        connection = http.client.HTTPConnection(host, port, timeout=10)
        try:
            connection.request("GET", "/static/notify.js")
            response = connection.getresponse()
            assert response.status == 200
            assert response.headers["Content-Type"].startswith("text/javascript")
            text = response.read().decode("utf-8")
        finally:
            connection.close()
    finally:
        app.stop()
        app.close()

    assert "ediaadNotify" in text
    assert "/api/events/stream" in text
    assert '"notification"' in text or "'notification'" in text


def test_index_html_loads_notify_js(tmp_path):
    from ediaad.app import Application

    app = Application.create(home=tmp_path / "home")
    app.start(port=0)
    host, port = app._server.socket.getsockname()[:2]
    import http.client

    try:
        connection = http.client.HTTPConnection(host, port, timeout=10)
        try:
            connection.request("GET", "/")
            page = connection.getresponse().read().decode("utf-8")
        finally:
            connection.close()
    finally:
        app.stop()
        app.close()

    assert "/static/notify.js" in page


def test_browser_notification_helpers(browser_notify):
    report = browser_notify

    assert report["supported"] == [True, False]
    assert report["permission"] == ["granted", "denied", "unsupported"]
    assert report["described"] == {"title": "ediaad：2330 1d", "body": "命中，信心 0.8125"}
    assert report["shownGranted"] is True
    assert report["shownDenied"] is False, "沒有權限時不得嘗試顯示"
    assert report["shownUnsupported"] is False
    assert report["shownCounts"] == [1, 0]
    assert report["shownFirst"]["title"] == "ediaad：2330 1d"
    assert report["shownFirst"]["options"]["tag"] == "2330|1d|x"
    assert report["shownFirst"]["options"]["body"] == "命中，信心 0.8125"
    assert report["requestGranted"] == "granted"
    assert report["requestUnsupported"] is False
    assert report["requestNoApi"] is False
