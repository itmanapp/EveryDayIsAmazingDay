"""瀏覽器原生通知管道（AC-051）。

伺服器不能直接叫瀏覽器顯示通知，因此本管道把「要顯示什麼」組成一份**獨立的事件**
（`event="notification"`，內容只有 `title`／`body`／`tag`）經既有推播送達頁面，由
`notify.js` 呼叫 `Notification` API。

**為什麼要獨立事件**：`SSEHub` 以事件內容去重，若兩個管道送同一份 payload，第二個會被
當成重複而抑制。這份 payload 刻意**不含**去重鍵欄位，因此它的 id 是內容雜湊（與網頁管道
的 id 不同）；`tag` 則帶上去重鍵，讓頁面端也能以同一個鍵避免重複顯示。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..web.sse_hub import event_id_for
from .message import notification_text

__all__ = ["BrowserNotifier", "notification_for"]


def notification_for(event: Mapping[str, Any]) -> dict[str, str]:
    """前端 `Notification` 所需的 payload（契約：只有 `title`／`body`／`tag`）。"""
    title, body = notification_text(event)
    return {"title": title, "body": body, "tag": event_id_for(event)}


class BrowserNotifier:
    """瀏覽器原生通知（`event="notification"`，由 `notify.js` 顯示）。"""

    name = "browser"

    def __init__(self, hub: Any, *, event: str = "notification") -> None:
        self.hub = hub
        self.event = event

    def notify(self, event: Mapping[str, Any]) -> None:
        self.hub.publish(notification_for(event), event=self.event)
