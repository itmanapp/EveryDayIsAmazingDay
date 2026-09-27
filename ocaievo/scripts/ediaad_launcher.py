#!/usr/bin/env python3
"""ediaad 桌面一鍵啟動的薄入口（TASK-026）。

只做一件事：把命令列交給 `ediaad.launcher.main`。所有邏輯都在套件裡，讓測試可以直接
呼叫 `main(argv, opener=...)`（不必真的開瀏覽器），也讓 `python -m ediaad.launcher` 與
這個檔案走同一條路徑。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 直接執行 `scripts/ediaad_launcher.py` 時，專案根目錄不在 `sys.path` 上。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ediaad.launcher import main  # noqa: E402 - 必須先補 sys.path

if __name__ == "__main__":
    raise SystemExit(main())
