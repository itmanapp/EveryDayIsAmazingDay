"""`tests/test_cli_serve.py`／`tests/test_cli_license.py` 共用的夾具（TASK-036）。

只存在於測試：loopback 假授權服務、合成租約（以 TASK-030 的公開測試向量金鑰簽章）與
子程序執行器。**不連外網**——`EDIAAD_LICENSE_URL` 一律指向 `127.0.0.1` 上的假服務。
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from _ed25519_fixture import FIXTURE_PUBLIC_KEY, sign

from ediaad.license import Lease, save_lease, signing_payload

PROJECT_DIR = Path(__file__).resolve().parent.parent
PYTHON = str(PROJECT_DIR / ".venv" / "bin" / "python")
NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
THIRTY_DAYS = timedelta(days=30)

#: 測試用的簽章公鑰（十六進位）——`serve` 以 `EDIAAD_LICENSE_PUBLIC_KEY` 覆寫內嵌佔位值。
PUBLIC_KEY_HEX = FIXTURE_PUBLIC_KEY.hex()


def stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_lease(
    machine: str,
    *,
    key_id: str = "EDIAAD-2026-0001",
    issued_at: datetime = NOW,
    expires_at: datetime | None = None,
    features: tuple[str, ...] = ("start", "update"),
) -> Lease:
    """合成一份由測試夾具簽章的租約（公開的 RFC 8032 金鑰，不可能被誤用）。"""
    fields = {
        "key_id": key_id,
        "machine": machine,
        "issued_at": stamp(issued_at),
        "expires_at": stamp(expires_at if expires_at is not None else issued_at + THIRTY_DAYS),
        "features": list(features),
        "catalog_version": "2026-10-01",
        "sig": "00" * 64,
    }
    unsigned = Lease(**fields)
    return Lease(**{**fields, "sig": sign(signing_payload(unsigned))})


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class Recorded:
    path: str
    payload: dict


class _Handler(BaseHTTPRequestHandler):
    server_version = "ediaad-test-license"

    def do_POST(self):  # noqa: N802 - http.server 的介面
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"_raw": raw}
        self.server.recorded.append(Recorded(self.path, payload))
        status, body = self.server.responder(payload, self.path)
        data = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
        encoded = data.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):  # 安靜：測試輸出只留斷言結果
        return


class LicenseServer:
    """`127.0.0.1` 上的假授權服務；`responder(payload, path) -> (status, body)`。"""

    def __init__(self, responder):
        self.responder = responder
        self.recorded: list[Recorded] = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.responder = responder
        self.httpd.recorded = self.recorded
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> "LicenseServer":
        self.thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)

    @property
    def url(self) -> str:
        host, port = self.httpd.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def paths(self) -> list[str]:
        return [item.path for item in self.recorded]


def cli_env(home: Path, **extra) -> dict[str, str]:
    """子程序的環境：`EDIAAD_HOME` 指向 tmp_path、公鑰指向測試夾具。"""
    env = dict(os.environ)
    env["EDIAAD_HOME"] = str(home)
    env["EDIAAD_LICENSE_PUBLIC_KEY"] = PUBLIC_KEY_HEX
    env.pop("EDIAAD_LICENSE_URL", None)
    env.pop("EDIAAD_UPDATE_URL", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update({key: str(value) for key, value in extra.items()})
    return env


def run_cli(*args: str, env: dict[str, str], timeout: float = 60.0, stdin=None):
    """以子程序執行 `python -m ediaad <args>`；回傳 CompletedProcess。"""
    return subprocess.run(
        [PYTHON, "-m", "ediaad", *args],
        cwd=str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        input=stdin,
    )


def write_lease(home: Path, lease: Lease) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    return save_lease(home / "lease.json", lease)


def wait_ready(port: int, timeout: float = 10.0, host: str = "127.0.0.1") -> bool:
    """以 TCP 連線探測就緒（與 TASK-026 的就緒探測同一種做法）。"""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.05)
    return False
