"""網頁層：標準庫 HTTP 服務、路由註冊表與原生前端骨架（TASK-020）。

對外只匯出 `create_server` 與 `routes`（SPEC 第 5 節的模組表）；`sse_hub` 是 TASK-021 的
佔位，尚未存在。
"""

from __future__ import annotations

from . import routes
from .server import create_server, static_dir

__all__ = ["create_server", "routes", "static_dir"]
