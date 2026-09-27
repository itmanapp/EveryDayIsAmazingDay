"""桌面一鍵啟動、重複啟動防護與優雅關閉（AC-049／AC-050）。

兩個入口：

- `main(argv)`：使用者與桌面圖示的入口。判定是否已在執行 → 必要時以**背景子程序**
  啟動服務 → 等就緒（`GET /api/health`，最多 `--timeout` 秒，預設 10）→ 開瀏覽器。
- `serve_main(argv)`／`--serve`：被啟動的那個**服務程序**。寫 PID 檔、安裝訊號處理
  常式（`SIGTERM`／`SIGINT`）、等待關閉事件，最後走 `Application.shutdown()`。
  TASK-036 的 `serve` 子命令應呼叫同一個函式，不要再寫第二套。

**重複啟動的判定**（AC-049 要求「PID 檔與埠探測共同判定」）：

| 情況 | 判定 | 動作 |
| --- | --- | --- |
| PID 檔指向活著的程序且埠有回應 | 已在執行 | 只開瀏覽器 |
| PID 檔指向活著的程序但埠還沒回應 | 啟動中 | 等它就緒，**不**啟第二個程序 |
| PID 檔不存在／內容損毀／程序已死 | 未執行 | 可安全覆寫 PID 檔並啟動 |
| 沒有我們的 PID 檔但埠被佔用 | **不是** ediaad | 回可讀錯誤（exit 2），不啟子程序 |

外部效果全部可注入（`opener`／`spawn`／`which`），因此測試不需要真的開瀏覽器，
也不會動到使用者正在執行的服務（SPEC 第 5 節原則 2）。
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .app import Application
from .license import (
    HTTP_CLIENT,
    check_lease,
    has_feature,
    machine_fingerprint,
    public_key_from_env,
)
from .paths import (
    high_water_path,
    home_root,
    lease_path as license_path,
    pid_path,
    revoked_path,
)

__all__ = [
    "BROWSERS",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_TIMEOUT",
    "EXIT_INPUT_ERROR",
    "EXIT_OK",
    "EXIT_RUNTIME_ERROR",
    "build_parser",
    "is_alive",
    "is_running",
    "main",
    "open_browser",
    "pid_path_for",
    "port_is_open",
    "read_pid",
    "serve_main",
    "wait_ready",
]

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_INPUT_ERROR = 2

DEFAULT_PORT = 8787
DEFAULT_HOST = "127.0.0.1"
#: 就緒等待上限（秒）；SPEC 第 6 節：啟動就緒等待上限 10 秒。
DEFAULT_TIMEOUT = 10.0
#: 依序嘗試的瀏覽器開啟指令（PROJECT.md 的環境實測：三者都存在）。
BROWSERS: tuple[str, ...] = ("xdg-open", "firefox", "google-chrome")
#: 就緒探測間隔（秒）；10 秒內最多約 200 次，夠快也不會吃掉 CPU。
READY_INTERVAL = 0.05
#: 服務程序的專案根目錄（`ediaad/` 的上一層），子程序必須在此目錄才能 `-m ediaad.launcher`。
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def pid_path_for(home: str | Path | None = None) -> Path:
    """PID 檔位置（`<home>/ediaad.pid`）；與 `stop.sh` 的約定一致。"""
    return pid_path(home)


def read_pid(path: str | Path) -> int | None:
    """讀 PID 檔；不存在、內容損毀或不是正整數時回 `None`（視為未執行，可安全覆寫）。"""
    try:
        content = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        pid = int(content)
    except ValueError:
        return None
    return pid if pid > 0 else None


def _is_zombie(pid: int) -> bool:
    """Linux：`/proc/<pid>/stat` 的狀態欄是 `Z` 表示程序已結束但還沒被回收。

    `os.kill(pid, 0)` 對殭屍程序仍然成功，因此「還在跑」的判定不能只看它：啟動器若把
    殭屍當成「已在執行」，就會拒絕啟動而使用者永遠開不起服務。
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return False
    try:
        return stat.rsplit(")", 1)[1].split()[0] == "Z"
    except IndexError:  # pragma: no cover - /proc 格式異常時保守回 False
        return False


def is_alive(pid: int) -> bool:
    """該 PID 是否**還在跑**（沒有權限時視為存在；已結束的殭屍不算）。"""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return not _is_zombie(pid)


def port_is_open(port: int, host: str = DEFAULT_HOST, timeout: float = 0.5) -> bool:
    """該埠是否有人接受連線（純 TCP 探測；用來判斷「被別的程序佔用」）。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_running(pid_path: str | Path, port: int, *, host: str = DEFAULT_HOST) -> bool:
    """「同一個 ediaad 正在服務」：PID 檔指向活著的程序，且該埠的 health check 通過。

    兩者缺一不可（AC-049 要求「共同判定」）：只看 PID 檔可能是陳舊的，只看埠可能是
    別人的程序佔用——因此埠那一半問的是 `/api/health`，而不是「有沒有人接受連線」。
    純 TCP 探測留給「埠被別的程序佔用」的判斷（`port_is_open`），兩者語意不同。
    """
    pid = read_pid(pid_path)
    if pid is None or not is_alive(pid):
        return False
    return _health_ok(port, host, timeout=0.5)


def _health_ok(port: int, host: str, timeout: float) -> bool:
    """`GET /api/health` 是否回 `{"status": "ok"}`（比純 TCP 探測更強的就緒訊號）。"""
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request("GET", "/api/health")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return False
    finally:
        connection.close()
    return response.status == 200 and payload.get("status") == "ok"


def wait_ready(
    port: int,
    timeout: float = DEFAULT_TIMEOUT,
    *,
    host: str = DEFAULT_HOST,
    interval: float = READY_INTERVAL,
) -> bool:
    """等服務就緒：在 `timeout` 秒內不斷做 health check，逾時回 `False`。"""
    deadline = time.monotonic() + timeout
    while True:
        if _health_ok(port, host, timeout=min(1.0, max(0.1, timeout))):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


def open_browser(
    url: str,
    *,
    which: Callable[[str], str | None] = shutil.which,
    spawn: Callable[..., Any] = subprocess.Popen,
) -> bool:
    """以 `xdg-open`／`firefox`／`google-chrome` 開啟 URL；找不到就回 `False`。

    不等待瀏覽器結束（`Popen` 之後就返回），否則啟動器會被瀏覽器佔住。
    `which`／`spawn` 可注入，因此測試不會真的開瀏覽器。
    """
    for name in BROWSERS:
        path = which(name)
        if not path:
            continue
        try:
            spawn([path, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            continue
        return True
    return False


def build_parser() -> argparse.ArgumentParser:
    """啟動器與服務程序共用的解析器（`--serve` 時是服務程序）。"""
    parser = argparse.ArgumentParser(
        prog="ediaad_launcher",
        description="ediaad 一鍵啟動：需要時以背景程序啟動服務，就緒後開啟瀏覽器。",
    )
    parser.add_argument(
        "--home",
        default=None,
        help="資料根目錄（預設 $EDIAAD_HOME，未設定時為 ~/.local/share/ediaad）",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"綁定位址（預設 {DEFAULT_HOST}）")
    parser.add_argument(
        "--port",
        type=int,
        default=os.environ.get("EDIAAD_PORT", str(DEFAULT_PORT)),
        help=f"服務埠（預設 $EDIAAD_PORT 或 {DEFAULT_PORT}）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"就緒等待上限秒數（預設 {DEFAULT_TIMEOUT}）",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="只啟動服務，不開啟瀏覽器（測試或無桌面環境時使用）",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="以服務程序身分執行（由啟動器自行呼叫；一般不直接使用）",
    )
    return parser


def _serve_command(args: argparse.Namespace) -> list[str]:
    """啟動子程序用的命令：同一個模組的 `--serve` 模式（不需要 TASK-036 的 `serve` 子命令）。"""
    return [
        sys.executable,
        "-m",
        "ediaad.launcher",
        "--serve",
        "--host",
        str(args.host),
        "--port",
        str(args.port),
    ] + (["--home", str(args.home)] if args.home else [])


def _spawn_service(command: Sequence[str], **kwargs: Any) -> Any:
    """以背景子程序啟動服務。

    `start_new_session=True`：服務不隨啟動器（或啟動它的終端機）結束而被帶走——
    桌面圖示的情境下啟動器會立刻退出。
    """
    kwargs.setdefault("cwd", str(PROJECT_ROOT))
    kwargs.setdefault("stdout", subprocess.DEVNULL)
    kwargs.setdefault("stderr", subprocess.DEVNULL)
    kwargs.setdefault("start_new_session", True)
    return subprocess.Popen(list(command), **kwargs)


def _terminate(child: Any) -> None:
    """先送 SIGTERM，等不到結束才 SIGKILL（就緒逾時時不留孤兒程序）。"""
    try:
        child.terminate()
    except OSError:
        return
    try:
        child.wait(timeout=5)
    except Exception:  # noqa: BLE001 - 任何等待失敗都要繼續嘗試強制結束
        try:
            child.kill()
        except OSError:
            pass


def _run_service(args: argparse.Namespace) -> int:
    """服務程序本體：寫 PID 檔 → 啟動 → 等關閉事件 → 優雅關閉。"""
    home = home_root(args.home)
    app = Application.create(home=home)
    # 更新服務位址由**服務入口**讀取（`Application` 不依賴環境變數，測試才天然隔離）。
    app.update_url = (os.environ.get("EDIAAD_UPDATE_URL") or "").strip()

    # ---- 授權啟動驗證（TASK-030／AC-053、AC-056、AC-058；接線在 TASK-036） ----
    # 「每次啟動都要離線驗章」（報告第 6.4 節）。**未啟用是合法狀態**：那時要讓服務起來，
    # 使用者才進得了網頁的「授權」區塊完成啟用（AC-066）；租約存在但無效（過期／撤銷／
    # 別台機器／簽章失敗）才是必須停下來的導流情境。
    verdict = check_lease(
        fingerprint=machine_fingerprint(),
        public_key=public_key_from_env(),
        http=HTTP_CLIENT,
        url=(os.environ.get("EDIAAD_LICENSE_URL") or "").strip() or None,
        lease_path=license_path(home),
        high_water_path=high_water_path(home),
        revoked_path=revoked_path(home),
    )
    if not verdict.ok and "尚未啟用" not in verdict.reason:
        print(f"錯誤：{verdict.reason}", file=sys.stderr)
        if verdict.force_online:
            print(
                "錯誤：系統時間異常，且線上驗證不可用；請確認網路後再啟動（不以本地時間延長授權）",
                file=sys.stderr,
            )
            app.close()
            return EXIT_RUNTIME_ERROR
        print(
            "提示：請至重新申請頁取得新密鑰，再以 `python -m ediaad license activate --key <密鑰>` 啟用",
            file=sys.stderr,
        )
        app.close()
        return EXIT_INPUT_ERROR
    if not verdict.ok:
        print(f"[LICENSE] {verdict.reason}；服務仍會啟動，請在網頁的「授權」區塊輸入密鑰")
    else:
        # AC-057 的功能分級：租約沒有 `update` 就停用更新檢查（只改記憶體，不動使用者的設定檔）
        if not has_feature(verdict.lease, "update"):
            app.settings["update_enabled"] = False
        print(f"[LICENSE] 授權有效：{verdict.lease.key_id}（到期 {verdict.lease.expires_at}）")

    # 設定檔損毀時**仍然啟動**：網頁是唯一的修復介面（TASK-020 的凍結設計），
    # 因此這裡只把問題印出來，讓它同時出現在網頁的系統狀態。
    if app.problems:
        detail = "、".join(f"{name}={message}" for name, message in app.problems.items())
        print(f"[WARN] 啟動時發現問題（服務仍會啟動）：{detail}", file=sys.stderr)

    app.write_pid_file()
    app.install_signal_handlers()
    # 三管道通知（AC-051）：只有服務啟動路徑會啟用，測試與工具不會誤觸桌面通知。
    app.enable_notifications()
    try:
        app.start(host=args.host, port=args.port)
    except OSError as error:
        app.remove_pid_file()
        app.close()
        print(f"錯誤：無法綁定 {args.host}:{args.port}：{error}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    print(f"[SERVE] ediaad 已啟動：http://{args.host}:{args.port}（PID {os.getpid()}）")
    try:
        while not app.shutdown_event.wait(0.2):
            if not app.running:
                break
    except KeyboardInterrupt:  # pragma: no cover - 訊號處理常式已接手，僅保險
        pass
    finally:
        app.shutdown()
    print("[STOP] ediaad 已優雅關閉")
    return EXIT_OK


def serve_main(argv: Sequence[str] | None = None) -> int:
    """服務程序入口（`--serve` 或 TASK-036 的 `serve` 子命令都應呼叫這裡）。"""
    return _run_service(build_parser().parse_args(argv))


def main(
    argv: Sequence[str] | None = None,
    *,
    opener: Callable[[str], bool] | None = None,
    spawn: Callable[..., Any] | None = None,
) -> int:
    """一鍵啟動（AC-049）。回傳 process exit code：0 成功、1 服務未就緒、2 埠被佔用等。"""
    args = build_parser().parse_args(argv)
    if args.serve:
        return _run_service(args)

    home = home_root(args.home)
    path = pid_path_for(home)
    port = args.port
    url = f"http://{args.host}:{port}"
    open_url = opener if opener is not None else (lambda target: open_browser(target))
    spawn_child = spawn if spawn is not None else _spawn_service

    if is_running(path, port, host=args.host):
        open_url(url)
        return EXIT_OK

    pid = read_pid(path)
    if pid is not None and is_alive(pid):
        # 程序在，但還沒就緒（例如剛被另一個啟動器叫起來）→ 等它，不啟第二個
        if wait_ready(port, args.timeout, host=args.host):
            open_url(url)
            return EXIT_OK
        print(
            f"錯誤：偵測到 ediaad 程序（PID {pid}），但 {port} 埠在 {args.timeout} 秒內未就緒",
            file=sys.stderr,
        )
        return EXIT_RUNTIME_ERROR

    if port_is_open(port, args.host):
        print(
            f"錯誤：{args.host}:{port} 已被其他程序佔用（不是 ediaad 的 PID 檔所指的程序）；"
            "請先關閉它，或以 --port 指定其他埠",
            file=sys.stderr,
        )
        return EXIT_INPUT_ERROR

    if path.exists():
        print(f"注意：{path} 是陳舊的 PID 檔（程序已不存在），將覆寫", file=sys.stderr)

    child = spawn_child(_serve_command(args))
    try:
        if not wait_ready(port, args.timeout, host=args.host):
            print(
                f"錯誤：服務在 {args.timeout} 秒內未就緒，已終止啟動的程序（PID {getattr(child, 'pid', '?')}）",
                file=sys.stderr,
            )
            _terminate(child)
            return EXIT_RUNTIME_ERROR
    except BaseException:
        _terminate(child)
        raise

    if not args.no_browser and not open_url(url):
        print(f"無法自動開啟瀏覽器，請手動開啟：{url}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - 由 scripts/ediaad_launcher.py 進入
    raise SystemExit(main())
