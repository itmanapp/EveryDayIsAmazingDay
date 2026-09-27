"""通知文字：三個管道共用同一份標題與內容。

各管道自己拼字串很容易出現「桌面通知說 50%、網頁提示說 0.5」這種語意不一致，因此
標題與內容只在這裡產生一次（`notification_text`），其餘模組只負責傳遞與呈現。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["describe_probability", "notification_text"]


def describe_probability(up_probability: Any, samples: Any) -> str:
    """歷史統計的文字；**沒有樣本時明說「無樣本」而不是 0%**（F-003 的同一原則）。"""
    if not samples:
        return "無樣本（沒有可用的歷史統計）"
    if up_probability is None:
        return "無樣本"
    return f"{float(up_probability) * 100:.1f}%（{int(samples)} 次）"


def notification_text(event: Mapping[str, Any]) -> tuple[str, str]:
    """由一筆事件產生 `(標題, 內容)`。"""
    symbol = str(event.get("symbol", "")).strip() or "未知商品"
    interval = str(event.get("interval", "")).strip()
    title = f"ediaad：{symbol} {interval} 出現規律".strip()
    body = (
        f"{event.get('pattern_id', '')} 於 {event.get('event_start_time', '')} 命中，"
        f"信心 {float(event.get('confidence', 0.0)):.4f}，"
        "歷史上漲機率 "
        f"{describe_probability(event.get('history_up_probability'), event.get('history_samples'))}"
    )
    return title, body
