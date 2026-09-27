# TASK-017：版本化 catalog 與更新攜帶

- id：TASK-017
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-038"]
- depends_on：["TASK-012"]
- test_evidence：["docs/workflow/tdd/TASK-017.md"]
- review_evidence：["docs/workflow/reviews/TASK-017.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：本地 catalog 與遠端 catalog 的 `catalog_version` 相比，遠端較新時下載一次並以「暫存檔＋rename」原子取代本地快取（取代後 `catalog_version()` 回傳新版、目錄不留下暫存檔）；版本相同時不對遠端發出任何下載請求；下載失敗（連線錯誤、非 200 或內容格式不符）時保留本地原檔且位元不變，並在回傳的狀態中記錄失敗。`Catalog` 物件含 `catalog_version`、`sources`、`instruments` 三項，且 `load_catalog`／`save_catalog` 可往返還原同一份內容。
- 本張不做：不實作 Binance、TWSE、Twelve Data、自訂 CSV 四個來源（TASK-013～TASK-016，本張只提供可被它們消費的 catalog schema 與載入）；不實作更新檢查的六條架構約束（5 秒逾時、不阻塞啟動與輪詢、失敗靜默、先回快取、5 分鐘去抖動、可完全關閉）與其排程（TASK-032）；不建立 `GET /v1/latest` 或 `/catalog.json` 端點（TASK-034），本張只消費 manifest 已提供的 `catalog_url` 與 `catalog_version`；不實作系統狀態頁的 catalog 狀態呈現（TASK-025）；不執行 git 或任何對外動作。
- 每個 AC 在本張負責的範圍：AC-038 全部（版本比對、較新時下載並原子取代本地快取、版本相同不重複下載、下載失敗保留原檔並記錄狀態）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-038、第 5 節模組表（`ediaad/markets/catalog.py` 的 `Catalog`、`load_catalog`、`save_catalog`、`catalog_version`；`ediaad/update.py` 的 `fetch_catalog`）、第 5 節資料契約的 `Catalog`（`catalog_version`、`sources`、`instruments`）與產物位置（`$EDIAAD_HOME/catalog.json`）、第 5 節「外部依賴與失敗處理」（更新服務失敗靜默、用快取）；`docs/architecture/ENGINEERING-REPORT.md` 第 7.2 節（`catalog.py` 內含帶版本的來源與商品清單、更新 manifest 可攜帶 `catalog_url`）、第 6.5 節 manifest 的 `catalog_version`／`catalog_url` 欄位與六條約束；`docs/workflow/PROJECT.md` 的環境變數（`EDIAAD_UPDATE_URL`）。
- 模組與公開介面：新增 `ediaad/markets/catalog.py`（`Catalog`、`load_catalog(path)`、`save_catalog(catalog, path)`、`catalog_version(catalog_or_path)`，以及更新函式 `update_catalog(local_path, catalog_url, client, state)`：比對版本、下載、原子取代、回報狀態；HTTP 客戶端可注入）；`ediaad/markets/base.py` 僅在需要時新增 registry 與 catalog 的對照函式。
- 預計觸及的檔案：`ediaad/markets/catalog.py`、`ediaad/markets/base.py`（如需要）、`tests/test_markets_catalog.py`；實作前重新查證。
- 必要環境／依賴：`.venv`（TASK-001）；TASK-012 的 `Source` 介面與 registry 已完成；測試以 `tmp_path` 的本地 catalog 與假 HTTP 客戶端執行，全程離線，不需要真實更新服務。

## 測試計畫

- 測試公開邊界：`load_catalog`／`save_catalog`／`catalog_version` 對檔案的往返效果，以及 `update_catalog(...)` 的請求次數、回傳狀態與本地檔內容；以假 HTTP 客戶端驅動，不檢視私有下載細節。
- 第一個失敗行為與預期斷言：模組尚未存在時匯入失敗（`ModuleNotFoundError: No module named 'ediaad.markets.catalog'`）；實作後第一個案例為版本較新：本地 `catalog_version` 為 `2026-09-01`、假遠端為 `2026-10-01`，呼叫 `update_catalog` 後假客戶端請求次數為 1，`catalog_version(本地路徑)` 為 `2026-10-01`，且本地目錄不存在暫存檔殘留。
- 後續例外／邊界情境：版本相同時請求次數為 0 且本地檔位元不變；下載失敗（連線錯誤、`500`、內容非 JSON、缺 `catalog_version`）時本地檔位元不變且回傳狀態標記失敗；本地 catalog 不存在（首次安裝）時的行為明確定義並斷言；版本字串的比較規則（`YYYY-MM-DD` 日期格式）明確定義並以邊界值測試（相同、較新、較舊）；下載中斷造成的半寫以暫存檔＋`os.replace` 防止，並以「寫入中斷後原檔仍可 `load_catalog`」斷言；`save_catalog` 後 `load_catalog` 的 round-trip 完全相等。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_markets_catalog.py -q`；相關回歸 `.venv/bin/python -m pytest tests/test_markets_base.py -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用（版本比對、下載次數與原子取代皆可以假 HTTP 客戶端與真實檔案系統完整驗證，無需人工檢查）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-016 的交付物（全套 475 passed）；本次新增 `ediaad/markets/catalog.py` 與 `tests/test_markets_catalog.py`，並在 `ediaad/markets/__init__.py` 加入匯出（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-017.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-017.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-catalog` sha256:bd49d41006475ccf8e0d8313fb8f9a425f0f9cc036bac8ceaa34dac371302428（原始碼樹，40 檔）；新增 `ediaad/markets/catalog.py` `0b2aa3ad…`、`tests/test_markets_catalog.py` `ab2cdbf4…`；修改 `ediaad/markets/__init__.py` `da15bd6e…`；全套 `519 passed`
- 取消、重開或變更原因：無
