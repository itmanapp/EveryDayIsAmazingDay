# TASK-002：OHLC 序列契約、CSV 與資料列載入及錯誤回報

- id：TASK-002
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-002","AC-003","AC-004"]
- depends_on：["TASK-001"]
- test_evidence：["docs/workflow/tdd/TASK-002.md"]
- review_evidence：["docs/workflow/reviews/TASK-002.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`ediaad.data.load_csv(path)` 對一份合法 OHLC CSV 回傳符合 Series 契約的 DataFrame（欄位與順序固定為 `time`、`open`、`high`、`low`、`close`、`volume`，`time` 為 UTC `datetime64[ns]`、升冪、無重複，其餘五欄為 float64）；`ediaad.data.from_rows(rows)` 對同一份資料的資料列形式回傳 dtype 與值完全相同的 Series；兩條路徑互換、以及寫成 CSV 再讀回（快取往返）後仍完全相同；五種壞輸入各自丟出 `DataFormatError`，訊息指出哪個欄位或哪一列出錯。
- 本張不做：不做特徵抽取、相似度或規律運算；不實作來源層的快取策略（`<cache_dir>/<symbol>_<interval>.csv` 由後續來源任務負責）；不實作 `Source` 介面與 registry；不做商品搜尋或交易日曆；不引入 `pandas`／`numpy` 以外的解析依賴；不做 CLI、不做網頁。
- 每個 AC 在本張負責的範圍：AC-002 全部（欄位與順序、UTC `datetime64[ns]`、升冪、無重複、float64）；AC-003 全部（缺欄位、空檔案、非數值、時間無法解析、重複時間戳五種壞輸入的 `DataFormatError`，且訊息可定位）；AC-004 全部（`load_csv` 與 `from_rows` 同構、快取往返後 dtype 與值不變，即 F-001 回歸）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-002～AC-004、第 4 節、第 5 節「模組責任與邊界」原則 1 與 3、第 5 節「Series」資料契約與「輸入／輸出、驗證與錯誤格式」中 `load_csv` 的驗證順序（解碼容忍 BOM → 欄位名正規化 → 必要欄位齊全 → 型別可轉換 → 時間可解析並轉 UTC `ns` → 無重複時間 → 依時間升冪排序）、第 6 節「可重現性」、第 7 節測試策略第 2 列；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F2、第 4.1 節原則 1 與 3、第 4.3 節 `errors.py`／`data.py`、第 4.4 節「Series」（F-001：ms 與 us 混用導致快取不透明）；`docs/workflow/CONTEXT.md`「序列（Series）」；`docs/workflow/adr/ADR-001.md`（從零重建，不沿用 v0.2 程式碼）。
- 模組與公開介面：新增 `ediaad/errors.py`（`EdiaadError` 為基底，`DataFormatError`、`ConfigError`、`SourceError` 為子類；本張只用到前兩者，四個一次定義以免後續任務反覆改同一檔）與 `ediaad/data.py`（`SERIES_COLUMNS`、`PRICE_COLUMNS`、`TIME_UNIT`、`load_csv(path)`、`from_rows(rows)`）。`load_csv` 與 `from_rows` 必須共用同一份欄位正規化、型別轉換與時間處理實作，讓契約只有一個來源；`TIME_UNIT` 明示解析度為 `ns`。
- 預計觸及的檔案：`ediaad/__init__.py`、`ediaad/errors.py`、`ediaad/data.py`、`requirements.txt`、`tests/test_data.py`（必要時 `tests/conftest.py` 放共用合成序列夾具）；實作前重新查證（`ediaad/` 套件目錄由本張首次建立）。
- 必要環境／依賴：TASK-001 建立的 `.venv`（Python 3.12.3、`numpy`、`pandas`、`pytest`）；測試全程離線，資料以 `tmp_path` 合成；不需要網路、`sudo`、`curl` 或系統套件。

## 測試計畫

- 測試公開邊界：只呼叫 `ediaad.data.load_csv` 與 `ediaad.data.from_rows`，並觀察回傳值的 `columns`、`dtypes`、`is_monotonic_increasing`、`duplicated()` 與逐格值；不呼叫私有輔助函式，也不斷言內部實作方式。
- 第一個失敗行為與預期斷言：`ediaad/data.py` 尚未存在時，於專案根執行 `.venv/bin/python -m pytest tests/test_data.py -q` 預期以 collection error 失敗（`ModuleNotFoundError: No module named 'ediaad.data'`）；實作後同一個測試的第一個綠燈斷言為 `list(series.columns) == list(SERIES_COLUMNS)`、`str(series["time"].dtype) == "datetime64[ns, UTC]"`，且 `series["time"].duplicated().any()` 為 False。
- 後續例外／邊界情境：五種壞輸入各自 `pytest.raises(DataFormatError)` 並以 `match=` 斷言訊息含出錯欄位名（缺欄位）或列號（非數值、時間無法解析、重複時間戳）；空檔案（0 bytes）與「只有標題列、無資料列」兩種都要涵蓋；標題含 UTF-8 BOM、前後空白與大小寫混用時需被正規化為固定欄位名；輸入時間為亂序時需升冪排序、含時區資訊時需轉為 UTC 且 dtype 仍為 ns。快取往返：把 `load_csv` 的結果寫回 CSV 再由 `load_csv` 讀取，斷言 `dtypes` 逐欄相等且 `pandas.testing.assert_frame_equal` 通過（F-001 回歸）。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_data.py -q`；相關回歸為專案根執行 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的執行指令表。
- 非程式任務的替代驗證與理由：不適用（本張為程式任務，所有行為都能在公開函式介面上以 pytest 斷言，無需替代驗證）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工時 `ocaievo/` 已有 TASK-001 的環境建置產物（`scripts/bootstrap_env.py`、`requirements*.txt`、`.venv/`），本次新增 `ediaad/`、`tests/` 與 `pytest.ini`（開工時以 `find . -type f -not -path "./.venv/*" | sort` 與逐檔 sha256 建立快照；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（預計 `docs/workflow/tdd/TASK-002.md`）
- Review 紀錄位置：見上方 review_evidence（預計 `docs/workflow/reviews/TASK-002.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-data` sha256:710b8f0f3ff152433d1fdd4d7f3fbb6654a549937d56cb4c1f73cd9de6fda57c（`ediaad/__init__.py`、`ediaad/errors.py`、`ediaad/data.py`、`tests/test_data.py`、`pytest.ini`）；全套 `17 passed`
- 取消、重開或變更原因：無
