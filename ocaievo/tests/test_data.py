"""`ediaad.data` 的公開契約測試（TASK-002）。

觀察邊界：只呼叫 `ediaad.data.load_csv`／`from_rows` 與公開常數
`SERIES_COLUMNS`／`PRICE_COLUMNS`／`TIME_UNIT`；不觸碰 private 函式。
所有測試使用 `tmp_path`，離線可跑。
"""

from __future__ import annotations

import pandas as pd
import pytest

from ediaad.data import (
    PRICE_COLUMNS,
    SERIES_COLUMNS,
    TIME_UNIT,
    from_rows,
    load_csv,
)
from ediaad.errors import DataFormatError

HEADER = "time,open,high,low,close,volume\n"


def write_csv(tmp_path, body: str, name: str = "ohlcv.csv"):
    path = tmp_path / name
    path.write_text(HEADER + body, encoding="utf-8")
    return path


# ---- AC-002：合法 CSV → 序列契約 -------------------------------------------


def test_load_csv_returns_series_contract(tmp_path):
    body = (
        "2024-01-01T00:00:00Z,100,110,90,105,1000\n"
        "2024-01-01T01:00:00Z,105,115,100,112,1200\n"
    )

    series = load_csv(write_csv(tmp_path, body))

    assert list(series.columns) == list(SERIES_COLUMNS)
    assert str(series["time"].dtype) == f"datetime64[{TIME_UNIT}, UTC]"
    assert series["time"].is_monotonic_increasing
    assert not series["time"].duplicated().any()
    for column in PRICE_COLUMNS:
        assert series[column].dtype == "float64", column
    assert len(series) == 2


def test_load_csv_sorts_rows_by_time_and_keeps_values(tmp_path):
    body = (
        "2024-01-01T02:00:00Z,120,130,110,125,900\n"
        "2024-01-01T00:00:00Z,100,110,90,105,1000\n"
        "2024-01-01T01:00:00Z,105,115,100,112,1200\n"
    )

    series = load_csv(write_csv(tmp_path, body))

    assert series["close"].tolist() == [105.0, 112.0, 125.0]
    assert series["volume"].tolist() == [1000.0, 1200.0, 900.0]
    assert series["time"].is_monotonic_increasing


# ---- AC-003：五種壞輸入 → DataFormatError 且指出問題 ------------------------


def test_missing_column_reports_the_missing_name(tmp_path):
    path = tmp_path / "missing_column.csv"
    path.write_text(
        "time,open,high,low,close\n2024-01-01T00:00:00Z,100,110,90,105\n",
        encoding="utf-8",
    )

    with pytest.raises(DataFormatError) as error:
        load_csv(path)

    assert "volume" in str(error.value)


def test_empty_file_is_rejected(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")

    with pytest.raises(DataFormatError):
        load_csv(path)


def test_header_only_file_is_rejected(tmp_path):
    with pytest.raises(DataFormatError) as error:
        load_csv(write_csv(tmp_path, ""))

    assert "空" in str(error.value) or "沒有" in str(error.value)


def test_non_numeric_price_reports_csv_line_number(tmp_path):
    body = (
        "2024-01-01T00:00:00Z,100,110,90,105,1000\n"
        "2024-01-01T01:00:00Z,105,abc,100,112,1200\n"
    )

    with pytest.raises(DataFormatError) as error:
        load_csv(write_csv(tmp_path, body))

    message = str(error.value)
    assert "第 3 列" in message
    assert "high" in message


def test_unparseable_time_reports_csv_line_number(tmp_path):
    body = (
        "2024-01-01T00:00:00Z,100,110,90,105,1000\n"
        "not-a-time,105,115,100,112,1200\n"
    )

    with pytest.raises(DataFormatError) as error:
        load_csv(write_csv(tmp_path, body))

    assert "第 3 列" in str(error.value)


def test_duplicate_timestamps_are_rejected(tmp_path):
    body = (
        "2024-01-01T00:00:00Z,100,110,90,105,1000\n"
        "2024-01-01T00:00:00Z,105,115,100,112,1200\n"
    )

    with pytest.raises(DataFormatError) as error:
        load_csv(write_csv(tmp_path, body))

    message = str(error.value)
    assert "重複" in message
    assert "2024-01-01" in message


# ---- AC-004：來源一致性與快取透明（F-001 回歸）-----------------------------

CONSISTENT_BODY = (
    "2024-01-01T00:00:00Z,100,110,90,105,1000\n"
    "2024-01-01T01:00:00Z,105,115,100,112,1200\n"
    "2024-01-01T02:00:00Z,112,120,108,118,950\n"
)


def test_from_rows_with_named_fields_matches_load_csv(tmp_path):
    from_csv = load_csv(write_csv(tmp_path, CONSISTENT_BODY))
    from_records = from_rows(
        [
            {
                "time": "2024-01-01T00:00:00Z",
                "open": "100",
                "high": "110",
                "low": "90",
                "close": "105",
                "volume": "1000",
            },
            {
                "time": "2024-01-01T01:00:00Z",
                "open": "105",
                "high": "115",
                "low": "100",
                "close": "112",
                "volume": "1200",
            },
            {
                "time": "2024-01-01T02:00:00Z",
                "open": "112",
                "high": "120",
                "low": "108",
                "close": "118",
                "volume": "950",
            },
        ]
    )

    pd.testing.assert_frame_equal(from_csv, from_records)


def test_from_rows_accepts_sequence_rows_with_epoch_milliseconds():
    series = from_rows(
        [
            [1704067200000, "100", "110", "90", "105", "1000"],
            [1704070800000, "105", "115", "100", "112", "1200"],
        ],
        time_unit="ms",
    )

    assert str(series["time"].dtype) == f"datetime64[{TIME_UNIT}, UTC]"
    assert series["time"].iloc[0] == pd.Timestamp("2024-01-01T00:00:00Z")
    assert series["close"].tolist() == [105.0, 112.0]
    assert series["open"].dtype == "float64"


def test_csv_round_trip_is_transparent(tmp_path):
    series = load_csv(write_csv(tmp_path, CONSISTENT_BODY))
    cache = tmp_path / "cache" / "BTCUSDT_1h.csv"
    cache.parent.mkdir(parents=True, exist_ok=True)
    series.to_csv(cache, index=False)

    reloaded = load_csv(cache)

    pd.testing.assert_frame_equal(series, reloaded)
    assert str(reloaded["time"].dtype) == str(series["time"].dtype)


# ---- 載入穩健性：BOM、欄位名正規化、時區與訊息截斷（既有覆蓋）--------------


def test_load_csv_tolerates_bom_and_messy_column_names(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text(
        "\ufeff Time , OPEN ,High,Low,Close,Volume\n"
        "2024-01-01T00:00:00Z,100,110,90,105,1000\n",
        encoding="utf-8",
    )

    series = load_csv(path)

    assert list(series.columns) == list(SERIES_COLUMNS)
    assert series["open"].tolist() == [100.0]


def test_load_csv_converts_offset_timestamps_to_utc(tmp_path):
    path = tmp_path / "offset.csv"
    path.write_text(
        "time,open,high,low,close,volume\n"
        "2024-01-01T08:00:00+08:00,100,110,90,105,1000\n",
        encoding="utf-8",
    )

    series = load_csv(path)

    assert series["time"].iloc[0] == pd.Timestamp("2024-01-01T00:00:00Z")
    assert str(series["time"].dtype) == f"datetime64[{TIME_UNIT}, UTC]"


def test_error_message_truncates_many_bad_rows(tmp_path):
    body = "".join(
        f"2024-01-0{day}T00:00:00Z,x,110,90,105,1000\n" for day in range(1, 8)
    )
    path = tmp_path / "multi_bad.csv"
    path.write_text("time,open,high,low,close,volume\n" + body, encoding="utf-8")

    with pytest.raises(DataFormatError) as error:
        load_csv(path)

    message = str(error.value)
    assert "第 2、3、4、5、6 等 7 列" in message
    assert "open" in message


def test_missing_file_is_reported_as_data_format_error(tmp_path):
    with pytest.raises(DataFormatError) as error:
        load_csv(tmp_path / "does_not_exist.csv")

    assert "找不到檔案" in str(error.value)


# ---- B-1 回歸：from_rows 的錯誤契約必須與 load_csv 一致 ---------------------


def test_from_rows_with_time_unit_reports_missing_time_as_data_format_error():
    """B-1 回歸：指定 time_unit 但缺 time 欄位時，必須是 DataFormatError（非 KeyError）。"""
    with pytest.raises(DataFormatError) as error:
        from_rows(
            [{"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}],
            time_unit="ms",
        )

    assert "time" in str(error.value)


def test_from_rows_reports_unusable_time_unit_as_data_format_error():
    with pytest.raises(DataFormatError) as error:
        from_rows(
            [{"time": "not-a-number", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}],
            time_unit="ms",
        )

    # pandas 以 errors="coerce" 把無法解讀的值轉為 NaT，因此走「時間無法解析」路徑；
    # 重點是錯誤型別仍在領域例外階層內，不會外洩 ValueError 或 NaT 假資料。
    assert "時間" in str(error.value) or "time_unit" in str(error.value)
