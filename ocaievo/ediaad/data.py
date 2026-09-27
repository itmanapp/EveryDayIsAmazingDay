"""序列（Series）契約與 CSV／資料列載入。

**序列契約**（見 `docs/workflow/SPEC.md` 第 5 節）：pandas DataFrame，欄位固定且順序
固定為 `time`／`open`／`high`／`low`／`close`／`volume`；`time` 為 UTC
`datetime64[ns]`、升冪、無重複；其餘五欄為 `float64`。

時間解析度明定為奈秒（`TIME_UNIT = "ns"`）不是任意選擇：報告的 F-001 缺陷是
「交易所路徑產生 ms、CSV 路徑產生 us」，同一份資料經快取往返後 dtype 改變。所有
進入序列的路徑（CSV 與資料列）都收斂到同一個 `_build_series`，因此兩個來源路徑
必然產出完全相同的結構。

錯誤一律為 `DataFormatError`，且訊息指出**缺少的欄位名**或**出錯的列號**，讓使用者
能直接修正資料；不吞掉錯誤、不產生 NaN 假資料。

本模組只做資料處理，不讀寫其他檔案、不連網、不輸出訊息（SPEC 第 5 節原則 1）。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from .errors import DataFormatError

__all__ = [
    "SERIES_COLUMNS",
    "PRICE_COLUMNS",
    "TIME_COLUMN",
    "TIME_UNIT",
    "load_csv",
    "from_rows",
]

SERIES_COLUMNS: tuple[str, ...] = ("time", "open", "high", "low", "close", "volume")
PRICE_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close", "volume")
TIME_COLUMN = "time"
TIME_UNIT = "ns"
TIME_DTYPE = f"datetime64[{TIME_UNIT}, UTC]"

_MAX_REPORTED_POSITIONS = 5


def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """欄位名去空白、轉小寫並移除 BOM，讓來源格式差異不影響契約。"""
    mapping = {
        column: str(column).strip().lower().lstrip("\ufeff") for column in frame.columns
    }
    return frame.rename(columns=mapping)  # type: ignore[arg-type]


def _describe_positions(positions: Sequence[int], *, header_lines: int) -> str:
    """把 0 基索引轉成使用者看得懂的列號字串（含表頭列）。"""
    lines = [str(index + header_lines + 1) for index in positions]
    shown = "、".join(lines[:_MAX_REPORTED_POSITIONS])
    if len(lines) > _MAX_REPORTED_POSITIONS:
        shown = f"{shown} 等 {len(lines)} 列"
        return f"第 {shown}"
    return f"第 {shown} 列"


def _build_series(
    frame: pd.DataFrame, *, source: str, header_lines: int
) -> pd.DataFrame:
    """把任意來源的資料框架收斂成序列契約（所有載入路徑的唯一出口）。"""
    frame = _normalize_columns(frame)

    missing = [column for column in SERIES_COLUMNS if column not in frame.columns]
    if missing:
        raise DataFormatError(f"{source}：缺少必要欄位 {', '.join(missing)}")

    if len(frame.index) == 0:
        raise DataFormatError(f"{source}：檔案為空或沒有可讀取的資料列")

    prices: dict[str, pd.Series] = {}
    for column in PRICE_COLUMNS:
        values = pd.to_numeric(frame[column], errors="coerce")
        invalid = values.isna().to_numpy().nonzero()[0]
        if len(invalid) > 0:
            raise DataFormatError(
                f"{source}：欄位 {column} 不是數值"
                f"（{_describe_positions(invalid.tolist(), header_lines=header_lines)}）"
            )
        prices[column] = values.astype("float64")

    stamps = pd.to_datetime(frame[TIME_COLUMN], utc=True, errors="coerce")
    if not isinstance(stamps, pd.Series):
        stamps = pd.Series(stamps, index=frame.index)
    unparsed = stamps.isna().to_numpy().nonzero()[0]
    if len(unparsed) > 0:
        raise DataFormatError(
            f"{source}：時間無法解析"
            f"（{_describe_positions(unparsed.tolist(), header_lines=header_lines)}）"
        )
    stamps = stamps.astype(TIME_DTYPE)

    duplicated = stamps.duplicated(keep=False)
    if duplicated.any():
        examples = (
            stamps[duplicated]
            .drop_duplicates()
            .dt.strftime("%Y-%m-%d %H:%M:%S%z")
            .head(3)
            .tolist()
        )
        raise DataFormatError(f"{source}：時間重複：{'、'.join(examples)}")

    result = pd.DataFrame({TIME_COLUMN: stamps.reset_index(drop=True), **{
        column: values.reset_index(drop=True) for column, values in prices.items()
    }})
    result = result.loc[:, list(SERIES_COLUMNS)]
    result = result.sort_values(TIME_COLUMN, kind="stable").reset_index(drop=True)
    return result


def load_csv(path: str | Path) -> pd.DataFrame:
    """讀入 OHLC CSV 並回傳符合序列契約的 DataFrame。

    處理順序：解碼（容忍 BOM）→ 欄位名正規化 → 驗證必要欄位 → 型別轉換 →
    時間轉 UTC 奈秒 → 檢查重複時間 → 依時間升冪排序。
    """
    csv_path = Path(path)
    if not csv_path.is_file():
        raise DataFormatError(f"CSV {csv_path}：找不到檔案")

    try:
        frame = pd.read_csv(
            csv_path,
            dtype=str,
            encoding="utf-8-sig",
            skipinitialspace=True,
            keep_default_na=False,
        )
    except pd.errors.EmptyDataError as error:
        raise DataFormatError(f"CSV {csv_path}：檔案為空或沒有可讀取的資料列") from error
    except pd.errors.ParserError as error:
        raise DataFormatError(f"CSV {csv_path}：無法解析 CSV：{error}") from error

    return _build_series(frame, source=f"CSV {csv_path}", header_lines=1)


def from_rows(
    rows: Iterable[Mapping[str, Any] | Sequence[Any]],
    columns: Sequence[str] = SERIES_COLUMNS,
    *,
    time_unit: str | None = None,
) -> pd.DataFrame:
    """由外部資料列建立序列，套用與 `load_csv` **完全相同**的驗證與結構。

    `rows` 可以是字典序列（例如交易所回傳的具名欄位）或序列序列（例如 K 線陣列），
    後者以 `columns` 指名欄位。`time_unit` 用於數值型時間戳（例如 Binance 的毫秒
    epoch），傳入 `"ms"` 等單位讓 pandas 正確解讀。
    """
    records = list(rows)
    if not records:
        raise DataFormatError("資料列：檔案為空或沒有可讀取的資料列")

    if isinstance(records[0], Mapping):
        frame = pd.DataFrame.from_records([dict(record) for record in records])
    else:
        frame = pd.DataFrame.from_records(records, columns=list(columns))

    if time_unit is not None and TIME_COLUMN in frame.columns:
        frame = frame.copy()
        try:
            frame[TIME_COLUMN] = pd.to_datetime(
                frame[TIME_COLUMN], unit=time_unit, utc=True, errors="coerce"
            )
        except (TypeError, ValueError) as error:
            raise DataFormatError(
                f"資料列：時間欄無法以單位 {time_unit!r} 解讀：{error}"
            ) from error

    return _build_series(frame, source="資料列", header_lines=0)
