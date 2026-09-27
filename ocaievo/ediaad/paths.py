"""`$EDIAAD_HOME` 與各產物路徑的**單一解析點**。

先前 `default_home()`／`keys_path()` 住在 `markets/us.py`（TASK-016）。當 `config.py`
（TASK-019）與 `app.py`（TASK-020）也需要同一組路徑時，共用一個中立模組比讓兩個模組都
匯入某個市場來源模組乾淨——`paths` 不依賴任何其他 `ediaad` 模組。

產物位置對應 SPEC 第 5 節「資料生命週期」（`$EDIAAD_HOME/`）：`ediaad.db`、`lease.json`、
`keys.json`、`settings.json`、`watchlist.json`、`catalog.json`、`update.json`、
`ediaad.pid`。
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "DEFAULT_HOME_PARTS",
    "HOME_ENV",
    "catalog_path",
    "db_path",
    "default_home",
    "home_root",
    "high_water_path",
    "keys_path",
    "lease_path",
    "pid_path",
    "revoked_path",
    "settings_path",
    "update_state_path",
    "watchlist_path",
]

HOME_ENV = "EDIAAD_HOME"
#: 未設定 `EDIAAD_HOME` 時，資料根目錄為 `~/.local/share/ediaad`。
DEFAULT_HOME_PARTS: tuple[str, ...] = (".local", "share", "ediaad")


def default_home() -> Path:
    """資料根目錄：`$EDIAAD_HOME`，未設定（或只有空白）時為 `~/.local/share/ediaad`。"""
    from_env = os.environ.get(HOME_ENV)
    if from_env and from_env.strip():
        return Path(from_env.strip()).expanduser()
    return Path.home().joinpath(*DEFAULT_HOME_PARTS)


def home_root(home: str | Path | None = None) -> Path:
    """解析呼叫端提供的 home；`None` 表示用 `default_home()`。"""
    return Path(home).expanduser() if home is not None else default_home()


def keys_path(home: str | Path | None = None) -> Path:
    return home_root(home) / "keys.json"


def settings_path(home: str | Path | None = None) -> Path:
    return home_root(home) / "settings.json"


def watchlist_path(home: str | Path | None = None) -> Path:
    """監控清單位置（`monitor.load_config` 讀的檔案）。"""
    return home_root(home) / "watchlist.json"


def db_path(home: str | Path | None = None) -> Path:
    return home_root(home) / "ediaad.db"


def lease_path(home: str | Path | None = None) -> Path:
    """租約位置（TASK-030：啟用後落地、每次啟動離線驗證）。"""
    return home_root(home) / "lease.json"


def high_water_path(home: str | Path | None = None) -> Path:
    """時鐘水位位置（TASK-030 的第二層時鐘防護；可被刪檔繞過，見報告第 6.4 節）。"""
    return home_root(home) / "high_water.json"


def revoked_path(home: str | Path | None = None) -> Path:
    """撤銷標記位置（TASK-031：被撤銷的密鑰不再被接受）。"""
    return home_root(home) / "revoked.json"


def pid_path(home: str | Path | None = None) -> Path:
    """啟動器的 PID 檔位置（AC-049 的重複啟動防護與 AC-050 的關閉依據）。"""
    return home_root(home) / "ediaad.pid"


def catalog_path(home: str | Path | None = None) -> Path:
    return home_root(home) / "catalog.json"


def update_state_path(home: str | Path | None = None) -> Path:
    """更新檢查快取位置（TASK-032：manifest 的顯示欄位與上次檢查時間）。"""
    return home_root(home) / "update.json"
