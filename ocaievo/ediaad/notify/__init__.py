"""三管道通知（AC-051）：網頁內提示、瀏覽器原生通知、服務端桌面通知。

三個管道都只是「同一個事件的不同呈現」，因此**引擎完全不需要知道通知的存在**：
`monitor.run_once` 的 `emit` 介面不變，`Application.make_emit()` 把同一個 payload 交給
這裡的 notifier 清單（報告第 6.6 節「引擎 0 改動」）。

`build_notifiers` 依平台與環境組出**可用**的管道：

| 情況 | 結果 |
| --- | --- |
| Linux ＋ `notify-send` 存在 | 網頁 ＋ 瀏覽器 ＋ 桌面（3 個） |
| Linux ＋ 沒有 `notify-send` | 網頁 ＋ 瀏覽器（2 個） |
| macOS ＋ `osascript`／Windows ＋ `powershell` | 3 個（命令產生，未實機驗證） |
| 其他平台 | 網頁 ＋ 瀏覽器（2 個） |

桌面通知**預設不啟用**（`Application.create()` 不會建立它們）：測試或工具不該在使用者
的桌面上彈通知；服務啟動路徑（`launcher --serve`）會明確呼叫 `enable_notifications()`。
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from .browser import BrowserNotifier
from .desktop import DesktopNotifier, command_name
from .message import notification_text
from .web import WebNotifier

__all__ = [
    "BrowserNotifier",
    "DesktopNotifier",
    "Notifier",
    "WebNotifier",
    "build_notifiers",
    "notification_text",
]


@runtime_checkable
class Notifier(Protocol):
    """一個通知管道：收到事件後以自己的方式呈現（失敗不得往外丟）。"""

    name: str

    def notify(self, event: Mapping[str, Any]) -> None:  # pragma: no cover - 介面
        ...


def build_notifiers(
    hub: Any,
    *,
    platform: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[[Sequence[str]], Any] | None = None,
    env: Mapping[str, str] | None = None,
    warn: Callable[[str], None] | None = None,
) -> list[Notifier]:
    """組出這個環境可用的通知管道（順序固定：網頁 → 瀏覽器 → 桌面）。"""
    resolved = platform if platform is not None else sys.platform
    notifiers: list[Notifier] = [WebNotifier(hub), BrowserNotifier(hub)]

    name = command_name(resolved)
    if name is not None and which(name):
        notifiers.append(
            DesktopNotifier(
                resolved, runner=runner, which=which, env=env, warn=warn
            )
        )
    return notifiers
