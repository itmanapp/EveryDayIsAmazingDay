#!/usr/bin/env python3
"""建立 ediaad 的隔離環境：``.venv``、pip 與依賴。

為什麼需要這支腳本（見 ``docs/workflow/PROJECT.md`` 的環境實測）：

- 目標環境**沒有預裝 pip**，也**不能使用 sudo** 安裝系統套件。
- 因此先以 ``venv --without-pip`` 建立環境，再用標準庫下載 ``get-pip.py`` 取得 pip。
- 只用標準庫 ``urllib``，不依賴 curl／wget。

設計特性：

- **冪等**：``.venv`` 已存在且依賴可用時直接成功，不重複安裝。
- **不破壞既有環境**：任何失敗都保留 ``.venv``，只回報可讀錯誤。
- **與工作目錄無關**：所有路徑以本檔位置解析，從任何目錄執行都指向同一個 ``ocaievo/.venv``。

exit code：``0`` 成功；``1`` 執行期失敗（下載或安裝失敗）；``2`` 輸入或環境錯誤。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.error
import urllib.request
import venv
from pathlib import Path

# ocaievo/：本檔位於 ocaievo/scripts/，因此往上兩層。
PROJECT_DIR = Path(__file__).resolve().parent.parent
VENV_DIR = PROJECT_DIR / ".venv"
REQUIREMENTS_FILES = ("requirements.txt", "requirements-dev.txt")
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
REQUIRED_MODULES = ("numpy", "pandas", "pytest")
MIN_PYTHON = (3, 10)
DOWNLOAD_TIMEOUT_SECONDS = 60

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_INPUT_ERROR = 2


def log(message: str) -> None:
    print(f"[bootstrap] {message}", flush=True)


def venv_python(venv_dir: Path) -> Path:
    """回傳 venv 內的 Python 執行檔路徑（相容 POSIX 與 Windows 佈局）。"""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def run(command: list[str], description: str) -> subprocess.CompletedProcess:
    log(description)
    return subprocess.run(command, check=False)


def create_venv(venv_dir: Path) -> None:
    log(f"建立虛擬環境：{venv_dir}")
    venv.EnvBuilder(with_pip=False, clear=False).create(str(venv_dir))


def pip_available(python: Path) -> bool:
    if not python.exists():
        return False
    result = subprocess.run(
        [str(python), "-m", "pip", "--version"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def download_get_pip(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    log(f"下載 get-pip.py：{GET_PIP_URL}")
    with urllib.request.urlopen(GET_PIP_URL, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        payload = response.read()
    if not payload:
        raise RuntimeError("get-pip.py 下載結果為空")
    destination.write_bytes(payload)


def install_pip(python: Path, get_pip_path: Path) -> int:
    return run(
        [str(python), str(get_pip_path), "--no-warn-script-location"],
        "以 get-pip.py 安裝 pip 到 .venv",
    ).returncode


def install_requirements(python: Path, requirements: list[Path]) -> int:
    command = [str(python), "-m", "pip", "install", "--no-warn-script-location"]
    for path in requirements:
        command += ["-r", str(path)]
    return run(command, "安裝依賴：" + "、".join(p.name for p in requirements)).returncode


def dependencies_available(python: Path) -> bool:
    if not python.exists():
        return False
    result = subprocess.run(
        [str(python), "-c", f"import {', '.join(REQUIRED_MODULES)}"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def report_versions(python: Path) -> None:
    script = (
        "import numpy, pandas, pytest, sys;"
        "print(f'python {sys.version.split()[0]}');"
        "print(f'numpy {numpy.__version__}');"
        "print(f'pandas {pandas.__version__}');"
        "print(f'pytest {pytest.__version__}')"
    )
    subprocess.run([str(python), "-c", script], check=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bootstrap_env.py",
        description="建立 ocaievo/.venv、取得 pip 並安裝 ediaad 的依賴（可重複執行）。",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="刪除既有 .venv 後重建（預設沿用既有環境）。",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只檢查 .venv 與依賴是否就緒，不做任何變更。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if sys.version_info < MIN_PYTHON:
        log(
            f"需要 Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 以上，"
            f"目前為 {sys.version.split()[0]}"
        )
        return EXIT_INPUT_ERROR

    missing = [name for name in REQUIREMENTS_FILES if not (PROJECT_DIR / name).is_file()]
    if missing:
        log(f"找不到依賴清單：{'、'.join(missing)}（預期位於 {PROJECT_DIR}）")
        return EXIT_INPUT_ERROR

    requirements = [PROJECT_DIR / name for name in REQUIREMENTS_FILES]
    python = venv_python(VENV_DIR)

    if args.check:
        if dependencies_available(python):
            log("檢查通過：.venv 與依賴皆就緒")
            report_versions(python)
            return EXIT_OK
        log("檢查失敗：.venv 或依賴尚未就緒")
        return EXIT_RUNTIME_ERROR

    if args.recreate and VENV_DIR.exists():
        log(f"--recreate：移除既有環境 {VENV_DIR}")
        import shutil

        shutil.rmtree(VENV_DIR)

    if VENV_DIR.exists() and pip_available(python) and dependencies_available(python):
        log("環境已就緒，無需變更（冪等）")
        report_versions(python)
        return EXIT_OK

    try:
        if not python.exists():
            create_venv(VENV_DIR)
        if not pip_available(python):
            get_pip_path = PROJECT_DIR / ".cache" / "get-pip.py"
            download_get_pip(get_pip_path)
            if install_pip(python, get_pip_path) != 0:
                log("安裝 pip 失敗；既有 .venv 保持不變，可重跑本腳本")
                return EXIT_RUNTIME_ERROR
        if install_requirements(python, requirements) != 0:
            log("安裝依賴失敗；既有 .venv 保持不變，可重跑本腳本")
            return EXIT_RUNTIME_ERROR
    except (urllib.error.URLError, OSError, RuntimeError) as error:
        log(f"環境建置失敗：{type(error).__name__}: {error}")
        log("既有 .venv 未被刪除；修正問題後可重跑本腳本")
        return EXIT_RUNTIME_ERROR

    if not dependencies_available(python):
        log(f"依賴安裝後仍無法 import：{', '.join(REQUIRED_MODULES)}")
        return EXIT_RUNTIME_ERROR

    log("完成")
    report_versions(python)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
