# TASK-036 Code Review

- task_id：TASK-036
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-cli-serve-license sha256:ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab
- Task／Spec 版本：TASK-036 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-25，第 1 輪（含 TASK-025 遺留缺陷的修正、公鑰可設定化、`serve` 授權閘門的設計決定與 TASK-032 間歇性測試的處理）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `45876364bc01a9749bb4597dcbd6f98453525f31b72ac3b2710a0d5dc4ff78f5`（119 個檔案，即 TASK-035 的 `checked_version`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab`（122 個檔案）；本張新增 `tests/test_cli_serve.py` `a8573484…`、`tests/test_cli_license.py` `b3d524f8…`、`tests/_cli_helpers.py` `8f0e81d5…`；修改 `ediaad/cli.py` `d0dcc0a2…`、`ediaad/launcher.py` `8f43da1b…`、`ediaad/license.py` `aa609934…`、`ediaad/web/routes.py` `ef01c2f9…`、`tests/test_web_watchlist_status.py` `4b2ab6ce…`、`tests/test_notify.py` `8f942fe4…`、`tests/test_update.py` `91eb6f4b…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：上述十個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`ediaad/monitor.py`／`match.py`／`store.py`／`app.py`／`markets/*`／`notify/*`／`cloudflare/*` 本張未修改；`ediaad/web/routes.py` 只改啟動前那一行的預設客戶端
- 程式規範來源：`docs/workflow/SPEC.md` AC-064、第 3 節主要流程（`python -m ediaad serve`、續期與更新）、第 5 節 `ediaad/cli.py` 的公開介面與「CLI exit code：0／1／2」、第 7 節測試策略列（CLI 以端到端子程序測試）；`docs/workflow/tasks/TASK-036.md`；`docs/architecture/ENGINEERING-REPORT.md` 第 6.1 節（`cli.py` 新增 `serve` 與 `license` 子命令）、第 6.4 節（三個觸發點、**每次啟動都要離線驗章**、撤銷立即生效、過期導流、時鐘篡改防護）、第 6.5 節（六條更新約束）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-064（`serve` 子命令存在且行為一致） | `cli._run_serve` → `launcher.serve_main`；`test_cli_serve.py` 的 17 個案例 | 符合 | A-1、A-3、A-6 |
| AC-064（`license status`） | `cli._run_license_status`；`test_cli_license.py` 的五個案例（含「把網址指向關閉的埠仍成功」證明不連網） | 符合 | A-2 |
| AC-064（`license activate --key`） | `cli._run_license_activate` → `license.activate`；六個案例（含簽章無效與 4xx 不落地） | 符合 | A-3 |
| AC-064（`license renew --trigger`） | `cli._run_license_renew` → `license.renew`；七個案例（含 403 過期／撤銷與逾時不修改租約） | 符合 | A-4 |
| AC-064（exit code 語意 0／1／2） | `main` 的錯誤分層（`DataFormatError`／`ConfigError` → 2、`SourceError` 與其他 `EdiaadError` → 1、未知例外 → 一行訊息＋1）；各案例逐項斷言 | 符合 | A-5、A-7 |
| AC-064（錯誤不吐 traceback） | 所有使用者錯誤路徑的斷言（`"Traceback" not in stderr`）；未知例外預設一行訊息、`EDIAAD_DEBUG=1` 才給堆疊 | 符合 | A-5 |
| AC-053／AC-056／AC-058（啟動的離線驗章、過期停止、時鐘防護） | `launcher._run_service` 的 `check_lease` 呼叫；`test_cli_serve.py` 的六個拒絕／放行案例 | 符合（**接線**在本張完成） | A-3、A-6 |
| AC-057（租約缺少 `update` 時更新停用） | `launcher._run_service` 的 `has_feature` 分級；兩個案例 | 符合（TASK-032 的 A-3 收斂） | A-8 |

逐條核對（AC-064）：

- **`serve`**：`--port`（預設 `EDIAAD_PORT`／8787，環境變數不合法時 exit 2）、`--home`（預設 `EDIAAD_HOME`），只 bind `127.0.0.1`；服務本體**完全**交給 `launcher.serve_main`（TASK-026 的 A-4），因此 PID 檔、訊號、優雅關閉與通知啟用都是同一條路徑。就緒（10 秒內）與結束（exit 0、埠釋放、PID 檔移除）都有子程序層證據。符合。
- **`license status`**：唯讀（`load_lease` ＋ `lease_status`），有效時 exit 0 並列出到期日、剩餘天數與功能；未啟用／已過期／已撤銷 → exit 2 並附原因與重新申請提示；測試證明它**不發出任何網路請求**。符合。
- **`license activate --key`**：`activate` 的 4xx → exit 2 且不落地、5xx／連線失敗 → exit 1、簽章無效 → exit 2 且不落地、成功 → exit 0 且落地的租約等於伺服器簽發的那一份。符合。
- **`license renew --trigger`**：預設 `manual`、三種 trigger 原樣送出、非法值由 argparse 擋下（exit 2）；後端 403（過期）→ exit 2＋重新申請、403 且 `revoked` → exit 2＋落地撤銷標記、不可達 → exit 1；所有失敗路徑都斷言租約檔**一位元都沒變**。符合。
- **exit code 語意**：0／1／2 的分層與 SPEC 第 5 節一致；未知例外預設只印一行（`EDIAAD_DEBUG=1` 時 re-raise 以便除錯）。符合（見 A-5 的取捨說明）。

## 品質 Review

- **修好一個真實的潛伏缺陷（本張最重要的品質成果）**：`routes.activate_license` 的預設 `http` 是**函式** `http_post`，而核心要的是有 `.post()` 的**物件**。真實路徑（未注入客戶端）會 500；TASK-025 的測試全部注入 `RecordingHttp` 所以看不到。已在 `license.py` 提供 `UrllibHttpClient`／`HTTP_CLIENT`、修正預設值，並在 TASK-025 的測試檔補「不注入客戶端」的回歸測試。**這正是「CLI 邊界測試」的價值**：換一條呼叫路徑就照出單元測試的盲點。
- **啟動閘門的設計決定被明確定義**：`未啟用` → 啟動（否則使用者進不了啟用頁，AC-066 不成立）；`有租約但無效` → 拒絕啟動（過期／撤銷／別台機器／簽章失敗／租約損毀）。exit code 用 `LeaseVerdict.force_online` 區分「狀態錯誤 → 2」與「線上驗證不可用 → 1」，**不靠訊息字串比對**。
- **設定檔損毀仍然啟動**（與 TASK-036.md 測試計畫第 5 點的寫法不同）：TASK-020 明訂「網頁是唯一的修復介面」，因此 `serve` 只警告並讓問題出現在系統狀態頁；**租約**損毀才拒絕啟動。已在 A-6 記錄這個刻意偏離。
- **公鑰可設定是必要的，不只是方便**：內嵌常數是 fail-closed 的佔位值，若沒有 `EDIAAD_LICENSE_PUBLIC_KEY`，授權閘門會永遠拒絕啟動（產品無法使用）。環境變數保留「預設不信任任何簽章」的性質，同時讓自架授權服務可用；格式錯誤直接 `ConfigError`（**不回退**到佔位值，否則症狀會變成「所有租約都驗不過」）。
- **CLI 只做轉譯**：`serve` 不含任何服務邏輯（全部交給 `serve_main`）、`license` 三個子命令分別呼叫 `activate`／`renew`／`lease_status`；`cli.py` 沒有新增授權判斷。這是 SPEC 第 5 節「CLI 不重複實作核心邏輯」的直接證據。
- **測試方式符合 SPEC 第 7 節**：CLI 一律以**子程序**驗證（exit code 與 stderr 才是使用者看到的東西），另以 `build_parser()` 驗參數樹；授權命令以 loopback 假服務驗請求契約；全程不連外網。
- **錯誤訊息可操作**：每個失敗都告訴使用者下一步（重新申請、設定 `EDIAAD_LICENSE_URL`、確認網路、`EDIAAD_DEBUG=1` 取堆疊），且檔名（`lease.json`）會出現在訊息裡（本張順手修好 `load_lease` 的檔名）。
- **變異矩陣的強度**：24 個變異在凍結版**全數被抓到、沒有存活者**；`serve` 的四個閘門決策、`status` 的三種狀態、`renew` 的三條失敗路徑、三個路徑參數與公鑰驗證都有對應的負例。
- **跨 Task 的測試變更誠實記錄**：`test_web_watchlist_status.py`（+1 回歸測試）、`test_notify.py`（替身補 `problems`／`settings`）、`test_update.py`（背景執行緒測試改為 join），三處都在 TDD 的表與 STATE 的待決事項中列出，供 TASK-037 複核。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 網路曝露 | advisory | `serve` 只 bind `127.0.0.1`（刻意：完全本地運行、不對外提供服務），但同一台機器的其他使用者仍可連上該埠；服務沒有身分驗證 | 多使用者機器上可考慮 Unix domain socket 或本機驗證；目前符合 SPEC 的「只 bind 127.0.0.1」 | 已記錄（`test_serve_starts_serves_and_stops_gracefully` 以 127.0.0.1 驗證） |
| A-2 | `license status` 的 exit 2 | advisory | 「尚未啟用／已過期／已撤銷」都回 exit 2（設定或狀態錯誤）。這對腳本而言與「參數打錯」同碼，無法只憑 exit code 分辨三種狀態 | 需要機器可讀輸出時可加 `--json`（新需求）；目前的人類可讀訊息已足夠，且 SPEC 只要求 0／1／2 | 已記錄（`test_cli_license.py` 的斷言即為契約） |
| A-3 | 授權閘門的位置 | advisory | 閘門放在 `launcher._run_service`，因此 `launcher --serve`（桌面啟動器、`scripts/ediaad_launcher.py`）與 `python -m ediaad serve` **行為一致**；但 `Application` 本身仍不驗授權（直接內嵌使用的呼叫端不受限制） | 刻意如此：`Application` 是給測試與工具用的低階介面，「啟動服務」的授權要求屬於**服務入口**。TASK-037 的 DELIVERY 應說明這條邊界 | 已記錄 |
| A-4 | 密鑰以命令列參數傳入 | advisory | `--key` 會出現在 shell 歷史與 `ps` 輸出（TASK-036.md 明訂不從 stdin 讀取以避免進入 shell 歷史，但參數本身就是另一種暴露） | 需要更安全時支援 `--key-file` 或 `getpass` 提示（新需求）；目前符合任務邊界 | 已記錄（TDD 的「未執行或受阻」第 3 點） |
| A-5 | 未知例外的處理 | advisory | 未知非 `EdiaadError` 例外只印一行訊息（`EDIAAD_DEBUG=1` 才 re-raise）。這滿足「不吐 traceback」，但預設會把程式缺陷偽裝成一般錯誤 | 保留 `EDIAAD_DEBUG` 開關；若日後要回報機制，可在非 debug 時也寫一份堆疊到日誌檔 | 已記錄（`cli.main` 的註解） |
| A-6 | 與 Task 文件的差異（設定檔損毀） | advisory（需追認） | TASK-036.md 的測試計畫第 5 點寫「損毀的 `settings.json` → exit 2」；實作改為**仍然啟動**並警告（TASK-020 的凍結設計：網頁是唯一的修復介面）。**租約**損毀則確實 exit 2 | 追認：`settings.json` 損毀時拒絕啟動會讓使用者無法用網頁修復；若確實要 exit 2，應同時提供 CLI 的設定修復路徑（新 AC） | 已記錄（`test_serve_warns_about_a_corrupt_settings_file_but_still_starts`） |
| A-7 | 子命令的 `--home` | advisory | `license` 三個子命令沒有 `--home`（只吃 `EDIAAD_HOME`），而 `serve` 兩者都支援；不一致 | 若日後要一致，為 `license` 加 `--home` 即可（向後相容）；目前以環境變數為準已在說明中寫明 | 已記錄 |
| A-8 | AC-057 的持久化 | advisory | features 分級只改**記憶體**中的 `update_enabled`，不覆寫 `settings.json`（尊重使用者設定）；若使用者把 `update_enabled` 設為 `False`、租約有 `update`，仍是關閉（兩者取交集） | 這是刻意的（租約只能**限制**、不能強制開啟）；網頁顯示的值即為實際生效值 | 已記錄（兩個 `serve` 案例） |
| A-9 | TASK-032 測試的間歇性 | advisory（**需在 TASK-037 複核**） | `test_background_without_an_executor_uses_a_daemon_thread` 在整套測試下曾間歇性失敗（10 秒輪詢 → 30 秒仍偶發，約 5 次全套出現 2 次）。已改成**直接 join 具名執行緒並斷言 daemon 性質**；根因未完全確定（疑似高負載下的執行緒排程） | TASK-037 的整體驗收要連續跑數次全套並確認不再出現；若再現，應以 `faulthandler`／`threading.enumerate()` 快照進一步定位 | 已修正並重跑（單檔 3/3、全套 1/1 通過）；記於 STATE 待決事項 |
| A-10 | 真實服務未驗證 | advisory（**未執行**） | 真實 Cloudflare Worker／D1 未部署，CLI → 真實授權服務的端到端因此未驗證；`serve` 後的瀏覽器互動屬 TASK-020～026 的人工檢查 | TASK-037 的 DELIVERY 明列；取得帳號後以 `wrangler dev` 或部署後的網址跑一次 `license activate`／`renew` | 待辦（TDD 的「未執行或受阻」第 1 點） |

## 修正與重審

- 第 1 輪 Spec Review：AC-064 的五項與三個啟動驗證／分級的接線逐條符合。
- 第 1 輪品質 Review 修正 **1 個真實缺陷**（TASK-025 遺留的預設 HTTP 客戶端）、**2 處可操作性問題**（`load_lease` 的檔名、可設定的簽章公鑰）與 **2 處跨 Task 的測試/替身更新**（`test_web_watchlist_status.py` 的回歸測試、`test_notify.py` 的 `FakeApp`）。
- 另外處理 TASK-032 的間歇性測試（改為 join ＋ daemon 斷言），並修正自己引入的 `launcher.py` 語法錯誤。
- 重審：重跑 CLI 兩個測試檔（**35 passed**）、全套（**1007 passed**）、Node（**82 passed**）、兩個流程驗證器（exit 0），並在凍結版重跑變異矩陣（**24／24 偵測到，0 存活、0 無效**）；重讀 `cli.py` 的分派與錯誤分層、`launcher._run_service` 的閘門四條路徑、`license.public_key_from_env`／`HTTP_CLIENT`、`routes` 的預設客戶端，以及三個子命令的輸出格式。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-064 逐條符合；AC-053／056／057／058 的接線完成）
- 品質 Review：passed（無 blocking；A-1～A-5／A-7／A-8 已記錄的刻意取捨，A-6 需追認，A-9 交 TASK-037 複核，A-10 未驗證）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（不可遠端存取是刻意設計）、A-2（需要 `--json` 才可能分辨，屬新需求）、A-3（`Application` 不驗授權是刻意的邊界）、A-4（`--key-file` 屬新需求）、A-5（保留 `EDIAAD_DEBUG` 開關）、A-6（追認與 TASK-020 的一致性）、A-7（`license --home` 屬一致性改善）、A-8（租約只限制、不強制開啟）、A-9（TASK-037 複核）、A-10（需帳號與部署授權）
- 能否標為 done：**可以**
- 限制與未驗證事項：真實授權服務與 D1 未部署（CLI → 真實 Worker 的端到端未驗證）；瀏覽器互動人工檢查未執行；密鑰以命令列參數傳入（`ps` 可見）；Windows 的訊號語意未驗證；`license` 子命令沒有 `--home`；TASK-032 的背景執行緒測試曾間歇性失敗（已改寫，待 TASK-037 連續複核）
