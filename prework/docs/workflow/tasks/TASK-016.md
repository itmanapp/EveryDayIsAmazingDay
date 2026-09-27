# TASK-016：Twelve Data 來源與金鑰存放隔離

- id：TASK-016
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-036"]
- depends_on：["TASK-012"]
- test_evidence：["docs/workflow/tdd/TASK-016.md"]
- review_evidence：["docs/workflow/reviews/TASK-016.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：在 `$EDIAAD_HOME/keys.json` 不存在或沒有 `twelvedata` 金鑰時，呼叫 Twelve Data 來源的 `fetch(symbol, interval, limit)` 丟出可讀錯誤，訊息含申請金鑰的說明與應填入的檔案路徑；有金鑰時以注入的假 HTTP 客戶端取得資料並回傳符合 Series 契約的序列。金鑰只存在 `$EDIAAD_HOME/keys.json`，該檔以 `0600` 權限建立，且金鑰字串不出現在 `watchlist.json`、網頁輸出或日誌中（以 `caplog` 與檔案內容斷言）。
- 本張不做：不實作 Binance、TWSE、catalog（TASK-013、TASK-014、TASK-015、TASK-017）；不建立網頁設定介面或系統狀態頁（TASK-020、TASK-025，本張只提供可被它們呼叫的存取函式）；不實作金鑰申請流程或代理伺服器（`docs/architecture/ENGINEERING-REPORT.md` 第 7.3 節已否決代理與內嵌金鑰）；不申請真實金鑰、不驗證真實額度（`docs/workflow/SPEC.md` 第 8 節 Q-013 為 deferred）；不執行 git 或任何對外動作。
- 每個 AC 在本張負責的範圍：AC-036 全部（無金鑰的可讀錯誤含申請說明、有金鑰時回傳 Series、金鑰只存在 `$EDIAAD_HOME/keys.json` 且 `0600`、不出現在 `watchlist.json`／網頁輸出／日誌）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-036、第 5 節模組表（`ediaad/markets/us.py` 的 `search`、`fetch`）、第 5 節「資料生命週期、權限與狀態轉移」（`keys.json` 權限 `0600`，絕不出現在 `watchlist.json`、網頁輸出或日誌）與「外部依賴與失敗處理」（Twelve Data 無金鑰或額度用盡回可讀錯誤、不影響其他商品）；`docs/architecture/ENGINEERING-REPORT.md` 第 7.3 節（金鑰型來源的取捨、金鑰必須存在獨立檔案）；`docs/workflow/PROJECT.md` 的環境變數（`EDIAAD_HOME`、`TWELVEDATA_API_KEY` 可選）與端點實測（Twelve Data 無金鑰回 `401` 並附申請說明）。
- 模組與公開介面：新增 `ediaad/markets/us.py`（`TwelveDataSource`：`id="twelvedata"`、`display_name`、`supported_intervals`（至少日線）、`needs_api_key=True`、`search`、`fetch`；模組級 `TWELVE_DATA_URL`、`load_api_key(home)`、`save_api_key(home, key)`（以 `0600` 建立 `keys.json`，不覆寫其他來源的鍵））。
- 預計觸及的檔案：`ediaad/markets/us.py`、`ediaad/markets/base.py`（僅新增註冊呼叫，如需要）、`tests/test_markets_twelvedata.py`；實作前重新查證。
- 必要環境／依賴：`.venv`（TASK-001）；TASK-012 的 `Source` 介面與 registry、TASK-002 的 `data.from_rows` 契約已完成；測試以 `tmp_path` 當作 `EDIAAD_HOME`、以假 HTTP 客戶端取代網路，全程離線且不需要真實金鑰。

## 測試計畫

- 測試公開邊界：`get_source("twelvedata").fetch(...)` 的例外與回傳值、`load_api_key`／`save_api_key` 對 `$EDIAAD_HOME/keys.json` 的檔案效果（權限位與內容）、以及日誌輸出；以假 HTTP 客戶端驅動，不檢視私有請求組裝細節。
- 第一個失敗行為與預期斷言：模組尚未存在時匯入失敗（`ModuleNotFoundError: No module named 'ediaad.markets.us'`）；實作後第一個案例為無金鑰情境：`EDIAAD_HOME` 指向 `tmp_path` 且無 `keys.json`，呼叫 `fetch("AAPL", "1d", 100)` 預期丟出 `SourceError`，訊息同時含申請說明字樣與 `keys.json` 路徑。
- 後續例外／邊界情境：`keys.json` 存在且含 `twelvedata` 金鑰時，假 HTTP 回傳合法資料並得到符合契約的 Series，且假客戶端只被呼叫一次；`keys.json` 為損毀 JSON 或缺 `twelvedata` 鍵或金鑰為空字串時各自得到可讀錯誤（不吞掉、不猜測金鑰）；`save_api_key` 建立的檔案權限為 `0600`（`stat().st_mode & 0o777 == 0o600`）且不影響同檔其他來源的鍵；以 `caplog` 斷言整個流程的日誌不含金鑰字串，並斷言 `watchlist.json` 內容不含金鑰；額度用盡／`429` 回應時回可讀錯誤且不影響其他商品。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_markets_twelvedata.py -q`；相關回歸 `.venv/bin/python -m pytest tests/test_markets_base.py -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用（無金鑰與有金鑰兩種情境皆可以 `tmp_path` 與假 HTTP 客戶端完整驗證；真實金鑰與額度依 SPEC 第 8 節 Q-013 為 deferred，不在本張驗證範圍）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-015 的交付物（全套 411 passed）；本次新增 `ediaad/markets/us.py` 與 `tests/test_markets_twelvedata.py`，並在 `ediaad/markets/__init__.py` 加入註冊匯入（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-016.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-016.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-twelve-data` sha256:30b5307030468ea3069ac561af5d466cc17c7828ec1bcb14b04ef88295790c68（原始碼樹，38 檔）；新增 `ediaad/markets/us.py` `df80b096…`、`tests/test_markets_twelvedata.py` `b0d4db8a…`；修改 `ediaad/markets/__init__.py` `d0f3e5ad…`；全套 `475 passed`
- 取消、重開或變更原因：無
