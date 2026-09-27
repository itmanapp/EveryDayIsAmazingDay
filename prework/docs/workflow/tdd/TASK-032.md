# TASK-032 測試紀錄

- task_id：TASK-032
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-update sha256:9831e0acb59672b1c9af4bae7c419aad8438f814f67abb5c74028d3f92bb3d55
- alternative_reason：**部分替代**——「不阻塞網頁回應」在真實瀏覽器上的體感與更新服務的真實端點（`/v1/latest`、`/catalog.json`）無法在此環境驗證；本張以「注入的假 HTTP（可計數、可卡住、可回 500／404、可回壞 JSON）＋注入的執行器／假時鐘」在單元層逐條固定六條約束，並以真實 HTTP 請求對真實服務實例斷言「三個路徑都不被卡住的更新檢查阻塞」，再以 Node 載入真實 `version.js` 驗證四種狀態文字。TASK-034 提供端點後由 TASK-037 做端到端驗收。
- Task／Spec 版本：TASK-032 / SPEC-001 v0.4
- 測試邊界：（1）`ediaad/update.py` 的 `check_update`／`parse_manifest`／`load_cache`／`save_cache`／`fetch_catalog`（時間與 HTTP 全部注入，`tmp_path` 觀察快取檔與「是否多出其他檔案」）；（2）`Application` 的更新排程與執行緒池（`trigger_update_check`／`close`）；（3）`GET /api/version` 的欄位與訊息（真實服務、真實 HTTP 請求）；（4）`version.js` 的純函式（Node 載入真實檔案）；（5）**不連向任何真實位址**（唯一的例外是變異 `U25`：刻意拿掉注入的 client，驗證測試會抓到它）。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-031 與 TASK-025 的交付物，全套 **919 passed**（本張完成後為 **966 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `8e3a252c4cb202d11ef51f847c10687766c55064500170b970e04bf98da5eee8`（92 個檔案，即 TASK-025 的 `checked_version`）。
- TDD 不適用的理由與替代驗證（若有）：見「未執行或受阻」第 1 點（真實端點與瀏覽器）。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/update.py` | `c7123a0e` | 新增：`UpdateState`（顯示欄位＋`source`＋`error`＋`checked_at`）、`parse_manifest`、`load_cache`／`save_cache`（原子）、`check_update`（六條約束）、`fetch_catalog`（轉接 TASK-017）、`http_get`（標準庫客戶端，`urllib` 延後 import）；`DEFAULT_TIMEOUT`／`DEFAULT_DEBOUNCE_SECONDS`／`UPDATE_SOURCES` |
| `ediaad/paths.py` | `94042f3e` | 修改：新增 `update_state_path`（`<home>/update.json`）並補進產物清單與 `__all__` |
| `ediaad/app.py` | `3a2e4dc3` | 修改：`update_url`／`update_cache_path`／`update_http`／`update_executor`、`trigger_update_check`（非阻塞、幂等、`_update_inflight` 防堆積）、`_update_pool_ref`（單一 worker 的 pool）、`_absorb_update_state`；`start()` 排程一次、`close()` 關閉 pool |
| `ediaad/launcher.py` | `b9f58eb7` | 修改：`_run_service` 由 `EDIAAD_UPDATE_URL` 設定 `app.update_url`（環境變數只由服務入口讀取，`Application` 本身不讀，測試才天然隔離） |
| `ediaad/web/routes.py` | `4cf12eb5` | 修改：`version` 端點新增 `catalog_version`／`source`／`error`／`update_enabled` 與 `_update_message`（四種「還沒有新版本」不得混淆）；排程與否交給 `trigger_update_check` 單獨決定（不在路由重寫同一條規則） |
| `ediaad/web/static/version.js` | `a1bc9c92` | 修改：`missingText` 與 `update_enabled === false` 分支（尚未檢查／檢查中／已關閉／無法取得＋有舊資料時的「上次檢查失敗」） |
| `tests/test_update.py` | `b9e61082` | 新增：42 個測試函式／47 個案例（含 2 個 Node 純函式斷言、2 個假 HTTP 類別、1 個記錄型執行器、3 個服務整合 fixture） |

## Cycle 1：manifest 解析、快取與「只顯示不下載不安裝」（11 個案例）

- 測試：合成 manifest（`schema`／`version`／`released_at`／`min_supported`／`notes`／`catalog_version`／`catalog_url`／`url`／`sha256`／`size`）→ `latest_version == "0.4.0"`、七個顯示欄位逐一比對、`source == "network"`、`error is None`、`checked_at` 為 `2026-10-02T12:00:00Z`、**恰一筆 GET（帶 5.0 秒逾時）**、快取往返相等；缺檔／壞 JSON／非物件／非 UTF-8 的快取一律回 `None`（**不得讓版本頁壞掉**），`save_cache` 拒絕非 `UpdateState`、`UpdateState.from_json` 拒絕非物件與非字串欄位且不寫檔；`parse_manifest` 對 `schema != 1`、缺 `version`、缺 `released_at`、非物件各有**指名欄位**的錯誤；無法解析的內容（壞 JSON／空字串／HTML）→ 靜默記狀態（stdout／stderr 空、無 ERROR 日誌）且**仍然寫入狀態**；`url`／`sha256` 指向的下載位址**從不被請求**，執行前後唯一的差別只有快取檔。
- 實作：`UpdateState`／`parse_manifest`／`load_cache`／`save_cache`、`check_update` 的同步成功路徑。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_update.py -q` | 1 | `1 error in 0.59s`：`ImportError: cannot import name 'update_state_path' from 'ediaad.paths'`（模組與路徑都還不存在） | 尚未有 `update.py`／2026-09-25 |
| Green | 同上 | 0 | `47 passed in 5.86s`（凍結版；開發過程中的分段結果見下表） | snap-2026-09-24-ocaievo-update／2026-09-25 |

## Cycle 2：約束 1「逾時上限 5 秒」（2 個測試）

- 測試：預設逾時就是 **5.0 秒**且原樣傳給 HTTP 客戶端；面對**會卡住**的客戶端（`threading.Event.wait(30)`）在 `timeout=0.2` 時 **0.4 秒內**返回、錯誤訊息含「逾時」、不拋例外，且同一個值同時給 socket 與硬上限；卡住的 worker 具名 `ediaad-update-http` 而且是 **daemon**（不會阻止行程結束）。
- 實作：`_get_with_deadline`——把請求放進 worker 執行緒再 `join(timeout)`。**只把 `timeout=` 傳給 socket 不夠**：那只管單次讀寫，慢速滴水的伺服器可以拖過它；硬上限必須由 join 給。

## Cycle 3：約束 3「失敗一律靜默，只記狀態」（3 個測試）

- 測試：客戶端丟 `SourceError` → 不拋例外、訊息進 `error`、狀態仍寫入快取、stdout／stderr 空、沒有 ERROR／CRITICAL 日誌；HTTP 500 → **保留上一份的顯示欄位**（`latest_version`／`notes` 不變）且 `source == "cache"`；HTTP 404 → 錯誤訊息含狀態碼。
- 實作：`_perform` 的 `try／except Exception`（成功與失敗都會把 `checked_at`／`source`／`error` 落地）。

## Cycle 4：約束 4「先回快取、背景檢查」（6 個測試）

- 測試：有過期快取 + `background=True` + 記錄型執行器 → **立刻**得到快取的內容（`source == "cache"`）、HTTP 客戶端**一次都沒被呼叫**、執行器收到 1 個工作；沒有快取時立刻回 `source == "pending"`；手動執行被交付的工作 → 恰一筆 GET、快取更新為新版、`on_result` 收到 `source == "network"` 的結果；背景失敗同樣靜默並經回呼回報；**背景也受五分鐘去抖動**（不排工作、不呼叫回呼）；沒有注入執行器時使用具名 daemon 執行緒（以輪詢等待背景完成）。
- 實作：`check_update` 的 `background`／`executor`／`on_result` 分支與 `_submit`／`_deliver`。

## Cycle 5：約束 5「去抖動 5 分鐘」（5 個測試）

- 測試：快取 `checked_at` 在 **299 秒前** → 0 筆請求且**沿用上次的來源標記**；**300 秒前**（邊界）→ 重新檢查、`checked_at` 更新；`force=True` → 即使剛檢查過也重查；**去抖動靠快取檔而非記憶體**（刪掉快取後同一組參數會再查一次）；模組原始碼不得出現 `datetime.now(`／`time.time(`（時間一律由呼叫端注入）。
- 實作：`UpdateState.is_stale(now, debounce_seconds)` 與 `check_update` 的前置判斷。

## Cycle 6：約束 6「可完全關閉」（3 個測試）

- 測試：`enabled=False` → **0 筆請求、0 個背景工作**、`source == "disabled"`、不拋例外；有快取時仍顯示上次已知值（`禁用 ≠ 把已知資訊抹掉`）；`enabled=False` 時 `force=True` 也**不得**繞過。
- 實作：`check_update` 的 disabled 分支（自行組出 `disabled` 狀態，不呼叫 `_perform`）。

## Cycle 7：`fetch_catalog` 與更新路徑（6 個測試）

- 測試：下載→**以 TASK-017 的 catalog schema 驗證**→原子安裝（`UpdateResult.status == "installed"`、`requests == 1`、寫出的檔案能用 `load_catalog` 讀回）；給 `remote_version` 且與本地相同 → **`status == "current"` 且 0 筆請求**（AC-038），較舊 → `local-newer` 且本地檔不被覆蓋；HTTP 500／內容不合法 → `status == "failed"` 且**不留任何檔案**；逾時在 0.4 秒內回來、同一個值給 socket。`update_state_path` 就是 `<home>/update.json`。
- 實作：`fetch_catalog` **完全委派** `markets.catalog.update_catalog`（本函式只把 `(狀態碼, 內容)` 轉成它要的 `client(url) -> payload`）。**這是本張最有價值的發現**：第一版自己寫了下載＋驗證＋寫檔，與 TASK-017 已有的流程重複（而且少了 schema 驗證，可能寫出 `load_catalog` 讀不回的檔案）——正是報告 F-001 的溫床；已改為單一實作（見「如實記載」第 1 點）。

## Cycle 8：服務整合（9 個測試）

- 測試：`start()` 在更新服務卡住時 **1 秒內**返回並真的把檢查排到背景（執行緒名 `ediaad-update`）；`/`、`/api/version`、`/api/status` 三個請求在更新服務卡住時都回 200 且 1 秒內返回；**監控輪詢**在同樣情況下完成一輪（`processed == 1`）；`/api/version` 第一次載入立即回（`pending`、0 筆網路請求）並排 1 個工作，第二次載入**不重複排程**（在進行中），背景完成後回 `source == "network"` 與新版本，第三次載入因去抖動不再檢查；沒有設定網址時**完全不連網**且訊息為「尚未檢查」；`update_enabled=False` → 訊息含「已關閉」且不排程，失敗狀態 → 訊息含「失敗」且**不含**「尚未檢查」，`pending` → 訊息含「進行中」（**四種處境互不混淆**）；`trigger_update_check` 自己就要判斷「沒有網址／已關閉／force 也無效」並回 `False`；`update_cache_path` 未設定時退回 `<home>/update.json`（不是安靜不檢查）；`close()` 之後預設 pool 已關閉（再提交會 `RuntimeError`）。
- 實作：`Application.trigger_update_check`／`_update_pool_ref`／`_absorb_update_state`、`start()`／`close()` 的接線、`routes._update_message`／`version`、`launcher._run_service` 的環境變數讀取。

## Cycle 9：版本頁文字（2 個測試，Node 載入真實 `version.js`）

- 測試：「尚未檢查」（無狀態）、「檢查中…」（`pending`）、「更新檢查：已關閉」（**專屬一行**，不能只靠訊息文字）、「無法取得（更新檢查失敗）」（有 `error` 且無資料、且不得出現「尚未檢查」）、有舊資料時額外顯示「上次檢查失敗：…」；`version.js` 以 200 與正確的 `Content-Type` 提供。
- 實作：`missingText` 與 `update_enabled === false` 分支。

## Red → Green 的實際順序

| 階段 | 命令（`ocaievo/`） | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_update.py -q` | 1 | `1 error in 0.59s`（`ImportError: update_state_path`；測試先寫、模組尚不存在） |
| Green 1（模組） | 同上 | 1 | `4 failed, 39 passed in 5.06s`（六條約束全綠；4 個 app／routes／前端尚未接線） |
| Green 2（服務與前端） | 同上 | 1 | `3 failed, 40 passed in 5.13s`（剩 3 個是測試自己的夾具基準：`start()` 先排過一次檢查） |
| Green 3 | 同上 | 0 | `43 passed in 4.92s` |
| Green 4（補強） | 同上 | 0 | `44 passed in 5.27s`（收緊逾時斷言＋`close()`／`pending` 覆蓋） |
| Green 5（catalog 委派） | 同上 | 0 | `45 passed in 5.34s` |
| Green 6（凍結版） | 同上 | 0 | `47 passed in 5.86s`（再補 2 個測試擊殺存活者） |

## 變異測試（兩階段：先殺存活者，再跑凍結版）

- 工具：`/tmp/mutate_task032.py`（整行／整段替換、`count(frm) == 1` 才套用、每輪逾時 180 秒、跑完立即還原並比對 sha256、`flock` 確保單一行程、`PYTHONDONTWRITEBYTECODE=1`，並在 **SIGTERM／SIGINT／`atexit` 時還原正在跑的變異**）。
- 矩陣：**46 個變異**（`update.py` 27、`app.py` 7、`routes.py` 7、`paths.py` 1、`version.js` 4），涵蓋逾時常數與 join 期限、HTTP 狀態碼判斷與訊息、例外範圍、失敗時保留顯示欄位與來源標記、`checked_at` 格式與有無、去抖動的邊界與方向、manifest 的 schema／必填／字串檢查、快取的非 UTF-8 與型別檢查、worker 逾時分支、關閉分支（含「有快取時仍顯示」與 `force`）、背景的三個注入點（executor／`on_result`／立即返回值）、catalog 的委派與版本參數、來源路徑的後備、app 的三個閘門（網址／開關／in-flight）、`close()` 的 pool 關閉、版本端點的觸發與四個欄位與四種訊息，以及前端四條文字分支。
- **第一階段抓到 3 個真實存活者，全部補強測試後擊殺**：
  1. `A01`（`trigger_update_check` 自己的「沒有網址／已關閉」閘門被拿掉）——存活的原因是**路由層重複寫了同一條 `update_url` 判斷**，把 trigger 的檢查遮住。已**移除路由層的重複規則**（單一真相）並補 `test_trigger_update_check_decides_alone`。
  2. `A06`（`update_cache_path or update_state_path(self.home)` 的後備被拿掉）——存活是因為 `create()` 永遠會設定該欄位，後備從未被走到。已補 `test_trigger_uses_the_home_default_cache_path`（以 `dataclasses.replace` 把欄位設成 `None`）。
  3. `V01`（`version.js` 的「已關閉」專屬行被拿掉）——存活是因為斷言只檢查「已關閉」三個字，而 `message` 文字「更新檢查已關閉」也會命中。已把斷言收緊成專屬行「更新檢查：已關閉」。
- 另有 1 個變異在修正後**失效**（`R01` 的目標行已隨「移除重複規則」消失，`count=0`），已改寫成新行的等價變異後重跑。
- **最終凍結版結果：46／46 全數偵測到（0 存活、0 無效）**；逐輪輸出形如 `46 passed, 1 failed`（Node 群以 `-k` 只跑版本頁測試，故顯示 `0 passed, 1 failed`）。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `.venv/bin/python -m pytest tests/test_update.py -q` | 0 | `47 passed in 5.86s` |
| `.venv/bin/python -m pytest tests/test_launcher_lifecycle.py tests/test_web_api.py tests/test_web_watchlist_status.py tests/test_web_sse.py tests/test_web_chart.py tests/test_web_match.py tests/test_web_preview_learn.py -q` | 0 | `219 passed in 120.86s`（含 `start()`／`close()` 的既有契約） |
| `.venv/bin/python -m pytest -q` | 0 | `966 passed, 2 warnings in 155.83s` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |
| 凍結版檔案樹 | — | sha256 `9831e0acb59672b1c9af4bae7c419aad8438f814f67abb5c74028d3f92bb3d55`（94 個檔案） |

## 如實記載的實作／測試／工具錯誤

1. **`fetch_catalog` 第一版與 TASK-017 重複實作（已修正，本張最重要的發現）**：第一版自己寫「下載 → 寫檔」，不只重複了 `markets.catalog.update_catalog` 已經做完的事（版本相同不發請求、schema 驗證、原子取代、狀態回報），還**少了 schema 驗證**——伺服器給什麼就寫什麼，可能寫出 `load_catalog` 讀不回的檔案。是在複查相鄰模組（等待變異矩陣時讀 `markets/catalog.py`）時發現的；已改為**完全委派**，只保留介面轉接（`(狀態碼, 內容)` → `client(url) -> payload`）。副作用：回傳型別是 TASK-017 的 `UpdateResult` 而非 TASK-032.md 寫的 `dict`，失敗是狀態而非例外（見 Review 的 A-1／A-2）。
2. **第一次變異矩陣被中斷時留下一個未還原的變異**：行程被終止時正好停在「已寫入變異、還沒還原」的窗口，原始碼留下 `source="cache"`（成功路徑），測試立刻以 6 個失敗顯示出來。已還原並為工具加上 `SIGTERM`／`SIGINT`／`atexit` 還原；**並且在每次中斷後先跑一次測試確認原始碼完整**，才繼續。
3. **測試夾具的基準被 `start()` 影響**：`Application.start()` 本來就會排一次更新檢查（那正是被測行為），但服務 fixture 之後才開始觀察網頁路徑，於是「第一次載入要排 1 個工作」的斷言一开始看到的是 2。已在 fixture 中清空記錄與 in-flight 旗標並說明理由（不是為了讓測試過關而放寬實作）。
4. **注入的狀態會被端點的排程蓋掉**：測「失敗／已關閉的呈現」時，端點又排了一次檢查並把 `update_state` 換成 `pending`；已把該測試的 `update_url` 清空（呈現路徑本來就不依賴網址），讓注入的狀態可被觀察。
5. **`source` 的語意被測試逼著定清楚**：第一版在「五分鐘內剛檢查過」時把來源改寫成 `cache`，於是「剛從網路拿到的新結果」與「過期的快取」不可區分。已改為：`cache` 專指「顯示的是**過期**快取、背景正在補」，去抖動時沿用上次的來源標記（`network`），並更新對應測試。
6. **逾時斷言第一版太鬆**：原本用 `timeout=0.05` 卻只斷言 `elapsed < 1.0`（容忍 20 倍超時）。已改為 `timeout=0.2`、`elapsed < 0.4`、並斷言**同一個值**同時傳給 socket（變異 `U03` 證明這樣才抓得到「join 期限寫錯」）。
7. **清理了 53 個孤兒測試服務**：先前被中斷的 pytest 留下 `python -m ediaad.launcher --serve --home /tmp/pytest-of-…` 子程序（PPID 已變成 `systemd --user`，時間戳 1.6～3.2 小時前）。已全部 `SIGTERM` 收掉（0 個殘留）；這也說明 launcher 的測試 teardown 在「pytest 被殺」時不會自動收子程序（見 Review 的 A-9）。

## 未執行或受阻

1. **真實更新服務與真實瀏覽器未驗證**：`/v1/latest` 與 `/catalog.json` 由 TASK-034 提供，真實下載的 catalog 內容、`ETag`／快取標頭與「實際上新版本」的顯示屬 TASK-037 的端到端驗收；版本頁在 Chrome（Wayland）的四種狀態畫面仍未人工檢查（SPEC 第 7 節）。
2. **長期行為未驗證**：五分鐘去抖動在長時間執行下的效果、更新服務持續不可用時的狀態老化（`checked_at` 會一直往後推）、以及服務連續運行數小時後的記憶體（每次檢查會建立暫時的 HTTP worker 執行緒，逾時後成為 daemon 直到請求結束）。
3. **`check_update` 的「永不拋例外」有範圍**：網路與內容失敗一律收斂成狀態，但**呼叫端參數錯誤**（例如 `cache_path=None`）仍會拋例外——這是刻意的（安靜吞掉會讓更新永遠不檢查卻沒人知道），已寫進 docstring 並在 Review 記錄。
4. **`enabled` 的來源仍是設定檔**：租約 `features` 的 `has_feature(lease, "update")` 分級在執行期還沒有生產呼叫端（TASK-036 的 `serve` 必須接上），因此 AC-057 的「缺少 `update` 時停用」目前只做到「`enabled` 參數語意正確＋可完全關閉」。
5. **`fetch_catalog` 的呼叫端尚不存在**：本張只交付可用的 API 與測試；實際的「下載並更新 catalog」按鈕／命令屬 TASK-036（本張不寫 UI、不排程 catalog 更新）。
