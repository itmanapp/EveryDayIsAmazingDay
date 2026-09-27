"""桌面一鍵啟動、重複啟動防護與優雅關閉（TASK-026／AC-049、AC-050）。

觀察邊界：
1. **真實程序（自動）**：以子程序啟動服務，觀察 PID 檔、埠探測、`/api/health`、
   `POST /api/shutdown`、`stop.sh` 與「再次啟動」。程序生命週期只能用真實程序驗證。
2. **單元（自動）**：`is_running`／`read_pid`／`is_alive`／`wait_ready`／`open_browser`
   的判定與注入點（`opener`／`spawn`／`which`），不真的開瀏覽器、不動使用者的服務。
3. **桌面圖示（人工）**：雙擊圖示的外觀與桌面整合屬 SPEC 第 7 節人工檢查。

所有測試使用 `tmp_path` 的 `EDIAAD_HOME` 與臨時埠，結束時一律把啟動的服務收乾淨。
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ediaad import launcher

PROJECT_DIR = Path(__file__).resolve().parent.parent
PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"
LAUNCHER_SCRIPT = PROJECT_DIR / "scripts" / "ediaad_launcher.py"
STOP_SCRIPT = PROJECT_DIR / "stop.sh"


# ---- 共用工具 ---------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def wait_until(predicate, timeout: float = 10.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def http_get(port: int, path: str, *, timeout: float = 5.0):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def http_post(port: int, path: str, body: object = None, *, timeout: float = 5.0):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"} if payload else {}
        connection.request("POST", path, body=payload, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


@pytest.fixture
def home(tmp_path):
    """測試專用的 `$EDIAAD_HOME`；結束時確保沒有殘留的服務程序。"""
    root = tmp_path / "home"
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        pid = launcher.read_pid(launcher.pid_path_for(root))
        # 有些測試刻意把自己的 PID 寫進 PID 檔（判定用）；**不可**因此對自己送訊號
        if pid is not None and pid != os.getpid() and launcher.is_alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            if not wait_until(lambda: not launcher.is_alive(pid), timeout=5.0):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass


def launcher_argv(home: Path, port: int, *extra: str) -> list[str]:
    return ["--home", str(home), "--port", str(port), "--timeout", "10", *extra]


def run_launcher(home: Path, port: int, *extra: str, opener=None, spawn=None) -> int:
    return launcher.main(
        launcher_argv(home, port, *extra),
        opener=opener,
        spawn=spawn,
    )


def script_env(home: Path, port: int) -> dict[str, str]:
    env = dict(os.environ)
    env["EDIAAD_HOME"] = str(home)
    env["EDIAAD_PORT"] = str(port)
    return env


# ---- AC-049：判定「是否已在執行」 -------------------------------------------


def test_is_running_is_false_without_a_pid_file_or_listener(home):
    """第一個失敗行為：模組不存在（collection error）；實作後必須回 False。"""
    assert launcher.is_running(home / "ediaad.pid", free_port()) is False


def test_read_pid_treats_missing_and_corrupt_files_as_not_running(home):
    path = home / "ediaad.pid"

    assert launcher.read_pid(path) is None

    path.write_text("abc\n", encoding="utf-8")
    assert launcher.read_pid(path) is None
    path.write_text("-4\n", encoding="utf-8")
    assert launcher.read_pid(path) is None
    path.write_text("0\n", encoding="utf-8")
    assert launcher.read_pid(path) is None

    path.write_text(f"{os.getpid()}\n", encoding="utf-8")
    assert launcher.read_pid(path) == os.getpid()


def test_is_alive_reports_live_and_dead_processes(home):
    assert launcher.is_alive(os.getpid()) is True

    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=30)
    assert launcher.is_alive(child.pid) is False

    assert launcher.is_alive(999_999) is False
    assert launcher.is_alive(0) is False
    assert launcher.is_alive(-1) is False


def test_is_running_requires_a_live_process_and_a_responding_service(home):
    """PID 檔與 health check 必須**共同**成立，才算是「同一個 ediaad 在服務」。"""
    from ediaad.app import Application

    path = home / "ediaad.pid"
    port = free_port()
    path.write_text(f"{os.getpid()}\n", encoding="utf-8")

    # 程序活著但沒有服務 → 還不算在執行
    assert launcher.is_running(path, port) is False

    app = Application.create(home=home)
    app.start(port=port)
    try:
        assert launcher.is_running(path, port) is True
    finally:
        app.stop()
        app.close()

    assert launcher.is_running(path, port) is False

    # 埠上只有別人的 listener（不會說 HTTP）→ 也不是我們的服務
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
        listener.listen(1)
        assert launcher.port_is_open(port) is True
        assert launcher.is_running(path, port) is False


def test_wait_ready_times_out_for_a_port_nobody_serves():
    started = time.monotonic()
    assert launcher.wait_ready(free_port(), timeout=0.3) is False
    assert time.monotonic() - started < 5.0


def test_wait_ready_does_not_accept_a_foreign_listener():
    """埠被別的程序佔用時不得算「就緒」（health check 必須真的問到 ediaad）。"""
    port = free_port()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
        listener.listen(1)
        assert launcher.port_is_open(port) is True
        assert launcher.wait_ready(port, timeout=0.5) is False


def test_wait_ready_returns_true_for_a_real_service(home):
    from ediaad.app import Application

    port = free_port()
    app = Application.create(home=home)
    app.start(port=port)
    try:
        assert launcher.wait_ready(port, timeout=10.0) is True
    finally:
        app.stop()
        app.close()


def test_open_browser_prefers_a_browser_that_exists():
    calls: list[list[str]] = []
    paths = {"xdg-open": "/usr/bin/xdg-open"}

    opened = launcher.open_browser(
        "http://127.0.0.1:8787",
        which=paths.get,
        spawn=lambda command, **kwargs: calls.append(command),
    )

    assert opened is True
    assert calls == [["/usr/bin/xdg-open", "http://127.0.0.1:8787"]]

    # 找不到任何瀏覽器時不得拋出例外，只回報沒開成功（呼叫端會把 URL 印出來）
    assert (
        launcher.open_browser(
            "http://127.0.0.1:8787",
            which=lambda name: None,
            spawn=lambda command, **kwargs: calls.append(command),
        )
        is False
    )


# ---- AC-049：啟動器的三種情況 -----------------------------------------------


def test_launcher_reports_a_port_occupied_by_another_program(home, capsys):
    """別人的程序佔住埠時不得誤判為「已在執行」，要回可讀錯誤且不啟動子程序。"""
    port = free_port()
    spawn_calls: list[object] = []

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
        listener.listen(1)
        exit_code = run_launcher(
            home, port, spawn=lambda command, **kwargs: spawn_calls.append(command)
        )

    assert exit_code == launcher.EXIT_INPUT_ERROR
    assert spawn_calls == []
    assert str(port) in capsys.readouterr().err
    assert not launcher.pid_path_for(home).exists()


def test_launcher_terminates_its_child_when_readiness_times_out(home, capsys):
    """就緒逾時要回報失敗並終止自己啟動的子程序，不留孤兒程序。"""

    class FakeChild:
        pid = 4242

        def __init__(self) -> None:
            self.terminated = 0
            self.killed = 0

        def terminate(self) -> None:
            self.terminated += 1

        def kill(self) -> None:
            self.killed += 1

        def wait(self, timeout=None) -> int:
            return 0

        def poll(self):
            return None if not (self.terminated or self.killed) else 0

    child = FakeChild()
    port = free_port()
    exit_code = run_launcher(
        home, port, "--timeout", "0.3", spawn=lambda command, **kwargs: child
    )

    assert exit_code == launcher.EXIT_RUNTIME_ERROR
    assert child.terminated >= 1
    assert "就緒" in capsys.readouterr().err or "逾時" in capsys.readouterr().err


def test_live_pid_with_a_foreign_listener_reports_a_startup_failure(home, capsys):
    """我們的程序還在、但埠被別的程序佔用時，要回報「程序未就緒」（1），
    而不是「埠被其他程序佔用」（2）——後者會誤導使用者去關別人的服務。"""
    port = free_port()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
        listener.listen(1)
        launcher.pid_path_for(home).write_text(f"{os.getpid()}\n", encoding="utf-8")
        spawn_calls: list[object] = []
        exit_code = run_launcher(
            home,
            port,
            "--timeout",
            "0.3",
            spawn=lambda command, **kwargs: spawn_calls.append(command),
        )

    assert exit_code == launcher.EXIT_RUNTIME_ERROR
    assert spawn_calls == []
    message = capsys.readouterr().err
    assert "未就緒" in message and "已被其他程序佔用" not in message


def test_launcher_starts_the_service_and_opens_the_browser_after_readiness(home):
    """未啟動時：背景啟服務 → 等就緒 → 才開瀏覽器（順序本身要被斷言）。"""
    port = free_port()
    opened: list[tuple[str, bool]] = []

    def opener(url: str) -> bool:
        # 開啟瀏覽器的那一刻，服務必須已經在回應
        opened.append((url, launcher.port_is_open(port)))
        return True

    exit_code = run_launcher(home, port, opener=opener)

    assert exit_code == launcher.EXIT_OK
    assert len(opened) == 1
    url, was_ready = opened[0]
    assert was_ready is True
    assert url == f"http://127.0.0.1:{port}"

    pid = launcher.read_pid(launcher.pid_path_for(home))
    assert pid is not None and launcher.is_alive(pid)
    status, payload = http_get(port, "/api/health")
    assert status == 200 and payload["status"] == "ok"


def test_second_launch_only_opens_the_browser(home):
    port = free_port()
    assert run_launcher(home, port, opener=lambda url: True) == launcher.EXIT_OK
    first_pid = launcher.read_pid(launcher.pid_path_for(home))
    assert first_pid is not None

    opened: list[str] = []
    spawn_calls: list[object] = []
    assert (
        run_launcher(
            home,
            port,
            opener=lambda url: opened.append(url) or True,
            spawn=lambda command, **kwargs: spawn_calls.append(command),
        )
        == launcher.EXIT_OK
    )

    assert opened == [f"http://127.0.0.1:{port}"]
    assert spawn_calls == [], "已啟動時不得再啟第二個程序"
    assert launcher.read_pid(launcher.pid_path_for(home)) == first_pid


def test_stale_pid_file_is_treated_as_not_running_and_overwritten(home):
    port = free_port()
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=30)
    launcher.pid_path_for(home).write_text(f"{child.pid}\n", encoding="utf-8")

    assert launcher.is_running(launcher.pid_path_for(home), port) is False
    assert run_launcher(home, port, opener=lambda url: True) == launcher.EXIT_OK

    new_pid = launcher.read_pid(launcher.pid_path_for(home))
    assert new_pid is not None and new_pid != child.pid and launcher.is_alive(new_pid)


# ---- AC-050：優雅關閉 -------------------------------------------------------


def test_application_removes_only_its_own_pid_file(home):
    from ediaad.app import Application

    app = Application.create(home=home)
    try:
        path = app.write_pid_file()
        assert launcher.read_pid(path) == os.getpid()

        # 別人的 PID 檔不得被我們移除
        path.write_text("999999\n", encoding="utf-8")
        app.remove_pid_file()
        assert path.exists()

        path.write_text(f"{os.getpid()}\n", encoding="utf-8")
        app.remove_pid_file()
        assert not path.exists()
    finally:
        app.close()


def test_application_shutdown_stops_the_server_and_removes_the_pid_file(home):
    from ediaad.app import Application

    port = free_port()
    app = Application.create(home=home)
    app.write_pid_file()
    app.start(port=port)
    assert launcher.port_is_open(port) is True

    app.shutdown()

    assert app.running is False
    assert launcher.port_is_open(port) is False
    assert not app.pid_path.exists()


def test_shutdown_endpoint_stops_the_service(home):
    port = free_port()
    assert run_launcher(home, port, opener=lambda url: True) == launcher.EXIT_OK
    pid = launcher.read_pid(launcher.pid_path_for(home))
    assert pid is not None

    status, payload = http_post(port, "/api/shutdown")
    assert status == 200 and payload["status"] == "shutting_down"

    assert wait_until(lambda: not launcher.is_alive(pid), timeout=15.0)
    assert not launcher.pid_path_for(home).exists()
    assert wait_until(lambda: not launcher.port_is_open(port), timeout=10.0)


# ---- AC-049／AC-050：真實入口腳本與 stop.sh ---------------------------------


def test_script_entry_starts_once_and_a_second_run_is_a_no_op(home):
    port = free_port()
    env = script_env(home, port)
    first = subprocess.run(
        [str(PYTHON), str(LAUNCHER_SCRIPT), "--no-browser"],
        cwd=str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert first.returncode == 0, first.stderr
    pid = launcher.read_pid(launcher.pid_path_for(home))
    assert pid is not None and launcher.is_alive(pid)
    assert launcher.wait_ready(port, timeout=10.0) is True

    second = subprocess.run(
        [str(PYTHON), str(LAUNCHER_SCRIPT), "--no-browser"],
        cwd=str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert second.returncode == 0, second.stderr
    assert launcher.read_pid(launcher.pid_path_for(home)) == pid


def test_sigterm_alone_stops_the_service_gracefully(home):
    """送 SIGTERM 就該結束並自己移除 PID 檔（優雅關閉，不必等 SIGKILL）。"""
    port = free_port()
    env = script_env(home, port)
    assert (
        subprocess.run(
            [str(PYTHON), str(LAUNCHER_SCRIPT), "--no-browser"],
            cwd=str(PROJECT_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        ).returncode
        == 0
    )
    pid = launcher.read_pid(launcher.pid_path_for(home))
    assert pid is not None

    os.kill(pid, signal.SIGTERM)

    assert wait_until(lambda: not launcher.is_alive(pid), timeout=8.0)
    assert not launcher.pid_path_for(home).exists(), "服務必須自己移除 PID 檔"
    assert wait_until(lambda: not launcher.port_is_open(port), timeout=5.0)


def test_stop_script_stops_the_service_and_the_service_can_start_again(home):
    port = free_port()
    env = script_env(home, port)
    assert (
        subprocess.run(
            [str(PYTHON), str(LAUNCHER_SCRIPT), "--no-browser"],
            cwd=str(PROJECT_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        ).returncode
        == 0
    )
    first_pid = launcher.read_pid(launcher.pid_path_for(home))
    assert first_pid is not None

    started = time.monotonic()
    stopped = subprocess.run(
        ["sh", str(STOP_SCRIPT)],
        cwd=str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    elapsed = time.monotonic() - started
    assert stopped.returncode == 0, stopped.stderr
    # 優雅路徑：服務收到 SIGTERM 就結束，不該等到逾時後才被 SIGKILL（那要 10 秒以上）
    assert elapsed < 8.0, f"stop.sh 花了 {elapsed:.1f} 秒，可能走到 SIGKILL 路徑"
    assert not launcher.is_alive(first_pid)
    assert not launcher.pid_path_for(home).exists()
    assert wait_until(lambda: not launcher.port_is_open(port), timeout=10.0)

    # 再次啟動必須成功，且是新的程序
    again = subprocess.run(
        [str(PYTHON), str(LAUNCHER_SCRIPT), "--no-browser"],
        cwd=str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert again.returncode == 0, again.stderr
    second_pid = launcher.read_pid(launcher.pid_path_for(home))
    assert second_pid is not None and second_pid != first_pid
    assert launcher.wait_ready(port, timeout=10.0) is True


def test_stop_script_is_executable_and_reports_nothing_to_stop(home):
    assert os.access(STOP_SCRIPT, os.X_OK), "stop.sh 必須可直接執行（./stop.sh）"

    completed = subprocess.run(
        ["sh", str(STOP_SCRIPT)],
        cwd=str(PROJECT_DIR),
        env=script_env(home, free_port()),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0
    output = completed.stdout + completed.stderr
    assert "未在執行" in output
    assert "找不到 PID 檔" in output


def test_desktop_entry_points_at_the_launcher():
    entry = PROJECT_DIR / "ediaad.desktop"
    text = entry.read_text(encoding="utf-8")

    assert "Type=Application" in text
    assert "ediaad_launcher.py" in text
    assert "Name=" in text
    assert "Terminal=false" in text


# ---- AC-050：網頁的「關閉服務」按鈕 -----------------------------------------


def test_index_page_has_the_shutdown_button_wired_to_the_endpoint(home):
    """按鈕與端點都必須存在；前端不得自己「假裝」關閉（一律打後端）。"""
    from ediaad.app import Application

    port = free_port()
    app = Application.create(home=home)
    app.start(port=port)
    try:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            assert response.status == 200
            page = response.read().decode("utf-8")
            connection.request("GET", "/static/app.js")
            script = connection.getresponse().read().decode("utf-8")
        finally:
            connection.close()
    finally:
        app.stop()
        app.close()

    assert 'id="shutdown-button"' in page
    assert 'id="shutdown-status"' in page
    assert "/static/app.js" in page
    assert '"/api/shutdown"' in script


def test_stop_script_clears_a_corrupt_pid_file(home):
    path = launcher.pid_path_for(home)
    path.write_text("not-a-pid\n", encoding="utf-8")

    completed = subprocess.run(
        ["sh", str(STOP_SCRIPT)],
        cwd=str(PROJECT_DIR),
        env=script_env(home, free_port()),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0
    output = completed.stdout + completed.stderr
    assert "未在執行" in output
    assert "無法解讀" in output
    assert not path.exists()


def test_stop_script_escalates_to_sigkill_and_clears_the_pid_file(home):
    """忽略 SIGTERM 的程序：逾時後必須 SIGKILL，並由 stop.sh 清除 PID 檔。"""
    stubborn = subprocess.Popen(
        ["sh", "-c", 'trap "" TERM; sleep 60'],
        start_new_session=True,
    )
    try:
        path = launcher.pid_path_for(home)
        path.write_text(f"{stubborn.pid}\n", encoding="utf-8")
        env = script_env(home, free_port())
        env["EDIAAD_STOP_TIMEOUT"] = "1"

        completed = subprocess.run(
            ["sh", str(STOP_SCRIPT)],
            cwd=str(PROJECT_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

        assert completed.returncode == 0
        assert "SIGKILL" in completed.stdout + completed.stderr
        assert wait_until(lambda: not launcher.is_alive(stubborn.pid), timeout=5.0)
        assert not path.exists()
    finally:
        if launcher.is_alive(stubborn.pid):
            stubborn.kill()
        stubborn.wait(timeout=10)
