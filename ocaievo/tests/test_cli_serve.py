"""`python -m ediaad serve` 的端到端子程序測試（TASK-036／AC-064）。

驗的是 CLI 邊界：子命令存在、啟動與優雅結束、以及**啟動時的離線授權驗證**（TASK-030
的 `check_lease`）——沒有租約時仍要能啟動（使用者才進得了啟用頁），但租約存在且無效
（過期／撤銷／別台機器／簽章失敗／時鐘異常且無法線上驗證）時必須**拒絕啟動**。
"""

from __future__ import annotations

import json
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from datetime import timedelta

import pytest

from _cli_helpers import (
    NOW,
    PROJECT_DIR,
    build_lease,
    cli_env,
    free_port,
    run_cli,
    wait_ready,
    write_lease,
)

from ediaad.license import machine_fingerprint

FINGERPRINT = machine_fingerprint()


@pytest.fixture
def home(tmp_path):
    path = tmp_path / "home"
    path.mkdir(parents=True, exist_ok=True)
    return path


def start_serve(home, port, env=None, extra=()):
    process = subprocess.Popen(
        [f"{PROJECT_DIR}/.venv/bin/python", "-m", "ediaad", "serve", "--port", str(port), "--home", str(home), *extra],
        cwd=str(PROJECT_DIR),
        env=env or cli_env(home),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return process


def stop_serve(process, sig=signal.SIGINT, timeout=15.0):
    if process.poll() is None:
        process.send_signal(sig)
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        out, err = process.communicate(timeout=10)
        pytest.fail(f"serve 沒有在 {timeout} 秒內結束；stdout={out!r} stderr={err!r}")
    return process.returncode, out, err


def http_get(port, path="/api/health"):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
        return response.status, response.read().decode("utf-8")


def test_serve_is_registered_with_port_and_home():
    from ediaad.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["serve", "--port", "1234", "--home", "/tmp/x"])
    assert args.command == "serve"
    assert args.port == 1234
    assert args.home == "/tmp/x"


def test_serve_help_exits_zero(home):
    for argv in (["--help"], ["serve", "--help"], ["license", "--help"], ["license", "activate", "--help"]):
        result = run_cli(*argv, env=cli_env(home))
        assert result.returncode == 0, (argv, result.stderr)
        assert "usage" in result.stdout.lower()


def test_serve_starts_serves_and_stops_gracefully(home):
    port = free_port()
    process = start_serve(home, port)

    try:
        assert wait_ready(port), "serve 必須在 10 秒內就緒"
        status, body = http_get(port)
        assert status == 200
        assert json.loads(body)["status"] == "ok"
        assert (home / "ediaad.pid").is_file(), "服務應寫下 PID 檔（TASK-026）"
    finally:
        code, out, err = stop_serve(process)

    assert code == 0, (out, err)
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0, "結束後埠必須釋放"
    assert not (home / "ediaad.pid").exists()


def test_serve_reports_a_busy_port(home):
    port = free_port()
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", port))
        blocker.listen(1)
        result = run_cli("serve", "--port", str(port), "--home", str(home), env=cli_env(home), timeout=30)

    assert result.returncode == 1
    assert "錯誤" in result.stderr
    assert "Traceback" not in result.stderr


def test_serve_starts_without_a_lease_so_the_activation_page_is_reachable(home):
    """未啟用是合法狀態：服務要啟動，使用者才進得了網頁的「授權」區塊（AC-066）。"""
    port = free_port()
    process = start_serve(home, port)
    try:
        assert wait_ready(port)
        status, body = http_get(port, "/api/license")
        assert status == 200
        assert json.loads(body)["state"] == "inactive"
    finally:
        code, out, err = stop_serve(process)

    assert code == 0, (out, err)
    assert "尚未啟用" in err or "尚未啟用" in out


def test_serve_defaults_the_port_from_the_environment(monkeypatch):
    from ediaad.cli import build_parser

    monkeypatch.setenv("EDIAAD_PORT", "9911")
    assert build_parser().parse_args(["serve"]).port == 9911


def test_serve_rejects_a_bad_ediaad_port(home):
    port = free_port()
    env = cli_env(home, EDIAAD_PORT="not-a-number")

    result = run_cli("serve", "--port", str(port), "--home", str(home), env=env, timeout=30)

    assert result.returncode == 2
    assert "EDIAAD_PORT" in result.stderr


def test_serve_honours_the_explicit_home_over_the_environment(tmp_path):
    """`--home` 必須完整決定資料目錄（不受 `EDIAAD_HOME` 影響）。"""
    other = tmp_path / "other-home"
    home = tmp_path / "cli-home"
    home.mkdir(parents=True)
    write_lease(home, build_lease(FINGERPRINT, issued_at=NOW - timedelta(days=60), expires_at=NOW - timedelta(days=30)))
    env = cli_env(other)  # EDIAAD_HOME 指向**沒有**租約的目錄

    result = run_cli("serve", "--port", str(free_port()), "--home", str(home), env=env, timeout=30)

    assert result.returncode == 2, result.stderr
    assert "過期" in result.stderr


def test_serve_reads_the_clock_water_from_the_explicit_home(tmp_path):
    """時鐘水位也要跟著 `--home`：那裡的未來水位必須觸發強制線上驗證。"""
    other = tmp_path / "other-home"
    home = tmp_path / "cli-home"
    home.mkdir(parents=True)
    write_lease(home, build_lease(FINGERPRINT))
    (home / "high_water.json").write_text(
        json.dumps({"high_water": 4102444800.0}), encoding="utf-8"  # 2100 年
    )
    env = cli_env(other, EDIAAD_LICENSE_URL=f"http://127.0.0.1:{free_port()}")

    result = run_cli("serve", "--port", str(free_port()), "--home", str(home), env=env, timeout=60)

    assert result.returncode == 1, result.stderr
    assert "時間異常" in result.stderr


def test_serve_refuses_an_expired_lease(home):
    port = free_port()
    expired = build_lease(FINGERPRINT, issued_at=NOW - timedelta(days=60), expires_at=NOW - timedelta(days=30))
    write_lease(home, expired)

    result = run_cli("serve", "--port", str(port), "--home", str(home), env=cli_env(home), timeout=30)

    assert result.returncode == 2, result.stderr
    assert "過期" in result.stderr
    assert "重新申請" in result.stderr
    assert "Traceback" not in result.stderr
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0, "拒絕啟動時不得佔用埠"


def test_serve_refuses_a_lease_for_another_machine(home):
    port = free_port()
    write_lease(home, build_lease("ffffffffffffffff"))

    result = run_cli("serve", "--port", str(port), "--home", str(home), env=cli_env(home), timeout=30)

    assert result.returncode == 2
    assert "指紋" in result.stderr or "不屬於這台機器" in result.stderr


def test_serve_refuses_a_revoked_lease(home):
    port = free_port()
    lease = build_lease(FINGERPRINT)
    write_lease(home, lease)
    (home / "revoked.json").write_text(
        json.dumps({"key_id": lease.key_id, "revoked_at": 1.0}), encoding="utf-8"
    )

    result = run_cli("serve", "--port", str(port), "--home", str(home), env=cli_env(home), timeout=30)

    assert result.returncode == 2
    assert "撤銷" in result.stderr


def test_serve_refuses_a_corrupt_lease_file(home):
    port = free_port()
    (home / "lease.json").write_text("{not json", encoding="utf-8")
    original = (home / "lease.json").read_text(encoding="utf-8")

    result = run_cli("serve", "--port", str(port), "--home", str(home), env=cli_env(home), timeout=30)

    assert result.returncode == 2
    assert "lease.json" in result.stderr
    assert "無法解讀" in result.stderr or "JSON" in result.stderr
    assert (home / "lease.json").read_text(encoding="utf-8") == original, "不得覆寫損毀的檔案"


def test_serve_requires_online_verification_when_the_clock_is_rolled_back(home):
    """簽章內的 `issued_at` 在未來（超過容忍值）→ 必須線上驗證；不可用就拒絕啟動。"""
    port = free_port()
    future = build_lease(
        FINGERPRINT, issued_at=NOW + timedelta(days=5), expires_at=NOW + timedelta(days=35)
    )
    write_lease(home, future)
    env = cli_env(home, EDIAAD_LICENSE_URL=f"http://127.0.0.1:{free_port()}")

    result = run_cli("serve", "--port", str(port), "--home", str(home), env=env, timeout=60)

    assert result.returncode == 1, result.stderr
    assert "時間異常" in result.stderr or "線上" in result.stderr
    assert "Traceback" not in result.stderr


def test_serve_warns_about_a_corrupt_settings_file_but_still_starts(home):
    """設定檔損毀時**仍然啟動**（網頁是唯一的修復介面，TASK-020 的凍結設計）。"""
    port = free_port()
    (home / "settings.json").write_text("{not json", encoding="utf-8")
    process = start_serve(home, port)
    try:
        assert wait_ready(port)
        status, body = http_get(port)
        payload = json.loads(body)
        assert status == 200
        assert "settings" in payload["problems"], "問題必須在網頁上看得見"
    finally:
        code, out, err = stop_serve(process)

    assert code == 0, (out, err)
    assert "settings.json" in err or "設定" in err


def test_serve_disables_update_when_the_lease_lacks_the_feature(home):
    """AC-057 的分級：租約只有 `start` 時，更新檢查必須停用（TASK-032 的 A-3 接線）。"""
    port = free_port()
    write_lease(home, build_lease(FINGERPRINT, features=("start",)))
    env = cli_env(home, EDIAAD_UPDATE_URL="https://update.example.invalid/v1/latest")
    process = start_serve(home, port, env=env)
    try:
        assert wait_ready(port)
        status, body = http_get(port, "/api/version")
        payload = json.loads(body)
        assert status == 200
        assert payload["update_enabled"] is False
        assert "已關閉" in payload["message"]
    finally:
        code, out, err = stop_serve(process)

    assert code == 0, (out, err)


def test_serve_keeps_update_enabled_when_the_lease_has_the_feature(home):
    port = free_port()
    write_lease(home, build_lease(FINGERPRINT, features=("start", "update")))
    env = cli_env(home, EDIAAD_UPDATE_URL="https://update.example.invalid/v1/latest")
    process = start_serve(home, port, env=env)
    try:
        assert wait_ready(port)
        status, body = http_get(port, "/api/version")
        assert status == 200
        assert json.loads(body)["update_enabled"] is True
    finally:
        code, out, err = stop_serve(process)

    assert code == 0, (out, err)
