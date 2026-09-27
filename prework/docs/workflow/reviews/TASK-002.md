# TASK-002 Code Review

- task_id：TASK-002
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-data sha256:710b8f0f3ff152433d1fdd4d7f3fbb6654a549937d56cb4c1f73cd9de6fda57c
- Task／Spec 版本：TASK-002 / SPEC-001 v0.3
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，共 2 輪（第 1 輪發現 B-1，修正後第 2 輪通過）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：組合 sha256 `710b8f0f3ff152433d1fdd4d7f3fbb6654a549937d56cb4c1f73cd9de6fda57c`；個別檔案——`ediaad/__init__.py` `a8954ad8e3aa34b926ccb0e4256caa3db677f56f066476bce1c17f876138e970`、`ediaad/errors.py` `17d9c88869c6dc63cb35ddd776922f9b5e98a4ae7238f9a60516961a3094500a`、`ediaad/data.py` `c35f654e51309eeeb77a46658180db4d87067126e5abf88a1988668b8e0bfc1d`、`tests/test_data.py` `33db039f11ebfaf33d6ffc7b51565f01d5e57f243f9e9cf420529faee47f1082`、`pytest.ini` `22338d505ed33b851ae17526820cec8a2c30eb12e3e6244aad679dfb2c1fda9e`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對；本張新增 4 檔（`ediaad/__init__.py`、`ediaad/errors.py`、`ediaad/data.py`、`tests/test_data.py`）、新增 `pytest.ini`、修改 `docs/workflow/tasks/TASK-002.md`，並新增 TDD／Review 紀錄
- 納入的已提交、未提交、新增檔案：上述 5 個程式／測試／設定檔（本張交付物）＋ 本張 TDD 與 Review 紀錄
- 排除的既有修改及理由：`ocaievo/scripts/`、`ocaievo/requirements*.txt`、`.venv/` 屬 TASK-001 交付物（已於 TASK-001 審查）；`docs/workflow/` 其餘文件為規劃產物
- 程式規範來源：`docs/workflow/SPEC.md` 第 5 節（序列契約、模組責任、原則 1「計算不碰 I/O」、錯誤分層、輸入驗證與錯誤格式）、`docs/architecture/ENGINEERING-REPORT.md` 第 4.4／5 節與 F-001、`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-002 | `ediaad/data.py`（`load_csv`、`_build_series`、`_normalize_columns`）；`tests/test_data.py::test_load_csv_returns_series_contract`、`::test_load_csv_sorts_rows_by_time_and_keeps_values` | 符合 | — |
| AC-003 | `ediaad/data.py`（缺欄位／空資料列／非數值／時間解析／重複時間檢查與訊息）；`tests/test_data.py` 六個錯誤情境測試 | 符合 | — |
| AC-004 | `ediaad/data.py`（`from_rows` 與 `load_csv` 共用 `_build_series`）；`tests/test_data.py::test_from_rows_with_named_fields_matches_load_csv`、`::test_from_rows_accepts_sequence_rows_with_epoch_milliseconds`、`::test_csv_round_trip_is_transparent` | 符合 | B-1（已修正） |

逐條核對：

- **AC-002**：`list(series.columns) == SERIES_COLUMNS`、`str(time.dtype) == "datetime64[ns, UTC]"`、`is_monotonic_increasing`、`not duplicated().any()`、五個價格欄 `float64` 皆以斷言驗證；未排序輸入的 `close`／`volume` 序列證明排序保留值。符合。
- **AC-003**：五種壞輸入（缺欄位／空檔案／非數值／無法解析時間／重複時間）各自以 `pytest.raises(DataFormatError)` 驗證，缺欄位斷言訊息含欄位名 `volume`，非數值與壞時間斷言訊息含 `第 3 列`，重複斷言訊息含 `重複` 與時間字串。另補標頭-only 空檔與缺檔兩個防禦情境。符合；無多做未要求行為（未加入 Schema 驗證、未改變欄位集）。
- **AC-004**：`pd.testing.assert_frame_equal` 對「CSV 路徑」與「資料列路徑」的結果做完整框架相等（含 dtype、欄位順序、值）；`test_csv_round_trip_is_transparent` 對序列寫入 CSV 再讀回做相等比較，直接對應 F-001 的「快取往返後 dtype 改變」症狀；epoch 毫秒測試驗證數值時間戳仍收斂到 `datetime64[ns, UTC]`。符合（B-1 修正後）。
- 例外與錯誤契約符合 SPEC 第 5 節：所有輸入問題都是 `DataFormatError`（exit 2 對應），不外洩 `KeyError`／`EmptyDataError`／`ValueError`。

## 品質 Review

第 1 輪已檢查並發現 B-1；第 2 輪複查全部項目。

- **錯誤處理與錯誤契約**：第 1 輪發現 `from_rows(..., time_unit=...)` 在缺 `time` 欄位時丟 `KeyError`（B-1，blocking，已修正並補兩個回歸測試）。修正後重測：缺 `time` + `time_unit` → `DataFormatError('資料列：缺少必要欄位 time')`；無法以指定單位解讀 → `DataFormatError('資料列：時間無法解析（第 1 列）')`。未發現其他外洩。
- **輸入驗證與資料一致性**：必要欄位、空資料列、非數值、時間可解析性、重複時間都在**單一出口** `_build_series` 檢查，因此 `load_csv` 與 `from_rows` 不可能出現驗證分歧（這正是 B-1 的根因，已由「單一出口 + 不提前存取欄位」消除）。未發現問題。
- **資源釋放與副作用**：`load_csv` 只用 `pd.read_csv`（自行關檔）；模組不寫檔、不連網、不輸出訊息，符合 SPEC 第 5 節原則 1。未發現問題。
- **模組責任與公開介面**：`data.py` 只依賴 `errors.py` 與 pandas；`__all__` 明確列出五個公開名稱；未引入未使用的抽象。未發現問題。
- **命名與可讀性**：`_describe_positions`／`_build_series` 等名稱與參數（`header_lines`）說明了「列號如何計算」這個易錯點；錯誤訊息以「來源：問題（位置）」的一致格式呈現。未發現問題。
- **測試品質**：測試只透過公開介面觀察，不呼叫 private 函式；預期值來自手算與獨立產生的 CSV，不是重寫實作；`tmp_path` 隔離、無網路、無時間依賴（`TIME` 相關無 sleeping）。`test_error_message_truncates_many_bad_rows` 以 7 列驗證截斷，能辨認訊息退化成列出上百列的退化。未發現問題。
- **契約細節的一致性**：`TIME_UNIT`／`TIME_DTYPE` 由常數導出，測試以 f-string 對齊常數，避免測試與實作各寫一份 `ns`。未發現問題。
- **未實機驗證項**：無（本張全部為純計算，無外部依賴）。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| B-1 | 錯誤處理／AC-004 | **blocking** | `ediaad/data.py` `from_rows`：`time_unit` 不為 `None` 時直接存取 `frame[TIME_COLUMN]`。觸發情境：`from_rows([{...沒有 time...}], time_unit="ms")`。影響：丟出 `KeyError` 而非 `DataFormatError`，使兩條載入路徑的錯誤契約不一致，且 `KeyError` 會被監控迴圈當成「來源畸形資料」吞成 warning，掩蓋真正的輸入錯誤 | 只在 `time` 欄位存在時才轉換；轉換以 `try/except` 包住並轉為 `DataFormatError` | **已修正並驗證**：`c35f654e…`；回歸測試 `test_from_rows_with_time_unit_reports_missing_time_as_data_format_error`、`test_from_rows_reports_unusable_time_unit_as_data_format_error`；全套 `17 passed` |
| A-1 | 訊息一致性 | advisory | `load_csv` 的列號含表頭（CSV 第 N 列），`from_rows` 的列號不含表頭（第 N 列） | 已在 TDD 紀錄〈未執行或受阻〉明列此差異；兩者訊息都含來源識別，實務上不致混淆 | 延後（文件化即可；改為統一計數反而讓 CSV 使用者對不上檔案行號） |
| A-2 | 效能 | advisory | `load_csv` 以 `dtype=str` 全量載入再轉型，極大檔案（數百萬列）記憶體偏高 | 需要時改為分塊載入；目前最大情境為 10,000 根（AC-029），且快取為 CSV，無實際壓力 | 延後（本版無此資料量需求） |

## 修正與重審

- 第 1 輪：Spec Review 符合；品質 Review 發現 B-1（blocking）。
- 修正：修改 `from_rows` 的時間轉換條件與例外轉換（見上表）。過程中加入兩個回歸測試；首次執行時其中一個**測試斷言寫錯**（實作已回正確的 `DataFormatError`，斷言卻期待不同字串），已修正斷言而非放寬實作，並在 TDD 紀錄如實記載。
- 第 2 輪：重跑 `tests/test_data.py` 與全套 pytest → `17 passed in 0.40s`；重讀 `data.py` 全文複查錯誤路徑、欄位存取順序與訊息格式。Spec 與品質兩軸均通過，blocking 歸零。
- 舊版通過結論不沿用：本報告的 `checked_version` 指向修正後的檔案雜湊。

## 結果

- Spec Review：passed（AC-002／AC-003／AC-004 逐條符合；無漏做、無多做未要求行為）
- 品質 Review：passed（第 1 輪的 blocking 已修正並重驗；第 2 輪未再發現 blocking）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（列號計數差異已文件化）、A-2（無實際資料量壓力）
- 能否標為 done：**可以**
- 限制與未驗證事項：無未實機驗證項；大型 CSV 的串流載入與多來源錯誤彙總不在本張範圍
