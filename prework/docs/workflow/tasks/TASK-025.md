# TASK-025：監控清單管理、系統狀態、版本與授權頁

- id：TASK-025
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-047","AC-048","AC-066"]
- depends_on：["TASK-020", "TASK-019", "TASK-012", "TASK-031"]
- test_evidence：["docs/workflow/tdd/TASK-025.md"]
- review_evidence：["docs/workflow/reviews/TASK-025.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`GET /api/instruments/search?q=` 可用中文名或代號關鍵字取得含 `symbol` 與 `display_name` 的清單並限制筆數（下拉即可選到商品，不需自行輸入代號）；`GET /api/watchlist` 回傳目前設定，`POST /api/watchlist` 在新增／移除商品、變更週期或輪詢間隔時先經驗證，通過後以原子寫入寫入設定檔，下一次 `run_once` 即以新清單輪詢；系統狀態頁顯示最後輪詢時間、各商品的資料來源（`cache`／`binance`／`cache-stale` 等）與錯誤訊息；版本頁顯示目前版本、最新版本、發佈日期與說明；授權頁在三種狀態下顯示對應內容——未啟用顯示首次啟用表單（輸入密鑰）、有效期內顯示授權狀態與剩餘天數、已過期或已撤銷顯示重新申請連結與原因，並提供更換密鑰的輸入入口，所有狀態以文字表達而非只靠顏色。
- 本張不做：不重實作設定的驗證與原子寫入（呼叫 TASK-019 的 `load_settings`／`save_settings_atomic`，AC-040 的原子性由 TASK-019 負責）、不做規律參數面板（TASK-023）與歷史回看（TASK-024）、不重實作租約驗章／啟用／續期／撤銷／功能分級（TASK-029～TASK-031，本張只讀取並呈現 `ediaad/license.py` 的狀態）；不做 catalog 更新（TASK-017）；不做更新檢查本身與六條架構約束（TASK-032，本張只在頁面與端點呈現 `UpdateState` 的內容）；不引入前端框架。
- 每個 AC 在本張負責的範圍：AC-047 全部（下拉搜尋不需輸入代號、變更通過驗證後寫入設定並在下一輪生效）；AC-048 全部（狀態頁的最後輪詢時間／各商品資料來源／錯誤訊息；版本頁的目前版本／最新版本／發佈日期／說明），其中「最新版本、發佈日期、說明」的資料由 TASK-032 的 `ediaad/update.py` 產出，本張以注入的假 `UpdateState` 驗證呈現；AC-066 全部（三種授權狀態的頁面呈現、首次啟用表單、剩餘天數、重新申請連結、更換密鑰入口、文字化狀態），租約狀態由 TASK-030／TASK-031 的 `verify_lease` 與續期結果提供，本張以注入的假租約狀態驗證呈現，兩者完成後由 TASK-037 整合驗收。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-047／AC-048／AC-066、第 5 節 `ediaad/config.py`（`load_settings`／`save_settings_atomic`／`DEFAULT_SETTINGS`）、`ediaad/monitor.py`（`Instrument`／`Watchlist`／`run_once`）、`ediaad/markets/base.py`（`Source`／`search`／`get_source`／`all_sources`）、`ediaad/update.py`（`UpdateState`／`check_update`）、`ediaad/license.py`（`Lease`／`verify_lease`）、第 5 節資料生命週期（`$EDIAAD_HOME/settings.json`、`lease.json`）與外部依賴失敗處理（除權息失敗要在系統狀態標記）；`docs/architecture/ENGINEERING-REPORT.md` 第 3.2 節 G3／G9／G10／G11、第 6.4 節租約格式與三種狀態、第 6.5 節 manifest 欄位、第 7.1 節 Source 介面（週期驗證改依來源查詢 `supported_intervals`，廢除全域 `ALLOWED_INTERVALS`）、第 7.3 節（TWSE 只有日線）；`docs/workflow/CONTEXT.md` 的「資料來源」「商品目錄」「租約」「機器指紋」「features」。
- 模組與公開介面：`ediaad/web/routes.py` 新增 `GET /api/instruments/search`（呼叫注入的 `Source.search(keyword, limit)`）、`GET`／`POST /api/watchlist`（驗證後呼叫 `save_settings_atomic`）、`GET /api/status`（由 `ediaad/app.py` 的 `Application` 彙整最後輪詢時間與每商品 `data_source`／錯誤訊息）、`GET /api/version`（目前版本與 `UpdateState` 的 `latest_version`／`released_at`／`notes`，缺資料時欄位為 `null` 並顯示「尚未檢查」）、`GET /api/license`（授權狀態、剩餘天數、`features`、重新申請連結；未啟用時 `state="inactive"`，缺 `lease.json` 不得報 500）；新增 `ediaad/web/static/watchlist.js`、`status.js`、`version.js`、`license.js`；`ediaad/app.py` 需保存每輪 `run_once` 的 `RunResult` 與資料來源標記供狀態頁讀取。
- 預計觸及的檔案：`ediaad/web/routes.py`、`ediaad/web/static/watchlist.js`、`ediaad/web/static/status.js`、`ediaad/web/static/version.js`、`ediaad/web/static/license.js`、`ediaad/web/static/index.html`、`ediaad/app.py`、`tests/test_web_watchlist_status.py`；實作前重新查證（特別是 TASK-012 的 registry 介面、TASK-019 的設定檔鍵名與 TASK-031 的租約狀態欄位）。
- 必要環境／依賴：TASK-012 的 registry 與 `Source.search`（測試以假來源注入，離線）、TASK-019 的設定檔與原子寫入（測試用 `tmp_path`）、TASK-020 的服務骨架與 `Application`、TASK-031 的租約狀態與 `features` 分級（測試以假 `Lease` 注入）；除權息或來源失敗的狀態標記沿用 TASK-015 的結果呈現，不在本張重算。

## 測試計畫

- 測試公開邊界：`GET /api/instruments/search`（假來源）、`GET`／`POST /api/watchlist` 對 `tmp_path` 設定檔的實際寫入與下一輪生效、`GET /api/status`、`GET /api/version`（注入假 `UpdateState`）、`GET /api/license`（注入假租約狀態：未啟用／有效期內／已過期或已撤銷三種）。
- 第一個失敗行為與預期斷言：先寫「`GET /api/instruments/search?q=台積` 回 200，清單每項同時含非空 `symbol` 與 `display_name`，且筆數不超過 `limit`」。實作前該端點回 404；實作後三項斷言成立。
- 後續例外／邊界情境：對只支援 `1d` 的來源（TWSE）選 `1h` 時回 400 並指出來源與不支援的週期、且設定檔內容不變；`instruments` 被清空回 400 並保留原檔；設定檔損毀時端點回報錯誤且不覆蓋原內容（原子性由 TASK-019 保證，本張只驗證端點行為與原檔未被改寫）；`POST /api/watchlist` 成功後以注入的時鐘與假 fetch 呼叫下一輪 `run_once`，確認新商品被處理；`/api/status` 在尚未輪詢時顯示「尚未輪詢」而非空白或 500；`/api/version` 在沒有 `UpdateState` 時欄位為 `null` 且頁面顯示「尚未檢查」；`/api/license` 在沒有 `lease.json` 時回 `state="inactive"` 而非 500，有效期內回剩餘天數為正整數，已過期或已撤銷回對應原因與重新申請連結，且三種狀態的文字內容互不相同（不依賴顏色）。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_web_watchlist_status.py -q`；相關回歸 `.venv/bin/python -m pytest -q`。
- 非程式任務的替代驗證與理由：不適用（三個 AC 的後端契約可自動驗證）；下拉搜尋的可用性與狀態／版本／授權頁的實際顯示以 Chrome（Wayland）人工檢查一次並記錄。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-031 的交付物（全套 **888 passed**），檔案樹 sha256 `e37eec7cf2cd17238cb489a9e0d338c078cbed1482f59624ed60f3514131314a`（87 檔，即 TASK-031 的 `checked_version`）；本次新增 `ediaad/web/static/watchlist.js`／`status.js`／`version.js`／`license.js` 與 `tests/test_web_watchlist_status.py`，並修改 `ediaad/web/routes.py`（六個端點）、`ediaad/app.py`（監控執行緒、來源分派與能力轉接、狀態彙整、事件落地）、`ediaad/monitor.py`（`validate_config` 抽出、`save_config`）、`ediaad/license.py`（`http_post`）、`ediaad/web/static/index.html`（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-025.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-025.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-web-watchlist` sha256:8e3a252c4cb202d11ef51f847c10687766c55064500170b970e04bf98da5eee8（原始碼樹，92 檔）；`ediaad/web/routes.py` `c64258d7…`、`ediaad/app.py` `d36c989d…`、`ediaad/monitor.py` `82908123…`、`ediaad/license.py` `a690e550…`、`ediaad/web/static/watchlist.js` `c801d72b…`、`status.js` `c9f177c5…`、`version.js` `858ffa16…`、`license.js` `812c1870…`、`index.html` `0b9ca974…`、`tests/test_web_watchlist_status.py` `062e19f4…`；全套 **919 passed**；變異矩陣 35 個 → 33 偵測到、2 等價（已說明）、0 無效
- 取消、重開或變更原因：無
