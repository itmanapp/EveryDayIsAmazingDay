# TASK-032 Code Review

- task_id：TASK-032
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-update sha256:9831e0acb59672b1c9af4bae7c419aad8438f814f67abb5c74028d3f92bb3d55
- Task／Spec 版本：TASK-032 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-25，第 1 輪（含 `fetch_catalog` 重複實作的修正、三個變異存活者的處理與變異工具的中斷安全）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `8e3a252c4cb202d11ef51f847c10687766c55064500170b970e04bf98da5eee8`（92 個檔案，即 TASK-025 的 `checked_version`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `9831e0acb59672b1c9af4bae7c419aad8438f814f67abb5c74028d3f92bb3d55`（94 個檔案）；本張新增 `ediaad/update.py` `c7123a0e…`、`tests/test_update.py` `b9e61082…`；修改 `ediaad/app.py` `3a2e4dc3…`、`ediaad/web/routes.py` `4cf12eb5…`、`ediaad/paths.py` `94042f3e…`、`ediaad/launcher.py` `b9f58eb7…`、`ediaad/web/static/version.js` `a1bc9c92…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：上述七個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`ediaad/markets/catalog.py`（TASK-017）本張**只呼叫** `update_catalog` 未修改；`monitor.py`／`store.py`／`web/server.py`／`web/sse_hub.py`／`license.py`／`notify/*`／`markets/*` 其餘檔案未修改
- 程式規範來源：`docs/workflow/SPEC.md` AC-059、第 5 節模組表（`ediaad/update.py` 的對外 API）與資料生命週期、第 6 節可靠性（更新檢查不得阻塞主要流程）與可測試性（網路與時鐘可注入）、第 7 節測試策略列；`docs/workflow/tasks/TASK-032.md`；`docs/architecture/ENGINEERING-REPORT.md` 第 6.5 節（manifest schema、**六條架構約束**、manifest 與 renew 分成兩個端點的理由）與第 3.3 節（不下載不安裝）；`ediaad/markets/catalog.py`（TASK-017 的既有 catalog 更新流程）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-059（六條約束） | `ediaad/update.py`（`check_update`／`_get_with_deadline`／`_perform`／`_submit`）、`ediaad/app.py`（`trigger_update_check`）、`ediaad/web/routes.py`（`version`）；`tests/test_update.py` 的 Cycle 2～6、8 | 符合 | A-1～A-8、A-11 |
| AC-059（只顯示版本資訊、不下載不安裝） | `parse_manifest`（只讀顯示欄位）、`tests/test_update.py::test_update_never_downloads_or_installs` | 符合 | A-1 |
| AC-059（逾時上限 5 秒） | `DEFAULT_TIMEOUT = 5.0`、`_get_with_deadline`；`test_default_timeout_is_five_seconds`、`test_blocking_http_returns_within_the_deadline` | 符合 | A-7 |
| AC-059（不阻塞啟動／網頁回應／監控輪詢） | `Application.start()`／`trigger_update_check`、`routes.version`；`test_start_does_not_block_on_the_update_check`、`test_web_responses_are_not_blocked_by_the_update_check`、`test_monitor_round_is_not_blocked_by_the_update_check` | 符合 | A-8 |
| AC-059（失敗靜默只記狀態） | `_perform` 的 `try／except Exception`、`_deliver`；Cycle 3 的三個測試＋背景失敗測試 | 符合 | A-11、A-12 |
| AC-059（網頁先回快取、實際檢查在背景） | `check_update(background=True)`、`Application.trigger_update_check`、`routes.version`；Cycle 4 的六個測試＋`test_version_endpoint_returns_cache_immediately_and_checks_in_background` | 符合 | A-6 |
| AC-059（5 分鐘去抖動） | `UpdateState.is_stale`＋`check_update`；Cycle 5 的五個測試 | 符合 | A-12 |
| AC-059（可完全關閉） | `check_update(enabled=False)`、`Application.trigger_update_check` 的閘門；Cycle 6 的三個測試＋`test_trigger_update_check_decides_alone` | 符合 | A-3 |
| AC-057（缺少 `update` 時更新功能停用但服務仍可用） | `update_enabled` 設定＋`/api/version` 的 `update_enabled` 與「已關閉」訊息；`test_version_endpoint_reports_disabled_and_failed_checks`、`test_version_page_distinguishes_every_state` | **部分符合（跨 Task）**：`enabled` 參數語意與呈現已完成；租約 `features` 的判定呼叫端屬 TASK-036 | A-3 |
| AC-048（版本頁顯示最新版本／發佈日期／說明） | 本張提供 `UpdateState` 的資料與四態訊息；TASK-025 的端點欄位沿用 | 符合（端到端由 TASK-037） | — |

逐條核對（六條約束）：

1. **逾時上限 5 秒**：`DEFAULT_TIMEOUT = 5.0` 同時傳給 HTTP 客戶端與 `_get_with_deadline` 的 `join()`。**只傳給 socket 不算數**——socket 逾時只管單次讀寫；測試以「卡住的客戶端 + `timeout=0.2`」證明 0.4 秒內返回、錯誤訊息含「逾時」、不拋例外，且卡住的 worker 是具名 daemon。符合。
2. **絕不阻塞啟動／網頁回應／監控輪詢**：更新檢查一律經 `Application.trigger_update_check` → `check_update(background=True)` → 單一 worker 的 pool（`ediaad-update`）。三個路徑各有測試：`start()` 在更新服務卡住時 1 秒內返回、`/`、`/api/version`、`/api/status` 三個請求都回 200 且 1 秒內、`run_monitor_round()` 完成一輪。另有 `_update_inflight` 防止「頁面連續載入把工作堆進佇列」。符合。
3. **失敗一律靜默，只記狀態**：`_perform` 把所有例外收斂成 `UpdateState.error` 並寫入快取；`_deliver` 吞掉回呼的例外；測試斷言 stdout／stderr 為空、沒有 ERROR／CRITICAL 日誌、且狀態仍被記錄（包含背景路徑）。符合。
4. **網頁載入立即回快取**：`background=True` 立刻回傳快取（`source="cache"`）或沒有快取時的 `pending`，工作交給 executor；`/api/version` 每次載入都排程但受去抖動限制、並以 `_update_inflight` 去重。測試以「記錄型執行器」確定「立即返回」與「背景真的做了什麼」兩件事可分別斷言。符合。
5. **去抖動 5 分鐘**：以快取檔的 `checked_at` 判斷（**跨程序有效**，有「刪掉快取就會重查」的測試）；299 秒不查、300 秒（含）查、`force=True` 可繞過。符合。
6. **可完全關閉**：`enabled=False` 時 0 筆請求、0 個背景工作、`source="disabled"`，且 `force=True` 也無效；有快取時仍顯示上次已知值（關閉不等於抹掉資訊）。`Application` 的閘門另有獨立測試（沒有網址／已關閉 → 回 `False`、不排工作、不建立狀態）。符合。

另核對「只顯示不下載不安裝」：`parse_manifest` 只讀顯示欄位，測試斷言假 HTTP 的請求 URL 集合恰為 manifest 位址（下載位址從未被請求）、執行前後 `tmp_path` 唯一的差別是快取檔。`fetch_catalog` 是**使用者明確要求**的 catalog 更新（資料，不是程式本體），且完全委派 TASK-017 的流程。

## 品質 Review

- **與 TASK-017 的重複實作在 Review 中被抓到並移除（本張最重要的品質成果）**：第一版 `fetch_catalog` 自己寫了「下載 → 寫檔」，而 `markets.catalog` 早就有 `update_catalog`（版本相同不發請求、schema 驗證、原子取代、`UpdateResult` 狀態回報）。更嚴重的是第一版**少了 schema 驗證**——伺服器給什麼就寫什麼，可能寫出 `load_catalog` 讀不回的檔案。已改為完全委派，只保留 `(狀態碼, 內容)` → `client(url) -> payload` 的介面轉接；副作用（回傳 `UpdateResult`、失敗是狀態）記錄為 A-1／A-2 待追認。
- **六條約束都是「可證的性質」而不是註解**：每一條都有對應的注入邊界（假 HTTP／假時鐘／記錄型執行器／卡住的 Event）與失敗斷言；變異矩陣再把每一條的實作細節逐一還原並確認至少一個測試失敗（46／46）。
- **時間完全由呼叫端注入**：`update.py` 的原始碼不含 `datetime.now(`／`time.time(`（有測試以原始碼斷言），`checked_at` 由 `now` 決定；這讓去抖動與 `checked_at` 的邊界可以精確固定。
- **「還沒有新版本」的四種處境互不混淆（F-003 的延伸）**：`_update_message` 與 `version.js` 的 `missingText` 把「尚未檢查」「檢查中」「已關閉」「檢查失敗」分開；失敗且有舊資料時另外顯示「上次檢查失敗」。**這是實作期間被測試逼出來的**：沒有這條紀律時，一次失敗的檢查會顯示成「尚未檢查」，使用者會以為服務還沒試過。
- **`source` 的語意被收緊**：`network`（這次檢查的結果）／`cache`（顯示的是**過期**快取、背景正在補）／`pending`（還沒有資料、正在檢查）／`disabled`；去抖動時沿用上次的標記，不把「五分鐘內剛拿到的結果」說成過期快取。
- **失敗也記 `checked_at`（A-12）**：失敗會把「這次嘗試的時間」寫進快取，因此失敗在五分鐘內同樣不會重試——避免服務不可用時每次頁面載入都打一次。這是刻意的取捨（停用時的行為另由 `enabled` 控制），已記錄。
- **介面轉接與錯誤分層一致**：`http_get` 把 4xx／5xx 當「有回應」（回狀態碼）而不是例外，與 `license.http_post` 同構；`urllib` 在函式內才 import，因此 `import ediaad.update` 不會拉進網路模組。
- **資源與生命週期**：更新檢查用單一 worker 的 `ThreadPoolExecutor`（`ediaad-update`），`close()` 以 `wait=False` 關閉（worker 是 daemon、單次檢查最多 5 秒）；`_get_with_deadline` 逾時後留下的 worker 也是 daemon，不會阻止行程結束（測試直接斷言 `daemon is True`）。
- **環境變數的邊界**：`EDIAAD_UPDATE_URL` 只由服務入口（`launcher._run_service`）讀取，`Application.create()` 不讀——因此測試天然隔離（不會因為開發機設了環境變數就意外連網），TASK-036 的 `serve` 必須沿用同一條路徑（A-4）。
- **變異矩陣的強度**：46 個變異在凍結版**全數被抓到**；第一階段抓到的 3 個存活者都是**真實的測試缺口**（路由層重複規則遮蔽 trigger 的閘門、未走到的後備路徑、被訊息文字遮蔽的前端專屬行），全部以「移除重複規則」或「補強斷言」處理，沒有為了全殺而放寬實作。
- **測試品質**：全程離線（唯一的真實網路嘗試是刻意設計的變異 `U25`，用來證明「注入的 client 真的有被使用」）；以真實 HTTP 請求觀察 `/api/version`；`tmp_path` 觀察檔案層面的副作用；Node 只載入真實 `version.js`。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 與 Task 文件的簽章落差 | advisory（需追認） | `TASK-032.md` 寫 `fetch_catalog(...) -> dict`；實作回傳 TASK-017 的 `UpdateResult`（`status`／`local_version`／`remote_version`／`message`／`requests`） | 追認：回傳 `UpdateResult` 才不需要把 TASK-017 的狀態資訊壓扁成 dict，也才能讓「版本相同不發請求」的 AC-038 行為透過本 API 可達。SPEC 第 5 節只列函式名，不需改 | 已記錄（`tests/test_update.py` 的 Cycle 7 六個案例） |
| A-2 | 錯誤語意 | advisory | `fetch_catalog` 的失敗是 `UpdateResult.status == "failed"` 而非例外（第一版設計是丟 `SourceError`） | 追認：與 `check_update` 的靜默紀律一致，也與 TASK-017 既有契約一致；呼叫端（TASK-036）應以狀態決定顯示 | 已記錄（`test_catalog_failure_is_reported_and_writes_nothing` 等） |
| A-3 | 跨 Task 缺口（AC-057 的另一半） | advisory（**需在後續 Task 處理**） | 租約 `features` 的 `has_feature(lease, "update")` 在執行期還沒有生產呼叫端：`update_enabled` 目前只來自 `settings.json` → 缺少 `update` 功能的租約仍會檢查更新 | TASK-036 的 `serve` 應在啟動驗證（`check_lease`）之後把 `has_feature(lease, "update")` 併入更新開關（或直接以 `enabled=` 傳入），否則 AC-057 的分級只是設定檔選項 | 待辦（已記於 `STATE.md` 待決事項；本張已驗證 `enabled=False` 的所有行為） |
| A-4 | 服務入口的責任 | advisory（需追認） | `EDIAAD_UPDATE_URL` 由 `launcher._run_service` 讀取並寫入 `Application.update_url`；`Application.create()` **刻意不讀**環境變數 | TASK-036 的 `serve` 子命令必須重用 `serve_main`／`_run_service`，否則更新檢查在 CLI 路徑不會被啟用；同時追認「環境變數只由入口讀取」這條慣例 | 待追認（`test_version_endpoint_never_checks_without_a_configured_url` 固定了預設不連網） |
| A-5 | SPEC 資料生命週期 | advisory（需追認） | 新增產物 `<home>/update.json`（更新快取）尚未列在 SPEC 第 5 節的產物清單 | 與 TASK-025 的 `watchlist.json` 一併在下次 SPEC 修訂補列 | 待追認（已記於 `STATE.md`） |
| A-6 | 狀態值域 | advisory | `UpdateState.source` 多了第四個值 `pending`（報告只列 `network`／`cache`／`disabled`，但寫的是「至少」） | 保留：沒有 `pending` 就得分別用「假裝是快取」或「假裝沒檢查」來表示「正在檢查」，兩者都會誤導使用者。前端與 API 都已呈現 | 已記錄（`test_background_check_without_cache_reports_pending` 等） |
| A-7 | 資源取捨 | advisory | 硬上限以「每個請求一個 worker 執行緒」換來；逾時後該執行緒會留到請求真的結束（daemon，不阻止行程） | 這是「不被慢速伺服器拖住」的必要成本；若日後有大量並行檢查（目前同一時間只有一個），可改用單一長駐 worker ＋ 佇列 | 已記錄（`test_blocking_http_returns_within_the_deadline` 斷言 daemon） |
| A-8 | 關閉語意 | advisory | `Application.close()` 對更新 pool 用 `shutdown(wait=False)` | 可接受：worker 是 daemon、單次檢查最多 5 秒；`wait=True` 會讓關閉被網路拖住 5 秒，違背「關閉要快」。已有測試證明關閉後 pool 不再接受工作 | 已記錄（`test_close_shuts_down_the_update_pool`） |
| A-9 | 測試環境衛生（**已處理**） | advisory | 先前被中斷的 pytest 留下 **53 個** `ediaad.launcher --serve` 孤兒程序（`--home /tmp/pytest-of-…`、PPID 變成 `systemd --user`、已存活 1.6～3.2 小時） | 已全部 `SIGTERM` 收掉（0 殘留）。launcher 測試的 teardown 在 pytest 被殺時不會自動收子程序——TASK-037 的全套驗證前後應檢查殘留程序並清理（或在測試中改用 process group／確保 pid 檔清理） | **已清理**；已記於 `STATE.md` |
| A-10 | 真實瀏覽器檢查 | advisory（**未執行**） | SPEC 第 7 節要求人工檢查；本環境無瀏覽器自動化。版本頁四種狀態（尚未檢查／檢查中／已關閉／檢查失敗）的實際畫面仍未目視 | 交付前在 Chrome（Wayland）打開版本頁並以「無網址」「已關閉」「指向不存在網域」三種設定各看一次 | 待辦（替代驗證已記錄於 TDD） |
| A-11 | 契約用語 | advisory | `check_update` 的「永不拋例外」只涵蓋網路與內容失敗；呼叫端參數錯誤（如 `cache_path=None`）仍會拋例外 | 已把 docstring 限定為「網路或內容失敗永不拋例外」並說明理由（安靜吞掉會讓更新永遠不檢查卻沒人知道） | **已修正並記載**（`update.py` 的 `check_update` docstring） |
| A-12 | 失敗的重試節奏 | advisory | 失敗也會寫入 `checked_at`，因此失敗後五分鐘內不重試（即使服務已恢復） | 保留：避免服務不可用時每次頁面載入都打一次；若要「失敗快速重試」，需要另一套退避策略與新的 AC，不應在沒有需求時先加 | 已記錄（`test_http_500_keeps_the_previous_display_values` 同時固定了失敗後的狀態） |
| A-13 | 流程記載 | advisory（非程式） | （a）第一次變異矩陣被中斷時留下一個未還原的變異，測試立刻以 6 個失敗顯示出來；工具已加 `SIGTERM`／`SIGINT`／`atexit` 還原，並在每次中斷後先跑測試確認原始碼完整。（b）`fetch_catalog` 的重複實作是在等待矩陣時複查相鄰模組才發現的 | 已全部修正並如實記載（TDD 的「如實記載」第 1、2 點） | **已記載** |

## 修正與重審

- 第 1 輪 Spec Review：AC-059 的七項宣稱逐條符合；AC-057 的「停用」在本張做到「`enabled` 語意正確＋可完全關閉」，租約 `features` 的判定呼叫端列為 A-3（TASK-036）。
- 第 1 輪品質 Review 修正 **1 處重複實作**：`fetch_catalog` 改為完全委派 TASK-017 的 `update_catalog`（連帶讓 catalog 的 schema 驗證與「版本相同不發請求」回到單一實作），並改寫 Cycle 7 的測試（新增 `current`／`local-newer` 兩個案例）。
- 依變異檢查處理 **3 個真實存活者**：移除路由層與 `trigger_update_check` 重複的網址判斷（單一真相）並補 `test_trigger_update_check_decides_alone`；補 `test_trigger_uses_the_home_default_cache_path` 讓後備路徑真的被走到；把前端斷言收緊成專屬行「更新檢查：已關閉」。另改寫 1 個因修正而失效的變異（`R01`）。
- 修正 1 處契約用語（A-11 的 docstring 範圍）與 1 處測試夾具基準（`start()` 已排程 vs 測試從乾淨狀態觀察）。
- 重審：重跑單檔（**47 passed**）、七個 web／launcher 迴歸檔（**219 passed**）、全套（**966 passed**）、兩個流程驗證器（exit 0），並在凍結版重跑變異矩陣（**46／46 偵測到，0 存活、0 無效**）；重讀 `update.py`（六條約束的每一步）、`Application.trigger_update_check`／`close`、`routes.version`／`_update_message`、`version.js` 與 `launcher._run_service` 的接線。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-059 七項逐條符合；AC-057 的另一半列為 A-3 交 TASK-036）
- 品質 Review：passed（無 blocking；`fetch_catalog` 的重複實作已移除，A-1／A-2／A-4／A-5 需追認，A-3 待 TASK-036，A-6～A-8／A-11／A-12 已記錄，A-9 已清理，A-10 待人工檢查，A-13 為流程記載）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1／A-2（追認 `UpdateResult` 契約）、A-3（需 TASK-036 接上 `features` 分級）、A-4（TASK-036 必須重用服務入口）、A-5（Spec 補產物清單）、A-6（保留 `pending`）、A-7／A-8（資源與關閉的刻意取捨）、A-10（交付前人工檢查）、A-12（失敗退避需新 AC 才擴充）、A-13（已記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：真實 `/v1/latest`／`/catalog.json` 端點未驗證（TASK-034／037）；版本頁四態的實際畫面未人工檢查；長期執行的狀態老化與執行緒殘留未量測；失敗後五分鐘內不重試（A-12）；`features` 分級在執行期尚未生效（A-3）
