"""Web 服務骨架與 API 對應核心函式（TASK-020）。

觀察邊界：對**真實啟動**的服務（`Application.start()` ＋ `create_server`，綁
`127.0.0.1` 的臨時埠）以標準庫 `http.client` 發請求，觀察狀態碼、`Content-Type`、
JSON 主體與 `server.socket.getsockname()`；完全離線。
"""

from __future__ import annotations

import http.client
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from ediaad.errors import ConfigError, DataFormatError, EdiaadError, SourceError

PROJECT_DIR = Path(__file__).resolve().parent.parent


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


def write_settings(home: Path, payload: dict) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    path = home / "settings.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def service(tmp_path):
    from ediaad.app import Application

    home = tmp_path / "home"
    app = Application.create(home=home)
    server = app.start(port=0)
    host, port = server.socket.getsockname()[:2]
    try:
        yield SimpleNamespace(app=app, server=server, host=host, port=port, home=home)
    finally:
        app.stop()
        app.close()


# ---- AC-041：綁定、靜態頁與健康端點 -----------------------------------------


def test_the_server_binds_only_to_localhost(service):
    host, port = service.server.socket.getsockname()[:2]

    assert host == "127.0.0.1", "只允許本機存取（報告第 6.3 節）"
    assert host != "0.0.0.0"
    assert port > 0
    assert service.host == "127.0.0.1"


def test_create_server_defaults_to_localhost(tmp_path):
    """直接呼叫 `create_server()`（不傳 host）也必須只綁本機。"""
    from ediaad.app import Application
    from ediaad.web.server import create_server

    app = Application.create(home=tmp_path / "home")
    server = create_server(port=0, app=app)
    try:
        host, port = server.socket.getsockname()[:2]
        assert host == "127.0.0.1"
        assert port > 0
    finally:
        server.server_close()
        app.close()


def test_health_returns_ok(service):
    response = call(service.host, service.port, "GET", "/api/health")

    assert response.status == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"], "健康端點必須回報版本"
    assert payload["problems"] == {}, "預設情況下沒有設定或資料庫問題"


def test_the_index_page_is_native_html(service):
    response = call(service.host, service.port, "GET", "/")

    assert response.status == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "ediaad" in response.text
    assert "<script" in response.text, "靜態頁必須載入前端骨架"


def test_the_static_assets_are_served_with_the_right_content_types(service):
    css = call(service.host, service.port, "GET", "/static/style.css")
    script = call(service.host, service.port, "GET", "/static/app.js")

    assert css.status == 200
    assert css.headers["content-type"].startswith("text/css")
    assert script.status == 200
    assert script.headers["content-type"].startswith("text/javascript")


def test_an_unknown_static_file_is_a_404(service):
    response = call(service.host, service.port, "GET", "/static/nope.css")

    assert response.status == 404


def test_the_page_does_not_rely_on_colour_alone(service):
    """SPEC 第 6 節可及性：狀態必須有文字，不能只用顏色表達。"""
    page = call(service.host, service.port, "GET", "/").text
    script = call(service.host, service.port, "GET", "/static/app.js").text

    assert "aria-live" in page, "狀態區必須是可讀取的即時區域"
    assert "正常" in script or "服務正常" in script, "狀態必須以文字呈現"


def test_static_path_traversal_is_blocked(service):
    """靜態目錄之外的真實檔案不得被任何形式的 `..` 取走。"""
    # 靜態目錄是 <repo>/ocaievo/ediaad/web/static；往上三層就是 pytest.ini 所在處。
    outside = PROJECT_DIR / "pytest.ini"
    assert outside.is_file(), "測試需要一個靜態目錄之外的真實檔案當目標"

    for path in (
        "/static/../../../pytest.ini",
        "/static/..%2f..%2f..%2fpytest.ini",
        "/static/%2e%2e%2f%2e%2e%2f%2e%2e%2fpytest.ini",
        "/static/..%5c..%5c..%5cpytest.ini",
        "/static/..%2f..%2f..%2f..%2f..%2fAGENTS.md",
    ):
        response = call(service.host, service.port, "GET", path)
        assert response.status == 404, f"{path} 應回 404，實際 {response.status}"
        assert b"testpaths" not in response.body, f"{path} 不得外洩檔案內容"
        assert b"project-workflow" not in response.body, f"{path} 不得外洩檔案內容"


# ---- AC-041：端點對應核心函式、錯誤轉譯與生命週期 ---------------------------


def test_patterns_endpoint_serialises_the_existing_constants(service):
    from ediaad.markets.calendar import MARKET_PATTERN_DEFAULTS
    from ediaad.patterns import NAMED_PATTERNS

    response = call(service.host, service.port, "GET", "/api/patterns")

    assert response.status == 200
    payload = response.json()
    assert payload["patterns"] == NAMED_PATTERNS, "必須直接序列化既有常數，不重算"
    assert payload["markets"] == {
        market: dict(params) for market, params in MARKET_PATTERN_DEFAULTS.items()
    }


def test_settings_endpoint_reads_the_file_through_load_settings(service):
    from ediaad.config import load_settings

    write_settings(service.home, {"horizon": 13, "market": "stock"})

    response = call(service.host, service.port, "GET", "/api/settings")

    assert response.status == 200
    assert response.json() == load_settings(service.home / "settings.json")
    assert response.json()["horizon"] == 13
    assert response.json()["market"] == "stock"


def test_a_corrupt_settings_file_returns_400_with_a_readable_message(service):
    (service.home / "settings.json").write_text("{not json", encoding="utf-8")

    response = call(service.host, service.port, "GET", "/api/settings")

    assert response.status == 400
    payload = response.json()
    assert payload["error"]["code"] == "invalid_request"
    assert "settings.json" in payload["error"]["message"]
    assert "Traceback" not in response.text


def test_an_unknown_api_path_returns_404_json(service):
    response = call(service.host, service.port, "GET", "/api/nope")

    assert response.status == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "Traceback" not in response.text


def test_a_wrong_method_returns_405(service):
    response = call(service.host, service.port, "POST", "/api/health", body={})

    assert response.status == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_a_malformed_body_is_reported_as_a_readable_400(service):
    connection = http.client.HTTPConnection(service.host, service.port, timeout=10)
    try:
        connection.request("POST", "/api/health", body=b"{not json")
        response = connection.getresponse()
        body = response.read().decode("utf-8")
    finally:
        connection.close()

    assert response.status in (400, 405), "本張沒有會讀主體的端點；只要不是 500 或崩潰"
    assert "Traceback" not in body


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        pytest.param(ConfigError("壞設定"), 400, "invalid_request", id="ConfigError→400"),
        pytest.param(DataFormatError("壞資料"), 400, "invalid_request", id="DataFormatError→400"),
        pytest.param(SourceError("來源失敗"), 502, "source_failed", id="SourceError→502"),
        pytest.param(EdiaadError("其他領域錯誤"), 400, "invalid_request", id="EdiaadError→400"),
        pytest.param(RuntimeError("boom"), 500, "internal_error", id="未預期例外→500"),
    ],
)
def test_the_error_mapping_is_explicit(error, status, code):
    from ediaad.web.routes import error_response

    actual_status, payload = error_response(error)

    assert actual_status == status
    assert payload["error"]["code"] == code
    assert payload["error"]["message"]
    if status == 500:
        assert "boom" not in payload["error"]["message"], "不得外洩例外內容"


def test_an_injected_domain_error_becomes_a_400(service, monkeypatch):
    from ediaad.web import routes

    def boom(_path):
        raise ConfigError("設定檔 /tmp/x.json：不是合法 JSON")

    monkeypatch.setattr(routes, "load_settings", boom)

    response = call(service.host, service.port, "GET", "/api/settings")

    assert response.status == 400
    assert "不是合法 JSON" in response.json()["error"]["message"]
    assert "Traceback" not in response.text


def test_an_injected_unexpected_error_becomes_a_500_without_a_stack(service, monkeypatch, caplog):
    import logging

    from ediaad.web import routes

    def boom(_path):
        raise RuntimeError("內部細節不該外洩")

    monkeypatch.setattr(routes, "load_settings", boom)

    with caplog.at_level(logging.ERROR, logger="ediaad.web"):
        response = call(service.host, service.port, "GET", "/api/settings")

    assert response.status == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "內部細節不該外洩" not in response.text, "回應不得外洩例外內容"
    assert "Traceback" not in response.text
    assert "內部細節不該外洩" in caplog.text, "伺服器日誌必須留下可除錯的紀錄"


def test_the_registry_lists_the_routes_and_rejects_duplicates():
    from ediaad.web import routes

    assert ("GET", "/api/health") in routes.routes()
    assert ("GET", "/api/patterns") in routes.routes()
    assert ("GET", "/api/settings") in routes.routes()

    with pytest.raises(ConfigError, match="重複註冊"):
        routes.route("GET", "/api/health", routes.health)


def test_stop_closes_the_listener_and_is_idempotent(tmp_path):
    from ediaad.app import Application

    app = Application.create(home=tmp_path / "home")
    server = app.start(port=0)
    host, port = server.socket.getsockname()[:2]
    assert call(host, port, "GET", "/api/health").status == 200

    app.stop()
    app.stop()

    assert app.running is False
    with pytest.raises(OSError):
        call(host, port, "GET", "/api/health")


def test_stop_is_safe_from_another_thread(tmp_path):
    import threading

    from ediaad.app import Application

    app = Application.create(home=tmp_path / "home")
    app.start(port=0)
    # 私有屬性在這裡是唯一能觀察「服務執行緒真的結束了」的方式（洩漏的執行緒會繼續
    # 接受連線並持有資料庫，公開介面看不到）。
    web_thread = app._thread
    errors: list[BaseException] = []

    def stopper() -> None:
        try:
            app.stop()
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    thread = threading.Thread(target=stopper, name="stopper")
    thread.start()
    thread.join(timeout=10)

    assert errors == []
    assert not thread.is_alive()
    assert app.running is False
    assert web_thread is not None and not web_thread.is_alive(), "停止後服務執行緒必須結束"


def test_the_service_can_be_restarted(tmp_path):
    from ediaad.app import Application

    app = Application.create(home=tmp_path / "home")
    first = app.start(port=0)
    first_port = first.socket.getsockname()[1]
    app.stop()

    second = app.start(port=0)
    host, port = second.socket.getsockname()[:2]
    try:
        assert call(host, port, "GET", "/api/health").status == 200
        assert port != first_port or True  # 埠可能被系統重用，兩種都合法
    finally:
        app.stop()
        app.close()


def test_close_is_idempotent_and_releases_the_database(tmp_path):
    from ediaad.app import Application

    app = Application.create(home=tmp_path / "home")
    assert app.store is not None

    app.close()
    app.close()

    with pytest.raises(ConfigError, match="已關閉"):
        app.store.seen_keys()


def test_a_corrupt_produce_does_not_prevent_startup(tmp_path):
    """損毀的產物只記錄問題，服務仍必須啟動並能回報問題。"""
    from ediaad.app import Application

    home = tmp_path / "home"
    write_settings(home, {})
    (home / "settings.json").write_text("{not json", encoding="utf-8")
    (home / "ediaad.db").write_bytes(b"not a database" * 20)

    app = Application.create(home=home)
    server = app.start(port=0)
    host, port = server.socket.getsockname()[:2]
    try:
        assert set(app.problems) == {"settings", "store"}

        health = call(host, port, "GET", "/api/health").json()
        assert health["status"] == "ok"
        assert health["problems"] == app.problems, "問題必須能在健康端點看到"

        assert call(host, port, "GET", "/api/settings").status == 400
    finally:
        app.stop()
        app.close()


def test_stop_returns_promptly_when_the_serve_loop_never_started(tmp_path):
    """`shutdown()` 會等 `serve_forever()` 結束；迴圈從未啟動時必須跳過它，否則永久阻塞。"""
    import time

    from ediaad.app import Application
    from ediaad.web.server import create_server

    app = Application.create(home=tmp_path / "home")
    app._server = create_server(port=0, app=app)  # 只建立，不啟動迴圈
    app._thread = None

    started = time.monotonic()
    app.stop()
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, f"stop() 不得阻塞（花了 {elapsed:.1f} 秒）"
    assert app.running is False
