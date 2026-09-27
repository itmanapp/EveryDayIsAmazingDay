# TASK-025 Code Review

- task_id：TASK-025
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-web-watchlist sha256:8e3a252c4cb202d11ef51f847c10687766c55064500170b970e04bf98da5eee8
- Task／Spec 版本：TASK-025 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24～2026-09-25，第 1 輪（含「重新申請連結指向不存在頁面」的缺陷修正與變異矩陣重跑）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `e37eec7cf2cd17238cb489a9e0d338c078cbed1482f59624ed60f3514131314a`（87 個檔案，即 TASK-031 的 `checked_version`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `8e3a252c4cb202d11ef51f847c10687766c55064500170b970e04bf98da5eee8`（92 個檔案）；本張新增 `ediaad/web/static/watchlist.js` `c801d72b…`、`status.js` `c9f177c5…`、`version.js` `858ffa16…`、`license.js` `812c1870…`、`tests/test_web_watchlist_status.py` `062e19f4…`；修改 `ediaad/web/routes.py` `c64258d7…`、`ediaad/app.py` `d36c989d…`、`ediaad/monitor.py` `82908123…`、`ediaad/license.py` `a690e550…`、`ediaad/web/static/index.html` `0b9ca974…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對；Red 以受控複本（`/tmp/red25`）重建新增公開邊界
- 納入的檔案：上述十個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`data.py`／`features.py`／`similarity.py`／`scan.py`／`outlook.py`／`patterns.py`／`store.py`／`config.py`／`markets/*`／`notify/*`／`web/server.py`／`web/sse_hub.py`／`launcher.py`／`cli.py` 本張只呼叫未修改（`monitor.run_once` 的介面完全不動）
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-047／AC-048／AC-066、第 5 節（HTTP 錯誤格式、資料生命週期 `$EDIAAD_HOME/settings.json` 與 `lease.json`、模組責任與依賴方向）、第 6 節可及性；`docs/workflow/tasks/TASK-025.md`；`docs/architecture/ENGINEERING-REPORT.md` 第 3.2 節 G3／G9／G10／G11、第 6.3 節（網頁層只做參數解析、錯誤轉譯與呈現）、第 6.4 節租約格式與三種狀態、第 7.3 節（TWSE 只有日線）；`references/review.md`；並沿著 TASK-013／TASK-024 的 A-1（來源分派與 `cache_dir`）、TASK-030／TASK-031 的 A-1（403 導流屬 TASK-033）追蹤跨 Task 缺口

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-047 | `ediaad/web/routes.py`（`instruments`／`watchlist`／`save_watchlist`）、`ediaad/monitor.py`（`validate_config`／`save_config`）、`ediaad/web/static/watchlist.js`／`index.html`；`tests/test_web_watchlist_status.py` 的 9 個 Cycle 1 案例 | 符合 | A-1～A-2、A-6、A-8 |
| AC-048 | `ediaad/web/routes.py`（`status`／`version`）、`ediaad/app.py`（`status_payload`／`fetch_for`／`make_emit`）、`ediaad/web/static/status.js`／`version.js`；5 個 Cycle 2 案例 | 符合（「最新版本／發佈日期／說明」的**資料產出**屬 TASK-032，本張以注入的假 `UpdateState` 驗證呈現） | A-3、A-5 |
| AC-066 | `ediaad/web/routes.py`（`license_status`／`activate_license`／`LICENSE_STATES`／`REAPPLY_URL`）、`ediaad/web/static/license.js`；8 個 Cycle 3 案例 | 符合 | A-4、A-7 |

逐條核對：

- **AC-047「下拉搜尋即可選到商品（不需輸入代號）」**：`GET /api/instruments/search?q=&limit=&source=` 完全交給來源的 `search`（網頁層不比對代號或名稱），每一項都同時回 `symbol` 與 `display_name`（`display_name` 為空時退回 `symbol`，因此「空的下拉選項」不可能出現）；`limit` 預設 20、上限 50，且**逐來源分配剩餘額度**。前端下拉以 `describeSearchResults` 呈現，測試以 Node 驗證「台積電」等名稱會出現在文字裡。符合。
- **AC-047「新增／移除商品、改週期、改輪詢間隔；變更通過驗證後寫入設定並在下一輪生效」**：`POST /api/watchlist` 支援三種變更（新增／移除／改週期與輪詢間隔，測試逐項驗證）；驗證與寫入順序是「`validate_config` → `save_config`（原子）→ 更新 `app.watchlist`」，因此不合法內容**不可能**落成檔案（7 種壞輸入後檔案逐字不變）；「下一輪生效」由 `POST` 之後真的呼叫 `run_monitor_round()` 並斷言假來源的請求與 `instrument_status` 內容證明。符合。
- **AC-048「顯示最後輪詢時間、各商品資料來源（cache／binance／cache-stale 等）與錯誤訊息」**：`/api/status` 回 `last_poll_at`（尚未輪詢為 `null`，前端顯示「尚未輪詢」）、逐商品的 `source_id`（設定指定）與 `data_source`（來源回報）、`error` 與 `problems`；測試涵蓋 `cache` 與 `cache-stale` 兩種實際標示，「來源失敗 → 該商品 error 有值、`warnings>=1`」亦有斷言。符合。
- **AC-048「版本頁顯示目前版本、最新版本、發佈日期與說明」**：`/api/version` 以 `app.version` 為目前版本，從 `app.update_state` 取 `latest_version`／`released_at`／`notes`／`checked_at`；沒有結果時**如實為 `null`** 並附「尚未檢查更新」。資料產出（`check_update`／六條約束）屬 TASK-032，本張以注入的假 `UpdateState` 驗證呈現路徑。符合。
- **AC-066「三種授權狀態」**：狀態來自 `license_status`（`unactivated`／`active`／`expired`／`revoked`），並以單一映射 `LICENSE_STATES` 把 `unactivated` 對外改稱 `inactive`；三種狀態的 API 與前端文字（「首次啟用」「有效期內」＋剩餘天數、「已過期」／「撤銷」＋「重新申請」）都有逐項斷言，且斷言的是**文字內容**而非顏色。符合。
- **AC-066「未啟用時顯示首次啟用表單（輸入密鑰）」**：`inactive` 狀態回 `reapply=true`、`features=[]`、`days_remaining=null`，前端 `describeLicense` 輸出首次啟用說明，頁面有 `#license-form`／`#license-key`；`POST /api/license/activate` 以此表單送出，缺 `EDIAAD_LICENSE_URL` 時明確回 400 而不是猜一個網址。符合。
- **AC-066「已過期或已撤銷顯示重新申請連結與原因」**：`expired`／`revoked` 的 `reapply=true`、訊息含原因（「重新申請」／「撤銷」），`reapply_url` 指向**首頁既有錨點** `/#license-heading`，並有測試把片段拿去首頁確認 `id` 真的存在（見「修正與重審」）。符合。
- **AC-066「提供更換密鑰的輸入入口」**：同一個表單第二次送出即為更換密鑰，測試以兩把不同 `key_id` 的租約驗證「以新租約為準」（`GET /api/license` 的 `key_id` 跟著換）。符合。

## 品質 Review

- **兩條跨 Task 缺口真的收斂了（本張最重要的結構成果）**：TASK-013／TASK-024 的 A-1 是「來源未依 `Instrument.source_id` 分派，且非 CSV 來源拿不到 `cache_dir`」——`Application.fetch_for` 以商品設定的 `source_id` 取來源，並用**能力探測**（`inspect.signature` 是否有 `cache_dir`／`max_age`）而不是來源名稱清單決定要不要傳參數。測試注入的類別命名為 `cached`（不在任何既有清單裡）也能拿到快取目錄，證明這不是「把 binance 硬寫進去」。AC-048 的 `cache`／`binance`／`cache-stale` 三態因此有了真實接縫。
- **「下一輪生效」是行為而不是狀態同步**：`POST /api/watchlist` 之後由測試真的跑一輪 `run_monitor_round()`（同一條 `monitor.run_once` 路徑），斷言假來源收到的請求與 `instrument_status`；`app.watchlist` 只是為了讓服務不必重啟就能用新清單。
- **驗證只有一份**：`monitor.validate_config` 同時服務 `load_config`（CLI 讀檔）、`save_config`（寫檔前再驗一次）與網頁端點；路由層**沒有**重寫「週期是否被來源支援」或「清單不得為空」。因此不可能出現「網頁接受、CLI 拒絕」的分岔，也直接保證了「損毀的設定不會被端點覆寫」。
- **監控清單落地在 `watchlist.json` 而不是 `settings.json`**：`settings.json` 的 7 鍵集是 TASK-019 的凍結契約，塞進 `instruments` 會讓那個契約分岔；`monitor.save_config`（驗證 → 暫存檔 → `os.replace`）與 CLI 讀的是同一個檔案，符合 `TASK-025.md` 的意圖（見 A-6 的追認）。
- **引擎 0 改動**：`monitor.run_once` 的介面（`fetch`／`emit`／`warn`／`state`）完全不動，服務端只是接上去；`make_emit` 除了推播與通知之外追加 `store.record_event`，而**去重狀態改用 `Store`**（TASK-018 的 SQLite）——測試以「同事件兩輪 → `alerted` 1、0；`Store` 內一筆事件、一個去重鍵」固定「跨重啟去重」。
- **執行緒語意完整**：`start_monitor` 冪等、沒有清單時回 `False` 並寫 `monitor_error`、每輪以 `Event.wait` 等待（停止不必等一輪結束）、`stop_monitor` 之後不留名為 `ediaad-monitor` 的執行緒、`shutdown()` 先停監控再停服務與關閉資料庫。測試以「等到 `last_poll_at` 有值」而不是 `sleep` 固定秒數，降低競態假陽性。
- **授權頁不重實作授權邏輯**：狀態、剩餘天數、`reapply` 全部來自 TASK-031 的 `lease_status`（唯一真相）；啟用的簽章範圍、30 天長度、機器比對、狀態碼分層全部來自 TASK-030 的 `activate`（網頁層只做「取密鑰 → 呼叫 → 回狀態」）。「缺檔」與「損毀」分開（`inactive` 200／`error` 200，**兩者都不得 500**），與 F-003 的原則一致。
- **可及性與可測性**：每個區塊有 `aria-labelledby` 的標題、狀態用 `aria-live`、錯誤用 `role="alert"`、表單有 `label`；所有狀態都有文字（`STATE_LABELS`），顏色只是輔助。四支前端模組都是載入時不碰 DOM 的 IIFE，可判斷的部分全以 Node 載入**真實檔案**驗證。
- **不引入新依賴**：後端只用標準庫（`urllib` 的 `http_post` 是授權服務的預設客戶端，可注入替換）與既有核心；前端不用框架；`node` 只在測試期使用（`skipif`）。假來源沿用既有的 `markets.base.register`／`unregister` 並在 `finally` 移除。
- **變異矩陣的強度**：凍結版 35 個變異（`routes.py` 17／`app.py` 10／`monitor.py` 2／前端 5）→ **33 偵測、2 等價（已說明）**；`REAPPLY_URL` 的兩個變異（空字串、改回舊的壞連結）是 Review 修正後補入並雙雙被抓到。原 Red 輸出未留存，已以受控複本重建（新增公開邊界的 24 failed／3 passed／3 errors）＋逐變異反空洞證據替代，並在 TDD 完整揭露重建範圍——**不把重建冒充成當時的 Red**。
- **測試品質**：所有案例離線（假來源、假租約、假 HTTP），以真實 HTTP 請求觀察 JSON 與狀態碼；設定檔以 `tmp_path` 觀察**檔案內容**（不只看回傳值）；Node 只載入真實檔案而沒有另寫一份前端邏輯。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 缺口（TASK-013／TASK-024 的 A-1，**已收斂**） | advisory（已處理） | 來源未依 `Instrument.source_id` 分派、非 CSV 來源拿不到 `cache_dir` → 系統狀態頁的三態沒有真實來源 | 本張在 `Application.fetch_for` 完成分派與能力轉接 | **已完成**：`test_fetch_passes_the_cache_dir_to_sources_that_support_it`（`cache_dir`＝`app.cache_dir`、`max_age`＝900、來源類別名為 `cached`）＋`test_status_reports_the_last_poll_and_per_instrument_source` |
| A-2 | 錯誤碼語意 | advisory | `POST /api/watchlist` 在**本機寫入失敗**時回 502（`code="source_failed"`），訊息說「上游來源失敗」但其實是磁碟問題 | 與 TASK-030 的落地失敗同構（`license.py` 的「無法寫入租約」也是 `SourceError`），目前一致；若日後要區分，應在 SPEC 第 5 節新增本機儲存錯誤碼，而不是在單一 Task 改動 | 已記錄（維持一致；測試斷言 502 且訊息含「寫入」） |
| A-3 | SPEC 第 5 節模組表 | advisory（需追認） | 本張新增的公開介面不在模組表：`monitor.validate_config`／`save_config`、`license.http_post`、六個 HTTP 端點與四支前端模組；先前的 `ediaad/match.py`、`ediaad/paths.py` 也在同一張待追認清單上 | 在 TASK-037 的整體驗收一併補列，維持「模組表 ↔ 實作」一致 | 待追認（已記於 `STATE.md` 待決事項） |
| A-4 | 時鐘不可注入 | advisory | `license_status` 以 `now=None` 呼叫 `lease_status`（用真實時鐘）；測試只能把租約的到期日相對真實 `now` 擺放，「剩餘天數」的邊界（例如 0.4 天）無法精確固定 | 若日後要精確測邊界，應讓 `Application` 提供可注入的 `now`（TASK-030 的 `check_lease` 已有此參數，路由層只是沒傳）；本張的斷言（`days_remaining > 0`、`expires_at` 逐字、三態文字）已足以固定 AC-066 的行為 | 已記錄（延後） |
| A-5 | 版本比較 | advisory | `/api/version` 的 `update_available` 是字串不等比較（`latest != version`），不是語意化版本排序 | 比較邏輯應由 TASK-032 的 `UpdateState`／`check_update` 擁有；本張只呈現，不在此新增排序規則 | 已記錄（TASK-032 的範圍） |
| A-6 | 與 Task 文件的落差 | advisory（需追認） | `TASK-025.md` 的接手上下文寫「驗證後呼叫 `save_settings_atomic`」，但實作改為 `watchlist.json` ＋ `monitor.save_config`（`settings.json` 的鍵集是 TASK-019 的凍結契約，塞進 `instruments` 會讓它分岔） | 追認此設計；Task 文件的文字可在 TASK-037 一併更新，SPEC 資料生命週期已列出 `watchlist.json`（`monitor.py` 的產物） | 已記錄（實作與 SPEC 一致，與 Task 文件的實作建議不同） |
| A-7 | 重新申請連結 | advisory（**已修正**） | `REAPPLY_URL` 原為 `/static/license_page.html#reapply`，該頁面**不存在**（`GET` 404，頁上也沒有 `reapply` 錨點）→ AC-066 的連結等於壞掉 | 已改為指向首頁授權區塊的既有錨點 `/#license-heading`；新增 `test_reapply_link_points_at_an_anchor_that_exists`（把片段拿去首頁找 `id="…"`）並補 `M35`／`M36` 兩個變異 | **已修正**：`routes.py` `REAPPLY_URL = "/#license-heading"`；`31 passed`；`M35`／`M36` 皆 DETECTED |
| A-8 | 真實瀏覽器檢查 | advisory（**未執行**） | SPEC 第 7 節要求人工檢查；本環境無瀏覽器自動化。下拉搜尋操作、清單編輯、三種授權狀態畫面與「不單靠顏色」的目視確認仍未做 | 交付前在 Chrome（Wayland）走一次：搜尋 → 新增 → 儲存 → 狀態頁 → 版本頁 → 三種授權狀態 | 待辦（替代驗證已記錄於 TDD） |
| A-9 | 長期穩定性 | advisory | 監控執行緒只測一輪（`interval=1`）＋立即停止；長時間輪詢的漂移、來源暫時失敗的重試節奏、`interval` 在服務運行中變更（需重啟執行緒）都未驗證 | 交付前手動讓服務連續跑一段時間並觀察狀態頁；若要在執行中套用新 `poll_interval_seconds`，需新增行為與 AC | 已記錄（延後） |
| A-11 | 跨 Task 缺口（TASK-024 的 A-1 的姊妹項，**本張未做**） | advisory（**需在後續 Task 處理**） | `ediaad/web/routes.py` 的 `_fetch_series`（`GET /api/series`，K 線圖用）仍只對預設 CSV 來源傳 `cache_dir`，其他來源用註冊時的預設（無快取）→ `source=binance` 的圖表請求每看一次就直連上游；同一支服務裡「監控輪詢有快取、圖表沒有」是兩種行為 | 讓 `_fetch_series` 與 `Application.fetch_for` 共用同一段能力探測（抽出一個 helper，而不是複製第二份判斷），或改由 `Application` 提供單一的「依商品取序列」入口供兩個路徑呼叫；圖表端點屬 TASK-020／TASK-022／TASK-024 的範圍，本張的宣告邊界（「不做歷史回看」）不含它，故未改動 | 待辦（已記於 `STATE.md` 待決事項；TASK-025 的監控路徑已接線並有測試） |
| A-10 | 流程記載 | advisory（非程式） | 原 Red 執行的輸出未留存；測試檔第一版有 5 處自傷錯誤（中文查詢字串讓 `http.client` 丟 `UnicodeEncodeError`、假來源候選讓 `limit` 測試不只一筆、`build_series(total=40)` 越界、假來源 id 未註冊、啟用測試未注入真實指紋與夾具公鑰） | 已全部修正並如實記載（TDD 的「如實記載的測試／實作錯誤」）；Red 以受控複本重建並明確標示範圍 | **已記載** |

## 修正與重審

- 第 1 輪 Spec Review：AC-047／AC-048／AC-066 的宣稱逐條符合（AC-048 的「最新版本／發佈日期／說明」資料產出屬 TASK-032，本張以注入的假 `UpdateState` 驗證呈現）。
- 第 1 輪品質 Review 抓到 **1 個 blocking 級缺陷並已修正**：`REAPPLY_URL` 指向不存在的頁面（`/static/license_page.html#reapply`）→ 改為 `/#license-heading`（既有錨點），並新增一個「連結片段必須存在於首頁」的測試與兩個變異（`M35`／`M36`）釘住；隨後重跑測試檔（`31 passed`）、全套（**919 passed**）、兩個流程驗證器（exit 0）與凍結版變異矩陣（**35 個 → 33 偵測、2 等價、0 無效**），並重算檔案樹雜湊（`8e3a252c…`，92 個檔案）。
- 依變異檢查處理：`M06` 因目標行已不存在（`count=0`）於凍結前移除；`M15`／`M27` 判讀為等價（同一契約的兩個入口／被下一道檢查掩蓋的型別防禦）並在 TDD 逐項說明，未為了「全殺」而放寬或重寫實作。
- 重審：重讀 `routes.py` 的六個端點、`app.py` 的監控區塊、`monitor.validate_config`／`save_config` 與四支前端模組，複查驗證與寫入順序、狀態碼語意、`.pyc` 假偵測的防護、來源分派與能力探測、以及「缺檔／損毀／尚未輪詢／尚無更新資料」四種「還沒有」狀態是否都與「有結果但沒有命中」分開。無需第二輪修正迴圈。

## 結果

- Spec Review：passed（AC-047／AC-048／AC-066 逐條符合）
- 品質 Review：passed（無 blocking；A-7 已修正，A-1 已收斂，A-3／A-6 需追認，A-2／A-4／A-5／A-9／A-11 已記錄延後，A-8 待人工檢查，A-10 為流程記載）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-2（需 SPEC 新增本機儲存錯誤碼才值得改）、A-3（Spec 補模組表，TASK-037）、A-4（需路由層可注入時鐘；現有斷言已足夠）、A-5（比較邏輯屬 TASK-032）、A-6（追認設計決定）、A-8（交付前人工檢查）、A-9（需長時間實跑，或新增 AC 才支援執行中改間隔）、A-10（已記載）、A-11（圖表端點不在本張宣告邊界內，需在後續 Task 讓兩個路徑共用同一段能力探測）
- 能否標為 done：**可以**
- 限制與未驗證事項：真實瀏覽器的人工檢查未執行；原 Red 輸出未留存（以受控複本重建＋變異矩陣替代）；`attachWatchlist`／`attachLicenseForm` 的 DOM 流程未自動測試；監控執行緒只驗證單輪；真實授權服務未驗證（TASK-033）；`update_available` 為字串比較（TASK-032 擁有語意化比較）；本機寫入失敗沿用 502 `source_failed` 的既有映射；`GET /api/series` 的非 CSV 來源仍未接上 `cache_dir`（A-11，屬 TASK-020／022／024 的端點）
