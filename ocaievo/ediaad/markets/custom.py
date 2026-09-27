"""自訂 CSV 來源：把使用者提供的 CSV 檔當成資料來源（AC-037）。

序列的解析**完全沿用 `data.load_csv`**，因此欄位順序、dtype、時間排序與
`DataFormatError` 行為與其他載入路徑逐字相同——不另寫一套解析（報告 F-001 的教訓：
同一份資料經不同路徑產生不同結構）。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..data import load_csv
from ..errors import ConfigError, SourceError
from .base import INTERVAL_ORDER, Instrument, register

__all__ = ["CsvSource"]


class CsvSource:
    """以 `<root>/<symbol>_<interval>.csv` 為來源。

    `root` 可在建構時指定，或於 `fetch` 時以 `root=` 逐次指定；兩者皆無時 `fetch` 丟出
    `ConfigError`（設定問題），檔案不存在則丟出 `SourceError`（來源失敗），沿用 CLI 的
    exit code 分層（SPEC 第 5 節）。
    """

    id = "csv"
    display_name = "自訂 CSV 檔"
    supported_intervals = INTERVAL_ORDER
    needs_api_key = False

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else None

    def search(self, query: str, limit: int = 20) -> list[Instrument]:
        """自訂 CSV 沒有商品目錄可查，因此把使用者輸入當成商品代號回傳單筆結果。

        空字串（或只有空白）與 `limit < 1` 一律回傳空清單。回傳的 `Instrument.interval`
        為空字串——CSV 檔本身沒有預設週期，由使用者在設定中指定。
        """
        text = query.strip()
        if not text or limit < 1:
            return []
        return [
            Instrument(symbol=text, interval="", source_id=self.id, display_name=text)
        ]

    def fetch(
        self,
        symbol: str,
        interval: str,
        root: str | Path | None = None,
        *,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """讀取 `<root>/<symbol>_<interval>.csv`，解析完全交給 `data.load_csv`。

        `limit` 的語意與其他來源一致（取最近 N 根）；`None` 表示全部。
        """
        directory = Path(root) if root is not None else self.root
        if directory is None:
            raise ConfigError(
                "CSV 來源需要目錄：請以 CsvSource(root) 或 fetch(..., root=...) 指定"
            )
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
            raise ConfigError(f"limit 必須是 >= 1 的整數或 None，收到 {limit!r}")

        path = directory / f"{symbol}_{interval}.csv"
        if not path.is_file():
            raise SourceError(f"找不到 CSV 檔：{path}")
        series = load_csv(path)
        if limit is not None and len(series) > limit:
            series = series.iloc[-limit:].reset_index(drop=True)
        return series



register(CsvSource())
