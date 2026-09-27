"""ediaad 的共用例外階層。

對應 CLI 的 exit code（見 `docs/workflow/SPEC.md` 第 5 節「錯誤分層」）：

- `DataFormatError`：輸入資料格式或內容不合法 → exit 2
- `ConfigError`：設定、參數或規格不合法 → exit 2
- `SourceError`：外部來源取得失敗 → exit 1

監控迴圈只攔截這一組領域錯誤（加上來源轉接器回傳畸形資料框架時的
`KeyError`／`IndexError`）；其他例外一律向上拋出，避免程式缺陷被 warning 掩蓋。
"""

from __future__ import annotations

__all__ = ["EdiaadError", "DataFormatError", "ConfigError", "SourceError"]


class EdiaadError(Exception):
    """所有可預期錯誤的父類別。"""


class DataFormatError(EdiaadError):
    """輸入資料（CSV、資料列、外部回應）格式或內容不合法。"""


class ConfigError(EdiaadError):
    """設定檔、參數或規格不合法。"""


class SourceError(EdiaadError):
    """外部資料來源取得失敗（網路、回應格式或快取狀態）。"""
