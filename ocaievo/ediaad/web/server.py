"""以標準庫實作的 HTTP 服務（報告第 6.3 節：`ThreadingHTTPServer`、零新增依賴）。

只 bind `127.0.0.1`（同一台機器上的單一使用者，因此不做認證／HTTPS／CSRF，但也**不得**
對外開放）；靜態資源僅從 `ediaad/web/static/` 提供，且必須防止路徑穿越。
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ..errors import ConfigError, EdiaadError
from . import routes

__all__ = ["create_server", "static_dir"]

logger = logging.getLogger("ediaad.web")

STATIC_DIR = Path(__file__).with_name("static")

_CONTENT_TYPES: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
}

MAX_BODY_BYTES = 1_000_000


def static_dir() -> Path:
    """靜態資源根目錄（測試與 TASK-026 的啟動器會用它）。"""
    return STATIC_DIR


def _resolve_static(path: str) -> Path | None:
    """把 URL 路徑解析成靜態目錄內的檔案；任何逃出目錄的路徑都回 `None`。"""
    relative = urllib.parse.unquote(path).lstrip("/") or "index.html"
    if relative.startswith("static/"):
        relative = relative[len("static/") :]

    root = STATIC_DIR.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


class _Handler(BaseHTTPRequestHandler):
    server_version = "ediaad"
    protocol_version = "HTTP/1.1"

    # ---- 進入點 ----

    def do_GET(self) -> None:  # noqa: N802 - 標準庫的命名
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    # ---- 實作 ----

    def _dispatch(self, method: str) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            query = urllib.parse.parse_qs(parsed.query)
            stream = routes.stream_for(path)
            if stream is not None:
                self._send_stream(stream, query)
                return
            try:
                body = self._read_body()
            except EdiaadError as error:
                # 主體解析失敗也要走同一套可讀的錯誤格式（不能讓連線直接斷掉）。
                status, payload = routes.error_response(error)
                self._send_json(status, payload)
                return
            status, payload = routes.dispatch(self.server.app, method, path, query, body)
            self._send_json(status, payload)
            return
        self._send_static(path)

    def _read_body(self) -> Any:
        length = self.headers.get("Content-Length")
        if not length:
            return None
        try:
            size = int(length)
        except ValueError:
            return None
        if size <= 0 or size > MAX_BODY_BYTES:
            return None
        raw = self.rfile.read(size)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ConfigError(f"請求主體不是合法 JSON：{error}") from error

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, path: str) -> None:
        resolved = _resolve_static(path)
        if resolved is None:
            self._send_json(
                404, {"error": {"code": "not_found", "message": f"找不到資源 {path}"}}
            )
            return

        body = resolved.read_bytes()
        content_type = _CONTENT_TYPES.get(resolved.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_stream(self, stream: Any, query: Any) -> None:
        """以 chunked 傳輸逐幀輸出（SSE 沒有 Content-Length）。

        客戶端斷線時寫入會丟出 `BrokenPipeError`／`ConnectionResetError`（或一般
        `OSError`）：只結束這一條串流，**不影響其他訂閱者與監控執行緒**。
        """
        headers = {key.lower(): value for key, value in self.headers.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        try:
            for frame in stream(self.server.app, query, headers):
                self.wfile.write(b"%X\r\n" % len(frame) + frame + b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError) as error:
            logger.debug("SSE 連線結束：%s", error)
        finally:
            self.close_connection = True

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - 標準庫簽名
        logger.debug("%s - %s", self.address_string(), format % args)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_server(host: str = "127.0.0.1", port: int = 8787, app: Any = None) -> _Server:
    """建立（尚未啟動迴圈的）HTTP 服務。

    `port=0` 讓作業系統挑一個空閒埠（測試用）。
    """
    if app is None:
        from ..app import Application

        app = Application.create()

    server = _Server((host, port), _Handler)
    server.app = app  # type: ignore[attr-defined]
    return server
