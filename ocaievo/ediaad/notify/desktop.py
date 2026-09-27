"""服務端桌面通知管道（AC-051）。

命令組裝是**純函式**（`command_for`），因此可以在不執行任何東西的情況下驗證三個平台的
命令；實際執行由可注入的 `runner` 負責，失敗（命令不存在、非 0 結束、`OSError`、沒有
桌面工作階段）一律只記 warning——**通知失敗絕不能中斷監控迴圈**。

平台命令：Linux `notify-send`、macOS `osascript`、Windows PowerShell 的 WinRT toast。
macOS／Windows 只產生命令，**未實機驗證**（SPEC 第 2 節 out of scope）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .message import notification_text

__all__ = ["DesktopNotifier", "command_for", "command_name"]


def command_name(platform: str) -> str | None:
    """該平台用來發桌面通知的執行檔名；不支援的平台回 `None`。"""
    if platform == "linux":
        return "notify-send"
    if platform == "darwin":
        return "osascript"
    if platform.startswith("win"):
        return "powershell"
    return None


def _apple_quote(text: Any) -> str:
    """AppleScript 字串（用 JSON 的引號規則，雙引號與反斜線都能安全跳脫）。"""
    return json.dumps(str(text), ensure_ascii=False)


def _powershell_quote(text: Any) -> str:
    """PowerShell 單引號字串（單引號以兩個單引號跳脫）。"""
    return "'" + str(text).replace("'", "''") + "'"


def _toast_script(title: Any, body: Any) -> str:
    """標準 Windows 的 WinRT toast（不需要任何第三方模組）。"""
    return (
        "$ErrorActionPreference='Stop';"
        "[void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
        " ContentType=WindowsRuntime];"
        "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$x=$t.GetElementsByTagName('text');"
        f"$x.Item(0).AppendChild($t.CreateTextNode({_powershell_quote(title)}))|Out-Null;"
        f"$x.Item(1).AppendChild($t.CreateTextNode({_powershell_quote(body)}))|Out-Null;"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('ediaad')"
        ".Show([Windows.UI.Notifications.ToastNotification]::new($t))"
    )


def command_for(platform: str, title: Any, body: Any) -> list[str]:
    """組出該平台的桌面通知命令；不支援的平台回空清單（呼叫端據此跳過）。"""
    name = command_name(platform)
    if name is None:
        return []
    if name == "notify-send":
        return ["notify-send", str(title), str(body)]
    if name == "osascript":
        return [
            "osascript",
            "-e",
            f"display notification {_apple_quote(body)} with title {_apple_quote(title)}",
        ]
    return [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        _toast_script(title, body),
    ]


def _default_runner(command: Sequence[str]) -> Any:
    return subprocess.run(
        list(command), check=False, capture_output=True, timeout=5
    )


def _default_warn(message: str) -> None:
    print(f"[WARN] {message}", file=sys.stderr)


class DesktopNotifier:
    """服務端桌面通知；所有失敗都只記 warning。"""

    name = "desktop"

    def __init__(
        self,
        platform: str | None = None,
        *,
        runner: Callable[[Sequence[str]], Any] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        env: Mapping[str, str] | None = None,
        warn: Callable[[str], None] | None = None,
    ) -> None:
        self.platform = platform if platform is not None else sys.platform
        self.runner = runner if runner is not None else _default_runner
        self.which = which
        self.env = os.environ if env is None else env
        self.warn = warn if warn is not None else _default_warn

    def notify(self, event: Mapping[str, Any]) -> None:
        name = command_name(self.platform)
        if name is None:
            self.warn(f"平台 {self.platform} 沒有支援的桌面通知命令，跳過桌面通知")
            return
        if not self.which(name):
            self.warn(f"找不到桌面通知命令 {name}，跳過桌面通知")
            return
        if self.platform == "linux" and not self.env.get("DBUS_SESSION_BUS_ADDRESS"):
            self.warn(
                "DBUS_SESSION_BUS_ADDRESS 未設定（沒有可用的桌面工作階段），跳過桌面通知"
            )
            return

        title, body = notification_text(event)
        command = command_for(self.platform, title, body)
        try:
            completed = self.runner(command)
        except OSError as error:
            self.warn(f"執行桌面通知命令 {name} 失敗：{error}")
            return
        returncode = getattr(completed, "returncode", 0)
        if returncode:
            self.warn(f"桌面通知命令 {name} 回傳 {returncode}，通知可能沒有送出")
