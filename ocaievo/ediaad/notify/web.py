"""網頁內提示管道：把事件推給已連線的頁面（AC-051）。

只是 `SSEHub.publish` 的薄包裝——推播的訂閱管理、去重與慢速客戶端保護都在 TASK-021
的 hub 裡，本模組不重寫任何一條。**沒有訂閱者時仍然「靜默」**：`publish` 會記錄事件 id
（去重需要）但沒有任何客戶端收到內容。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["WebNotifier"]


class WebNotifier:
    """網頁內提示（`event="alert"`，由 `events.js` 顯示在事件清單）。"""

    name = "web"

    def __init__(self, hub: Any, *, event: str = "alert") -> None:
        self.hub = hub
        self.event = event

    def notify(self, event: Mapping[str, Any]) -> None:
        """推播一筆事件；`SSEHub` 會抑制重複 id（第二道防線）。"""
        self.hub.publish(event, event=self.event)
