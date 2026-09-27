# TASK-002 測試紀錄

- task_id：TASK-002
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-data sha256:710b8f0f3ff152433d1fdd4d7f3fbb6654a549937d56cb4c1f73cd9de6fda57c
- alternative_reason：無（本張為程式任務，四個 Cycle 都有可先寫而失敗的行為）
- Task／Spec 版本：TASK-002 / SPEC-001 v0.3
- 測試邊界：只呼叫 `ediaad.data.load_csv`／`from_rows` 與公開常數 `SERIES_COLUMNS`／`PRICE_COLUMNS`／`TIME_UNIT`；不觸碰 private 函式。測試資料以 `tmp_path` 產生 CSV 與資料列，全程離線。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001 的環境（`.venv`，numpy 2.5.3／pandas 3.0.6／pytest 9.1.1），但沒有 `ediaad/` 套件；基準為 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## Cycle 1：合法 CSV 的序列契約與排序（AC-002）

- AC 與預期行為：合法 OHLC CSV → 欄位順序固定、`time` 為 UTC `datetime64[ns]` 且升冪無重複、其餘五欄 `float64`；輸入未排序時輸出依時間升冪且值不變。
- 測試檔案／案例：`tests/test_data.py::test_load_csv_returns_series_contract`、`::test_load_csv_sorts_rows_by_time_and_keeps_values`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_data.py -q` | 2 | `E ModuleNotFoundError: No module named 'ediaad'`；`1 error in 0.41s`（收集期失敗） | 尚未有 `ediaad/`／2026-09-24 |
| Green | 同上 | 0 | `2 passed in 0.30s` | snap-2026-09-24-ocaievo-data／2026-09-24 |

- Red 確實因目標行為失敗的解釋：測試匯入尚不存在的 `ediaad.data`，失敗來自目標模組未實作，不是工具或環境問題（`.venv` 與 pytest 已在 TASK-001 驗證可用）。
- 最小實作摘要：`ediaad/__init__.py`（`__version__`）、`ediaad/errors.py`（例外階層）、`ediaad/data.py`（常數、`load_csv` 與共用的 `_build_series` 骨架：欄位正規化 → 型別轉換 → 時間轉 UTC 奈秒 → 排序）。

## Cycle 2：五種壞輸入的錯誤回報（AC-003）

- AC 與預期行為：缺欄位、空檔案、非數值、無法解析的時間、重複時間戳 → `DataFormatError`，且訊息指出缺少的欄位名或出錯的列號。
- 測試檔案／案例：`tests/test_data.py` 的 `test_missing_column_reports_the_missing_name`、`test_empty_file_is_rejected`、`test_header_only_file_is_rejected`、`test_non_numeric_price_reports_csv_line_number`、`test_unparseable_time_reports_csv_line_number`、`test_duplicate_timestamps_are_rejected`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_data.py -q` | 1 | `6 failed, 2 passed`：`KeyError`（缺欄位）、`pandas.errors.EmptyDataError`（空檔）、4 個 `Failed: DID NOT RAISE DataFormatError`（非數值／壞時間／重複時間被靜默轉成 NaN／NaT，標頭-only 檔被當成合法空序列） | 同上／2026-09-24 |
| Green | 同上 | 0 | `8 passed in 0.33s` | 同上／2026-09-24 |

- Red 確實因目標行為失敗的解釋：六個失敗全部是「驗證尚未實作」的直接後果——三種壞資料被 `errors="coerce"` 靜默轉成 NaN／NaT（正是最危險的假資料），另兩種錯誤型別外洩成 `KeyError`／`EmptyDataError`。不是拼字或工具問題。
- 最小實作摘要：`_build_series` 加入必要欄位檢查、空資料列檢查、逐欄非數值偵測（附 CSV 列號）、時間解析偵測與重複時間檢查；`load_csv` 攔截 `EmptyDataError`／`ParserError` 並轉為領域錯誤，且缺檔時明確回報。

## Cycle 3：來源一致性與快取透明（AC-004）

- AC 與預期行為：`from_rows` 與 `load_csv` 對同一份資料產出完全相同的結構與值；序列寫入快取再讀回完全相同（F-001 回歸）；`from_rows` 支援 epoch 毫秒。
- 測試檔案／案例：`test_from_rows_with_named_fields_matches_load_csv`、`test_from_rows_accepts_sequence_rows_with_epoch_milliseconds`、`test_csv_round_trip_is_transparent`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| 既有覆蓋（非 Red） | `.venv/bin/python -m pytest tests/test_data.py -q` | 1 → 0 | 首次執行 `2 failed, 9 passed`，兩個失敗都是 `NameError: name 'from_rows' is not defined`（**測試檔漏了 import**，屬測試缺陷，不是行為 Red，不作為 TDD 證據）；修正 import 後 `11 passed` | snap-2026-09-24-ocaievo-data／2026-09-24 |

- 如實說明（依 `references/tdd.md`「若測試一開始就是綠，確認行為是否已存在……如實記為既有覆蓋，不捏造 Red」）：
  - `from_rows` 與快取往返的行為，在 **Cycle 2 的同一次編輯**中就因為「兩條路徑共用唯一的 `_build_series` 出口」而一併實作完成（這正是 F-001 的結構性修法）。因此本 Cycle 的三個測試在修正測試檔 import 後**立即通過**，記為**既有覆蓋**，不宣稱有 Red。
  - `test_csv_round_trip_is_transparent` 是 F-001 的直接回歸測試（同一份資料經 CSV 往返後 dtype 與值不變），即使沒有 Red 也保留，因為它鎖住最重要的契約。
- 最小實作摘要：`from_rows`（支援具名欄位與序列列、`time_unit` 數值時間戳）與 `load_csv` 共用 `_build_series`。

## Cycle 4：載入穩健性（既有覆蓋）

- 預期行為：BOM 容忍與欄位名正規化（去空白、轉小寫、去 BOM）、帶時區位移的時間轉 UTC、多列錯誤訊息的截斷、缺檔回報。
- 測試檔案／案例：`test_load_csv_tolerates_bom_and_messy_column_names`、`test_load_csv_converts_offset_timestamps_to_utc`、`test_error_message_truncates_many_bad_rows`、`test_missing_file_is_reported_as_data_format_error`。
- 歷程：先以一次性腳本實測這些行為（BOM＋`" Time "`／`" OPEN "` → 契約欄位；`+08:00` → `2024-01-01 00:00:00+00:00`；7 列非數值 → `第 2、3、4、5、6 等 7 列`；缺檔 → `找不到檔案`），確認正確後才寫成測試鎖定。因為行為已存在，記為**既有覆蓋**，不捏造 Red。

## Review 修正：B-1（blocking）

- 發現：品質 Review 時以一次性腳本實測 `from_rows(..., time_unit="ms")` 遇到缺少 `time` 欄位的資料列，得到 `KeyError: 'time'` 而非 `DataFormatError`，使錯誤契約在兩條載入路徑間不一致（違反 AC-004 的「完全相同驗證」）。
- 修正：`from_rows` 只在 `time` 欄位存在時才做 `time_unit` 轉換（缺少時交由 `_build_series` 回報缺欄位），並以 `try/except` 包住轉換、把 `TypeError`／`ValueError` 轉為 `DataFormatError`。
- 回歸測試：`test_from_rows_with_time_unit_reports_missing_time_as_data_format_error`、`test_from_rows_reports_unusable_time_unit_as_data_format_error`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest -q`（加入 B-1 回歸測試後） | 1 | `1 failed, 16 passed`：失敗原因是**測試斷言寫錯**（實作已正確回 `DataFormatError('資料列：時間無法解析（第 1 列）')`，斷言卻期待 `時間欄`）；已修正斷言，非放寬實作 | 同上／2026-09-24 |
| Green | `.venv/bin/python -m pytest -q` | 0 | `17 passed in 0.40s` | 最終版 snap-2026-09-24-ocaievo-data sha256:710b8f0f3ff152433d1fdd4d7f3fbb6654a549937d56cb4c1f73cd9de6fda57c／2026-09-24 |

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit code | 版本／證據位置 |
| --- | --- | --- | --- |
| B-1 修正後全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`17 passed in 0.40s`） | 最終版 checked_version |
| 單檔（本張公開邊界） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_data.py -q` | 0（`17 passed`） | 同上 |
| F-001 回歸（快取往返透明） | 同上（`test_csv_round_trip_is_transparent`） | 通過 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 未涵蓋且刻意不做：多檔案／多來源的錯誤彙總、進度回報、大型 CSV 的串流載入（本張為單一檔案載入，`AC-002`～`AC-004` 未要求；大型檔案以 pandas 既有實作處理）。
- 已知限制：`from_rows` 的列號以「資料列（不含表頭）」計數，`load_csv` 以「CSV 列（含表頭）」計數；兩者訊息都明確標示來源（`CSV <path>`／`資料列`）。
