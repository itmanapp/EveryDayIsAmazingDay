# TASK-012：Source 介面、registry 與自訂 CSV 來源

- id：TASK-012
- type：refactor
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-030","AC-037"]
- depends_on：["TASK-002"]
- test_evidence：["docs/workflow/tdd/TASK-012.md"]
- review_evidence：["docs/workflow/reviews/TASK-012.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`from ediaad.markets.base import all_sources, get_source, register` 可用；`get_source("csv")` 回傳的來源物件具備 `id`、`display_name`、`supported_intervals`、`needs_api_key`、`search`、`fetch` 六項；`all_sources()` 列出已註冊來源，查詢未註冊的 id 時得到可讀錯誤（訊息含查詢的 id 與可用 id）；對來源不支援的週期（例如對只支援日線的來源要求 `1h`）提出可讀錯誤；`ediaad/monitor.py` 不再以全域 `ALLOWED_INTERVALS` 作為週期驗證的唯一依據，改為查 `get_source(source_id).supported_intervals`，使設定驗證的錯誤訊息指出出錯的來源與週期。以自訂 CSV 來源取得序列時，沿用 `data.load_csv` 完全相同的欄位順序、dtype、排序契約與 `DataFormatError` 行為。
- 本張不做：不實作 Binance、TWSE、Twelve Data 三個來源（分別為 TASK-013、TASK-014、TASK-016），也不在本張宣稱四個來源已齊備；**不重建報告第 4.3 節的 `ediaad/sources/` 舊介面（`OHLCVClient`）**，理由見 SPEC 第 5 節「相容性／遷移」與 ADR-001（從零重建、無需相容的呼叫端）；不建立版本化 catalog 與更新攜帶（TASK-017）；不新增 catalog schema 的下載或版本比對邏輯；不改變 `load_config` 的鍵集、`Watchlist` 欄位或既有錯誤語意（只把週期檢查的資料來源由全域常數換成 registry 查詢）；不執行 git 或任何對外動作。
- 每個 AC 在本張負責的範圍：AC-030 的介面與 registry 機制（`Source` 協定六欄位、`register`／`get_source`／`all_sources`、依來源查 `supported_intervals`、移除全域 `ALLOWED_INTERVALS` 作為唯一依據、不支援週期的可讀錯誤），四個來源各自的實作與週期清單由 TASK-013／TASK-014／TASK-016 補齊，四來源齊備的整體斷言留待 TASK-037 整合驗收；AC-037 全部（自訂 CSV 來源沿用 `load_csv` 的契約與錯誤行為）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-030、AC-037、第 5 節模組表的 `ediaad/markets/base.py`（`Source`、`Instrument`、`register`、`get_source`、`all_sources`）、同節「輸入／輸出、驗證與錯誤格式」與「相容性／遷移」（不重建 `ediaad/sources/` 的理由）；`docs/architecture/ENGINEERING-REPORT.md` 第 7.1 節（`Source` 介面與廢除全域 `ALLOWED_INTERVALS` 的連帶影響）、第 7.2 節（`markets/` 目錄清單）、第 4.3 節模組清單；`docs/workflow/adr/ADR-001.md`（從零重建，模組邊界一次設計到位）。
- 模組與公開介面：新增 `ediaad/markets/__init__.py`、`ediaad/markets/base.py`（`Source`（`Protocol`）、`Instrument`、`register`、`get_source`、`all_sources`，以及供設定驗證使用的來源週期查詢）、`ediaad/markets/custom.py`（自訂 CSV 來源：`id="csv"`、`needs_api_key=False`、`fetch` 轉呼叫 `data.load_csv`、`search` 回傳單筆 `Instrument` 或明確定義的空清單）；`ediaad/monitor.py` 的週期驗證改呼叫 registry。**不建立 `ediaad/sources/`**。
- 預計觸及的檔案：`ediaad/markets/__init__.py`、`ediaad/markets/base.py`、`ediaad/markets/custom.py`、`ediaad/monitor.py`、`tests/test_markets_base.py`；實作前重新查證。
- 必要環境／依賴：`.venv`（TASK-001）；TASK-002 的 `data.load_csv`、`SERIES_COLUMNS` 與 `DataFormatError` 已完成；測試以 `tmp_path` 合成 CSV 與假來源，不連網。

## 測試計畫

- 測試公開邊界：直接匯入 `ediaad.markets.base` 與 `ediaad.markets.custom` 的公開函式；以 `get_source("csv").fetch(...)` 觀察 Series 契約；以 `monitor.load_config` 觀察週期驗證是否改走 registry，不檢視私有常數或模組內部變數。
- 第一個失敗行為與預期斷言：在模組尚未存在時執行 `.venv/bin/python -c "from ediaad.markets.base import all_sources"`，預期 exit 1（`ModuleNotFoundError: No module named 'ediaad.markets'`），對應測試收集失敗；實作後預期 `all_sources()` 至少含一個 `id == "csv"` 的來源，且該來源的六個協定欄位皆存在、`needs_api_key is False`。
- 後續例外／邊界情境：`get_source("不存在")` 丟出可讀錯誤並列出可用 id；對只支援日線的來源要求 `1h` 丟出可讀錯誤並指出來源與週期；`search("")` 與 `limit` 上限的行為須明確定義並以斷言固定；自訂 CSV 來源沿用 `load_csv` 五種壞輸入（缺欄位、空檔案、非數值、時間無法解析、重複時間戳）各自 `DataFormatError`；`load_config` 對來源不支援週期的設定丟出 `ConfigError` 且訊息指出索引位置。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_markets_base.py -q`；相關回歸 `.venv/bin/python -m pytest tests/test_data.py tests/test_monitor.py -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用（介面、registry 與自訂來源皆可以公開函式加假來源完整驗證）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-011 的交付物（全套 208 passed）；本次新增 `ediaad/markets/`（`__init__`／`base`／`custom`）與 `tests/test_markets_base.py`，並修改 `ediaad/monitor.py`、`ediaad/cli.py`、`tests/test_monitor.py`、`tests/test_scan.py`、`tests/test_cli_match_monitor.py`（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-012.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-012.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-markets-base` sha256:588008ed025e518da487ea5d061788435f206d44297ee71a1d2fa174410610ea（原始碼樹，29 檔；計算方式見 `docs/workflow/PROJECT.md`）；新增 `ediaad/markets/__init__.py` `fa74df62…`、`ediaad/markets/base.py` `2d048d7e…`、`ediaad/markets/custom.py` `80a548f7…`、`tests/test_markets_base.py` `8c26d2b9…`；全套 `248 passed`
- 取消、重開或變更原因：無
