# TASK-032：更新檢查子系統與六條約束

- id：TASK-032
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-059"]
- depends_on：["TASK-001"]
- test_evidence：["docs/workflow/tdd/TASK-032.md"]
- review_evidence：["docs/workflow/reviews/TASK-032.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`ediaad/update.py` 提供 `check_update(...)`（讀取 `GET /v1/latest` manifest）、`UpdateState`、`fetch_catalog(...)`（讀取 `GET /catalog.json`）與快取讀寫；六條約束**逐條可驗證**：
  1. 逾時上限 5 秒（單次請求不得超過 5 秒即返回）。
  2. 絕不阻塞啟動、網頁回應、監控輪詢（更新檢查在獨立執行緒執行）。
  3. 失敗一律靜默，只記狀態（不拋例外、不印錯誤、不中斷主流程）。
  4. 網頁載入時立即回傳快取結果，實際檢查在背景執行。
  5. 去抖動 5 分鐘（同一時窗內不重複發出請求）。
  6. 可完全關閉（關閉後不建立執行緒、不發出請求）。
  且**只顯示版本資訊、不下載不安裝**：模組只讀 manifest 的顯示欄位（`version`、`released_at`、`min_supported`、`notes`、`catalog_version`），不觸碰也不抓取 `url`／`sha256` 指向的檔案，不寫入安裝目錄。
- 本張不做：不做下載、解壓、安裝、替換程式或重啟（明確 out of scope，報告第 3.3 節與 SPEC 第 2 節）；不做 catalog 的版本比對與原子取代（TASK-017）；不實作 `/v1/latest` 與 `/catalog.json` 端點（TASK-034）；不做版本頁 UI（TASK-025）；不做 `features` 分級判定本身（TASK-031，本張只接收 `enabled` 參數）；不做 `license`／`serve` 子命令（TASK-036）。
- 每個 AC 在本張負責的範圍：AC-059 全部（五秒逾時、不阻塞啟動／網頁／輪詢、失敗靜默、快取優先、五分鐘去抖動、可完全關閉、只顯示不下載不安裝）。AC-057 中「缺少 `update` 時更新功能停用」的判定屬 TASK-031，本張負責在 `enabled=False` 時完全不動作。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-059、第 5 節模組表 `ediaad/update.py` 的對外 API（`check_update`、`UpdateState`、`fetch_catalog`）、外部依賴表「Cloudflare 更新服務：5 秒逾時、失敗靜默、用快取」、產物位置（`$EDIAAD_HOME/catalog.json`）、第 6 節可靠性（更新檢查不得阻塞主要流程）與可測試性（網路與時鐘可注入）、第 7 節測試策略列；`docs/architecture/ENGINEERING-REPORT.md` 第 6.5 節全文（manifest schema、**六條架構約束**、分成 manifest 與 renew 兩個端點的理由）；`docs/workflow/PROJECT.md` 環境變數 `EDIAAD_UPDATE_URL` 與實測表（PyPI／Cloudflare 端點可達，但測試不得依賴網路）。
- 模組與公開介面：`ediaad/update.py`（本張首次建立）新增
  - `UpdateState`（至少含 `latest_version`、`released_at`、`min_supported`、`notes`、`checked_at`、`source`（`network`／`cache`／`disabled`）、`error`）。
  - `check_update(*, http, manifest_url: str, now, cache_path, enabled: bool = True, timeout: float = 5.0, debounce_seconds: int = 300, force: bool = False, background: bool = False) -> UpdateState`。
  - `fetch_catalog(*, http, catalog_url: str, cache_path, now, timeout: float = 5.0) -> dict`。
  - `load_cache(path)`／`save_cache(path, state)`（原子寫入，沿用 TASK-019 的原子寫入原則）。
  - `http` 為可注入客戶端（介面只要求 `get(url, timeout) -> (status, body)`）；時間一律由 `now` 注入，不得使用 `datetime.now()`；背景執行以注入的 executor／thread factory 為邊界，測試不依賴真實計時。
- 預計觸及的檔案：`ediaad/update.py`、`tests/test_update.py`；必要時 `ediaad/config.py`（`update_enabled` 設定的讀取，屬 TASK-019）；實作前重新查證。
- 必要環境／依賴：`.venv`＋`pytest`；假 HTTP（可計數、可阻塞、可逾時、可回 500）；假時鐘；`tmp_path` 作為快取位置；全程離線，測試不得連向 `EDIAAD_UPDATE_URL` 的真實位址。

## 測試計畫

- 測試公開邊界：只呼叫 `check_update`、`fetch_catalog`、`load_cache`；HTTP 與時鐘全部注入；以 `tmp_path` 觀察快取檔與「是否產生其他檔案」。
- 第一個失敗行為與預期斷言：實作前 import 失敗；首案 `test_manifest_parsed_and_cached` 餵入合成 manifest（`version`、`released_at`、`min_supported`、`notes`、`catalog_version`、`catalog_url`、`url`、`sha256`、`size`），斷言 `UpdateState.latest_version == "0.4.0"`、`source == "network"`、快取檔已寫入，且假 HTTP 只收到一筆 GET（沒有第二筆指向 `url` 的下載請求）。
- 後續例外／邊界情境：六條約束逐條如下。
  1. **逾時上限 5 秒**：假 HTTP 收到 `timeout == 5.0`；以會阻塞的假 HTTP＋捲動假時鐘驗證在 5 秒上限內返回並記下 `error`，呼叫端不拋例外（測試不實際等待 5 秒）。
  2. **不阻塞**：以 `threading.Event` 讓假 HTTP 卡住，透過注入的背景執行邊界啟動檢查，斷言（a）啟動路徑函式、（b）網頁請求處理函式、（c）監控 `run_once` 三者都在未放行 Event 前就返回。
  3. **失敗靜默**：假 HTTP 拋 `SourceError` 或回 500 → `check_update` 不拋例外、不寫入 stderr／日誌的 error 級訊息，只把狀態記進 `UpdateState.error`。
  4. **快取優先**：已有快取時呼叫後立即得到 `source == "cache"` 的結果，背景檢查完成後才更新快取與 `UpdateState`。
  5. **五分鐘去抖動**：`now` 相差 299 秒連續呼叫兩次 → 假 HTTP 請求計數為 1；相差 300 秒 → 計數為 2；`force=True` 時不受去抖動限制。
  6. **可完全關閉**：`enabled=False` → 請求計數為 0、不建立任何執行緒、回 `source == "disabled"`，且不因關閉而拋例外。
  7. **只顯示不下載不安裝**：模組執行前後比較 `tmp_path` 的檔案清單，除快取 JSON 外不得新增檔案；假 HTTP 的請求 URL 集合只含 manifest／catalog 位址。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_update.py -q`；回歸 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用，六條約束皆可在單元層以注入的假 HTTP／假時鐘／假執行緒邊界先寫 Red。
- 必要的人工檢查：無。「不阻塞網頁回應」若要在整合層複核，屬 TASK-020 的伺服器測試；本張以「檢查在背景執行邊界上、主執行緒立即返回」為自動化證據。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-031 與 TASK-025 的交付物（全套 **919 passed**），檔案樹 sha256 `8e3a252c4cb202d11ef51f847c10687766c55064500170b970e04bf98da5eee8`（92 檔，即 TASK-025 的 `checked_version`）；本次新增 `ediaad/update.py` 與 `tests/test_update.py`，修改 `ediaad/app.py`（`update_url`／排程／pool）、`ediaad/web/routes.py`（`version` 的欄位與訊息）、`ediaad/paths.py`（`update_state_path`）、`ediaad/launcher.py`（服務入口讀 `EDIAAD_UPDATE_URL`）、`ediaad/web/static/version.js`（四態文字）；`ediaad/markets/catalog.py` 只呼叫未修改（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-032.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-032.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-update` sha256:9831e0acb59672b1c9af4bae7c419aad8438f814f67abb5c74028d3f92bb3d55（原始碼樹，94 檔）；`ediaad/update.py` `c7123a0e…`、`ediaad/app.py` `3a2e4dc3…`、`ediaad/web/routes.py` `4cf12eb5…`、`ediaad/paths.py` `94042f3e…`、`ediaad/launcher.py` `b9f58eb7…`、`ediaad/web/static/version.js` `a1bc9c92…`、`tests/test_update.py` `b9e61082…`；全套 **966 passed**；變異矩陣 46 個 → **46 偵測到**（0 存活、0 無效）
- 取消、重開或變更原因：無（第 1 輪 Review 修正 `fetch_catalog` 的重複實作並處理 3 個變異存活者）
