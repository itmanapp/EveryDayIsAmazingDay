"""SSE 即時提醒與事件歷史（TASK-021）。

觀察邊界：對真實服務的 SSE 串流（標準庫 HTTP client 建立連線後逐行讀取）與
`GET /api/events` 的 JSON；`SSEHub` 本身以多訂閱者的單元測試觀察誰收到、誰沒收到。
完全離線。
"""

from __future__ import annotations

import http.client
import json
import queue
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

ALERT = {
    "symbol": "BTCUSDT",
    "interval": "1h",
    "pattern_id": "range_fakeout_reversion",
    "event_start_time": "2024-07-01T00:00:00+00:00",
    "event_end_time": "2024-07-05T00:00:00+00:00",
    "confidence": 0.8,
    "detected_at": "2024-07-06T00:00:00+00:00",
    "history_up_probability": 0.6,
    "history_samples": 4,
}


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


class Stream:
    """最小 SSE 讀取器：逐行讀取直到空行（一幀結束）或逾時。"""

    def __init__(self, host: str, port: int, *, last_event_id: str | None = None) -> None:
        self.connection = http.client.HTTPConnection(host, port, timeout=10)
        headers = {"Accept": "text/event-stream"}
        if last_event_id is not None:
            headers["Last-Event-ID"] = last_event_id
        self.connection.request("GET", "/api/events/stream", headers=headers)
        self.response = self.connection.getresponse()

    def frame(self, *, timeout: float = 3.0) -> dict[str, str]:
        """讀取一幀（含 keep-alive 註解）並回傳其欄位。"""
        self.connection.sock.settimeout(timeout)
        fields: dict[str, str] = {"data": "", "comment": ""}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.response.readline()
            if not line:
                break
            text = line.decode("utf-8").rstrip("\n")
            if text == "":
                return fields
            if text.startswith(":"):
                fields["comment"] = text
            elif ":" in text:
                name, _, value = text.partition(":")
                value = value[1:] if value.startswith(" ") else value
                if name == "data":
                    fields["data"] += value
                else:
                    fields[name] = value
        raise AssertionError(f"在 {timeout} 秒內沒有讀到完整的幀：{fields!r}")

    def wait_for(self, event_name: str, *, timeout: float = 3.0) -> dict[str, str]:
        """持續讀幀直到出現指定事件（略過 keep-alive 與其他事件）。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = self.frame(timeout=max(0.1, deadline - time.monotonic()))
            if frame.get("event") == event_name:
                return frame
        raise AssertionError(f"在 {timeout} 秒內沒有收到 {event_name} 事件")

    def close(self) -> None:
        self.connection.close()


def wait_until(predicate, *, timeout: float = 3.0, interval: float = 0.02) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError(f"條件在 {timeout} 秒內沒有成立")


@pytest.fixture
def service(tmp_path):
    from ediaad.app import Application

    app = Application.create(home=tmp_path / "home")
    server = app.start(port=0)
    host, port = server.socket.getsockname()[:2]
    try:
        yield SimpleNamespace(app=app, server=server, host=host, port=port, home=tmp_path / "home")
    finally:
        app.stop()
        app.close()


# ---- SSE 幀格式（純函式） ---------------------------------------------------


def test_format_sse_produces_a_valid_frame():
    from ediaad.web.sse_hub import format_sse

    frame = format_sse({"symbol": "BTCUSDT"}, event="alert", event_id="abc|1h")

    text = frame.decode("utf-8")
    assert text.startswith("id: abc|1h\n")
    assert "event: alert\n" in text
    assert 'data: {"symbol": "BTCUSDT"}\n' in text
    assert text.endswith("\n\n"), "SSE 幀必須以空行結束"


def test_a_payload_with_newlines_still_produces_one_valid_frame():
    """`json.dumps` 會把換行轉義，因此幀內永遠不會出現真實換行。

    這裡固定的是**可達的不變式**：含換行的內容仍然只有一個 `data:` 行、沒有裸 `\r`、
    而且能被還原成同一個 payload。（`format_sse` 內部的逐行拆分是防禦性程式碼：若日後
    改成縮排輸出才會用到，見 TDD 紀錄。）
    """
    from ediaad.web.sse_hub import format_sse

    original = {"note": "第一行\n第二行\r\n第三行"}
    frame = format_sse(original, event="alert")

    text = frame.decode("utf-8")
    lines = text.split("\n")
    data_lines = [line for line in lines if line.startswith("data: ")]
    assert len(data_lines) == 1, f"轉義後的 JSON 只有一行：{lines}"
    assert all("\r" not in line for line in lines), "不得留下裸 \r"
    assert text.endswith("\n\n")
    assert json.loads(data_lines[0][len("data: ") :]) == original


def test_format_sse_omits_the_id_line_when_there_is_no_id():
    from ediaad.web.sse_hub import format_sse

    frame = format_sse({"x": 1}, event="alert").decode("utf-8")

    assert not frame.startswith("id:")
    assert frame.startswith("event: alert\n")


def test_the_event_id_is_stable_and_distinguishes_events():
    from ediaad.web.sse_hub import event_id_for

    assert event_id_for(ALERT) == event_id_for(dict(ALERT))
    assert event_id_for(ALERT) != event_id_for({**ALERT, "symbol": "ETHUSDT"})
    assert event_id_for(ALERT) != event_id_for({**ALERT, "event_start_time": "2024-08-01T00:00:00+00:00"})

    # 兩個 dict 必須**同時存活**：CPython 會重用剛被回收的臨時物件位址，若只寫成兩次
    # 字面值呼叫，「以物件身分當 id」的實作會僥倖通過（變異 M3 就是這樣存活的）。
    first_without_key = {"note": "沒有去重鍵"}
    second_without_key = {"note": "沒有去重鍵"}
    assert first_without_key is not second_without_key
    assert event_id_for(first_without_key) == event_id_for(second_without_key), "缺少去重鍵時仍需穩定"
    assert event_id_for(first_without_key) == event_id_for(first_without_key)


# ---- SSEHub -----------------------------------------------------------------


def test_the_hub_broadcasts_to_every_subscriber():
    from ediaad.web.sse_hub import SSEHub

    hub = SSEHub()
    first, second = hub.subscribe(), hub.subscribe()

    event_id = hub.publish(ALERT)

    assert event_id
    for subscriber in (first, second):
        frame = subscriber.get(timeout=1)
        assert b"event: alert" in frame
        assert json.loads(frame.decode("utf-8").split("data: ", 1)[1].split("\n", 1)[0]) == ALERT


def test_the_hub_stops_sending_after_unsubscribe():
    from ediaad.web.sse_hub import SSEHub

    hub = SSEHub()
    subscriber = hub.subscribe()
    hub.unsubscribe(subscriber)

    assert hub.client_count == 0
    assert hub.publish(ALERT) is not None
    with pytest.raises(queue.Empty):
        subscriber.get(timeout=0.2)


def test_the_hub_suppresses_a_repeated_event_id():
    from ediaad.web.sse_hub import SSEHub

    hub = SSEHub()
    subscriber = hub.subscribe()

    assert hub.publish(ALERT) is not None
    subscriber.get(timeout=1)

    assert hub.publish(dict(ALERT)) is None, "同一事件不得再廣播一次"
    with pytest.raises(queue.Empty):
        subscriber.get(timeout=0.2)


def test_the_hub_reports_the_client_count():
    from ediaad.web.sse_hub import SSEHub

    hub = SSEHub()
    assert hub.client_count == 0

    first, second = hub.subscribe(), hub.subscribe()
    assert hub.client_count == 2

    hub.unsubscribe(first)
    assert hub.client_count == 1
    hub.unsubscribe(second)
    hub.unsubscribe(second)  # 幂等
    assert hub.client_count == 0


def test_a_slow_subscriber_does_not_block_the_publisher():
    """監控執行緒呼叫 `publish`；慢速（或已死）的客戶端不得拖住它。"""
    from ediaad.web.sse_hub import SSEHub

    hub = SSEHub(queue_size=1)
    subscriber = hub.subscribe()

    started = time.monotonic()
    for index in range(5):
        hub.publish({**ALERT, "event_start_time": f"2024-07-0{index + 1}T00:00:00+00:00"})
    elapsed = time.monotonic() - started

    assert hub.publish({**ALERT, "event_start_time": "2024-07-09T00:00:00+00:00"}) is not None
    assert subscriber.qsize() <= 1, "佇列滿時丟棄新幀，不得阻塞發布端"
    assert elapsed < 0.5, f"發布端不得被慢速客戶端阻塞（花了 {elapsed:.1f} 秒）"


# ---- AC-042：串流端點 -------------------------------------------------------


def test_the_stream_endpoint_pushes_an_alert_frame(service):
    stream = Stream(service.host, service.port)
    try:
        assert stream.response.status == 200
        wait_until(lambda: service.app.hub.client_count == 1)
        started = time.monotonic()
        service.app.hub.publish(ALERT)
        frame = stream.wait_for("alert", timeout=3.0)
        elapsed = time.monotonic() - started
    finally:
        stream.close()

    assert frame.get("event") == "alert"
    assert frame.get("id"), "每一幀都必須帶穩定 id（供 Last-Event-ID 使用）"
    assert json.loads(frame["data"]) == ALERT
    assert elapsed < 1.0, f"推播必須在 1 秒內送達（實際 {elapsed:.3f} 秒）"


def test_the_stream_endpoint_sets_the_event_stream_headers(service):
    stream = Stream(service.host, service.port)
    try:
        headers = {key.lower(): value for key, value in stream.response.getheaders()}
    finally:
        stream.close()

    assert headers["content-type"] == "text/event-stream; charset=utf-8"
    assert "no-cache" in headers["cache-control"]


def test_the_stream_endpoint_keeps_the_connection_alive_without_events(service):
    """沒有事件時必須持續送出 `: keep-alive` 註解行，不能讓連線逾時中斷。"""
    stream = Stream(service.host, service.port)
    try:
        frame = stream.frame(timeout=3.0)
    finally:
        stream.close()

    assert frame.get("comment", "").startswith(": keep-alive")


# ---- AC-042：事件歷史 -------------------------------------------------------


def seed_events(app) -> None:
    app.store.record_event(
        {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "pattern_id": "range_fakeout_reversion",
            "event_start_time": "2024-07-01T00:00:00+00:00",
            "event_end_time": "2024-07-05T00:00:00+00:00",
            "confidence": 0.8,
            "detected_at": "2024-07-06T00:00:00+00:00",
            "history_up_probability": 0.6,
            "history_samples": 4,
        }
    )
    app.store.record_event({**ALERT, "symbol": "2330", "event_start_time": "2024-07-15T00:00:00+00:00"})


def test_history_returns_the_events_from_the_store(service):
    seed_events(service.app)

    response = call(service.host, service.port, "GET", "/api/events")

    assert response.status == 200
    payload = response.json()
    assert [item["symbol"] for item in payload["events"]] == ["BTCUSDT", "2330"]
    assert payload["events"][0] == {**ALERT, "symbol": "BTCUSDT"}


def test_history_filters_by_symbol_and_time_range(service):
    seed_events(service.app)

    by_symbol = call(service.host, service.port, "GET", "/api/events?symbol=2330").json()
    assert [item["symbol"] for item in by_symbol["events"]] == ["2330"]

    in_range = call(
        service.host,
        service.port,
        "GET",
        "/api/events?start=2024-07-10T00:00:00%2B00:00&end=2024-07-20T00:00:00%2B00:00",
    ).json()
    assert [item["symbol"] for item in in_range["events"]] == ["2330"]

    both = call(
        service.host, service.port, "GET", "/api/events?symbol=BTCUSDT&end=2024-07-02T00:00:00%2B00:00"
    ).json()
    assert [item["symbol"] for item in both["events"]] == ["BTCUSDT"]


def test_history_without_matches_returns_an_empty_list(service):
    seed_events(service.app)

    unknown = call(service.host, service.port, "GET", "/api/events?symbol=NOPE")
    empty_range = call(service.host, service.port, "GET", "/api/events?start=2030-01-01T00:00:00%2B00:00")

    assert unknown.status == 200 and unknown.json()["events"] == []
    assert empty_range.status == 200 and empty_range.json()["events"] == []


def test_history_rejects_a_reversed_range(service):
    response = call(
        service.host,
        service.port,
        "GET",
        "/api/events?start=2024-07-15T00:00:00%2B00:00&end=2024-07-01T00:00:00%2B00:00",
    )

    assert response.status == 400
    assert response.json()["error"]["code"] == "invalid_request"
    assert "不得早於" in response.json()["error"]["message"]


def test_history_rejects_a_bad_time(service):
    response = call(service.host, service.port, "GET", "/api/events?start=not-a-time")

    assert response.status == 400
    assert "Traceback" not in response.text


def test_history_reports_an_unavailable_store(service):
    service.app.store.close()
    service.app.store = None

    response = call(service.host, service.port, "GET", "/api/events")

    assert response.status == 503
    assert response.json()["error"]["code"] == "store_unavailable"


# ---- AC-042：斷線、重連與引擎接線 -------------------------------------------


def test_a_reconnecting_client_does_not_receive_the_same_id_again(service):
    first = Stream(service.host, service.port)
    try:
        wait_until(lambda: service.app.hub.client_count == 1)
        service.app.hub.publish(ALERT)
        frame = first.wait_for("alert", timeout=3.0)
        event_id = frame["id"]
    finally:
        first.close()
    wait_until(lambda: service.app.hub.client_count == 0)

    second = Stream(service.host, service.port, last_event_id=event_id)
    try:
        wait_until(lambda: service.app.hub.client_count == 1)
        assert service.app.hub.publish(dict(ALERT)) is None, "同一事件不得再次廣播"

        keep_alive = second.frame(timeout=2.0)
        assert keep_alive.get("event") != "alert", "重連後不得重播已去重的事件"

        service.app.hub.publish({**ALERT, "event_start_time": "2024-08-01T00:00:00+00:00"})
        latest = second.wait_for("alert", timeout=3.0)
        assert latest["id"] != event_id, "新事件必須帶新的 id"
    finally:
        second.close()


def test_a_disconnected_client_does_not_break_the_others(service, capsys):
    survivor = Stream(service.host, service.port)
    leaving = Stream(service.host, service.port)
    try:
        wait_until(lambda: service.app.hub.client_count == 2)
        leaving.close()

        service.app.hub.publish(ALERT)
        assert survivor.wait_for("alert", timeout=3.0)["event"] == "alert"
        wait_until(lambda: service.app.hub.client_count == 1, timeout=5.0)

        service.app.hub.publish({**ALERT, "event_start_time": "2024-08-02T00:00:00+00:00"})
        assert survivor.wait_for("alert", timeout=3.0)["event"] == "alert", "另一個訂閱者必須繼續收到"
    finally:
        survivor.close()

    captured = capsys.readouterr()
    assert "Traceback" not in captured.err, "客戶端斷線不得在伺服器留下未處理的例外"
    assert "BrokenPipeError" not in captured.err


def test_the_application_emit_publishes_to_the_hub(service):
    """`Application.make_emit()` 是「引擎 → 瀏覽器」的接縫（引擎本身不改行為）。"""
    stream = Stream(service.host, service.port)
    try:
        wait_until(lambda: service.app.hub.client_count == 1)
        emit = service.app.make_emit()
        emit("[ALERT] BTCUSDT 1h", ALERT)

        frame = stream.wait_for("alert", timeout=3.0)
        assert json.loads(frame["data"]) == ALERT
    finally:
        stream.close()


def test_the_frontend_subscribes_to_the_stream(service):
    script = call(service.host, service.port, "GET", "/static/events.js")
    page = call(service.host, service.port, "GET", "/").text

    assert script.status == 200
    assert "EventSource" in script.text
    assert "/api/events/stream" in script.text
    assert "Last-Event-ID" in script.text or "lastEventId" in script.text or "id" in script.text
    assert "events.js" in page, "首頁必須載入事件前端"
    assert 'for="' in page, "篩選表單必須有 label（SPEC 第 6 節可及性）"
