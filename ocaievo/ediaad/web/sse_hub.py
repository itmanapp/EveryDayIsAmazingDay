"""SSE 推播中樞與幀格式（TASK-021）。

**為什麼用 SSE 而不是 WebSocket**：單向推播足夠、比 WebSocket 簡單、標準庫就能實作
（報告第 6.3 節），且不需要任何第三方套件。

**去重的分工**：真正的去重是「引擎 ＋ 落地儲存」的責任（TASK-010／TASK-018 的鍵：
商品、週期、規律 ID、事件開始時間）。本模組只做**傳輸層的第二道防線**——同一個事件 id
不會被廣播第二次，因此客戶端以 `Last-Event-ID` 重連時不可能收到已顯示過的事件。事件
歷史端點（`GET /api/events`）是「重連期間漏掉什麼」的權威來源，前端以 id 合併。

`publish` 由監控執行緒呼叫，因此**絕不阻塞**：慢速或已死的客戶端只會讓自己的佇列滿，
滿了就丟棄新幀（歷史端點補得回來），不會拖住掃描。
"""

from __future__ import annotations

import collections
import hashlib
import json
import logging
import queue
import threading
from collections.abc import Mapping
from typing import Any

__all__ = ["KEEP_ALIVE_FRAME", "SSEHub", "event_id_for", "format_sse"]

logger = logging.getLogger("ediaad.web")

#: 沒有事件時送出的註解行（SSE 註解，客戶端會忽略但要維持連線）。
KEEP_ALIVE_FRAME = b": keep-alive\n\n"

#: 去重鍵的四個欄位（與 `monitor.AlertState`、`store.Store` 完全一致）。
KEY_FIELDS: tuple[str, ...] = ("symbol", "interval", "pattern_id", "event_start_time")


def event_id_for(payload: Mapping[str, Any]) -> str:
    """事件的穩定 id：優先用去重鍵，缺少時用內容雜湊（同一內容仍是同一個 id）。"""
    parts = [str(payload.get(field, "")).strip() for field in KEY_FIELDS]
    if all(parts):
        return "|".join(parts)
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return digest[:16]


def format_sse(
    payload: Mapping[str, Any], event: str = "alert", event_id: str | None = None
) -> bytes:
    """產生一個合法的 SSE 幀（`id:`／`event:`／`data:` ＋ 空行）。

    `data` 必須逐行處理：JSON 內容若含換行（例如說明文字），每個實體行都要有自己的
    `data: ` 前綴，否則客戶端會把整幀解讀成兩幀。
    """
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event:
        lines.append(f"event: {event}")

    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    for line in text.splitlines() or [""]:
        lines.append(f"data: {line}")
    return ("\n".join(lines) + "\n\n").encode("utf-8")


class SSEHub:
    """已連線客戶端的註冊表與廣播器（執行緒安全）。"""

    def __init__(self, *, queue_size: int = 64, recent_limit: int = 512) -> None:
        self._subscribers: set[queue.Queue[bytes]] = set()
        self._lock = threading.Lock()
        self._recent: collections.OrderedDict[str, None] = collections.OrderedDict()
        self.queue_size = queue_size
        self.recent_limit = recent_limit

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def subscribe(self) -> queue.Queue[bytes]:
        """新增一個訂閱者並回傳它的佇列。"""
        subscriber: queue.Queue[bytes] = queue.Queue(maxsize=self.queue_size)
        with self._lock:
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[bytes]) -> None:
        """移除訂閱者（幂等）。"""
        with self._lock:
            self._subscribers.discard(subscriber)

    def publish(self, payload: Mapping[str, Any], *, event: str = "alert") -> str | None:
        """廣播一個事件；已廣播過的 id 會被抑制並回傳 `None`。"""
        identifier = event_id_for(payload)
        with self._lock:
            if identifier in self._recent:
                logger.debug("SSE 略過重複事件 %s", identifier)
                return None
            self._recent[identifier] = None
            while len(self._recent) > self.recent_limit:
                self._recent.popitem(last=False)
            subscribers = tuple(self._subscribers)

        frame = format_sse(payload, event=event, event_id=identifier)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(frame)
            except queue.Full:
                # 慢速客戶端：丟棄這一幀。歷史端點是補齊的權威來源，且絕不能阻塞發布端。
                logger.warning("SSE 訂閱者佇列已滿，丟棄一幀：%s", identifier)
        return identifier

    def seen_ids(self) -> tuple[str, ...]:
        """最近廣播過的 id（供測試與系統狀態頁觀察）。"""
        with self._lock:
            return tuple(self._recent)
