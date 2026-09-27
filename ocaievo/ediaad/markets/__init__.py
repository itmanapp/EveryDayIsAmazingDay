"""市場來源：`base` 提供介面與 registry，各子模組提供實作。

匯入本套件即註冊所有內建來源：`custom`（自訂 CSV）、`crypto`（Binance）、`twse`
（台股日線）與 `us`（Twelve Data 美股）。
"""

from __future__ import annotations

from . import adjust, calendar, catalog, crypto, custom, twse, us
from .base import (
    DEFAULT_SOURCE_ID,
    INTERVAL_ORDER,
    Instrument,
    Source,
    all_sources,
    get_source,
    register,
    unregister,
)

__all__ = [
    "DEFAULT_SOURCE_ID",
    "INTERVAL_ORDER",
    "Instrument",
    "Source",
    "adjust",
    "all_sources",
    "calendar",
    "catalog",
    "crypto",
    "custom",
    "twse",
    "us",
    "get_source",
    "register",
    "unregister",
]
