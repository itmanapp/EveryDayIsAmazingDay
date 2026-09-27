# TASK-025 測試紀錄

- task_id：TASK-025
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-web-watchlist sha256:8e3a252c4cb202d11ef51f847c10687766c55064500170b970e04bf98da5eee8
- alternative_reason：**部分替代**——三種授權狀態的實際畫面與下拉選單的操作手感無法在無瀏覽器自動化的環境驗證；本張以「Node 載入四支真實前端模組驗證純函式（清單轉型、狀態文字、三態標籤、啟用主體）」＋「端點以真實 HTTP 請求觀察 JSON 與狀態碼」＋「`POST /api/watchlist` 之後以注入時鐘與假來源跑**真的下一輪** `run_once`」作為替代；Chrome（Wayland）的人工檢查仍**未執行**（見「未執行或受阻」）。另外**原 Red 執行的輸出未留存**（見同一節第 2 點）：本紀錄以受控複本重建新增公開邊界的 Red，並以凍結版變異矩陣逐項釘住每個新行為。
- Task／Spec 版本：TASK-025 / SPEC-001 v0.4
- 測試邊界：（1）`GET /api/instruments/search`、`GET/POST /api/watchlist`、`GET /api/status`、`GET /api/version`、`GET /api/license`、`POST /api/license/activate` 的 JSON 與狀態碼（真實 HTTP，假來源注入，全程離線）；（2）寫入 `watchlist.json` 後**下一輪輪詢**真的使用新清單；（3）監控執行緒的啟動／冪等／停止；（4）事件落地到 `Store` 與跨輪去重；（5）來源分派的 `cache_dir`／`max_age` 能力轉接；（6）四支前端模組的純函式（Node 載入真實檔案）；（7）首頁接線。租約以假 `UpdateState`／假租約／假 HTTP 客戶端注入，不連網。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-031 的交付物，全套 **888 passed**（本張完成後為 **919 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `e37eec7cf2cd17238cb489a9e0d338c078cbed1482f59624ed60f3514131314a`（87 個檔案，即 TASK-031 的 `checked_version`）。
- TDD 不適用的理由與替代驗證（若有）：見「未執行或受阻」第 1 點（真實瀏覽器）與第 2 點（原 Red 輸出未留存）。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/web/routes.py` | `c64258d7` | 修改：新增 `instruments`（`GET /api/instruments/search`）、`watchlist`／`save_watchlist`（`GET`／`POST /api/watchlist`）、`status`、`version`、`license_status`、`activate_license`；`DEFAULT_SEARCH_LIMIT`／`MAX_SEARCH_LIMIT`／`WATCHLIST_KEYS`／`REAPPLY_URL`／`LICENSE_STATES` |
| `ediaad/app.py` | `d36c989d` | 修改：監控執行緒（`start_monitor`／`stop_monitor`／`monitor_running`／`run_monitor_round`）、逐商品來源分派與能力轉接（`fetch_for`）、`_record_instrument`／`instrument_status`／`last_poll_at`／`last_result`／`monitor_error`／`status_payload`；`make_emit` 追加 `store.record_event`；`shutdown()` 先停監控 |
| `ediaad/monitor.py` | `82908123` | 修改：`validate_config` 由 `load_config` 抽出（公開、可重用）；新增 `save_config`（先驗證再原子寫入） |
| `ediaad/license.py` | `a690e550` | 修改：新增 `http_post`（標準庫 `urllib`，授權服務的預設 HTTP 客戶端；可注入替換） |
| `ediaad/web/static/watchlist.js` | `c801d72b` | 新增：`buildWatchlistBody`／`parseInstrumentRow`／`describeWatchlist`／`describeSearchResults`／`attachWatchlist` 等純函式與黏著層 |
| `ediaad/web/static/status.js` | `c9f177c5` | 新增：`describeStatus`（最後輪詢時間、逐商品來源與錯誤、問題清單、未輪詢時的「尚未輪詢」） |
| `ediaad/web/static/version.js` | `858ffa16` | 新增：`describeVersion`（目前／最新版本、發佈日期、說明、尚未檢查） |
| `ediaad/web/static/license.js` | `812c1870` | 新增：`STATE_LABELS`／`describeLicense`（三態＋error 的文字化）／`buildActivateBody`／`attachLicenseForm` |
| `ediaad/web/static/index.html` | `0b9ca974` | 修改：新增「監控清單」「系統狀態」「版本」「授權」四個區塊與四支 script |
| `tests/test_web_watchlist_status.py` | `062e19f4` | 新增：31 個測試（含 3 個 Node 純函式斷言與 3 個假來源／假來源能力類別） |

## Cycle 1：下拉搜尋與監控清單讀寫（AC-047，9 個測試）

- 測試：`GET /api/instruments/search?q=台積&source=fake` 回 200，`items[0]` 同時有 `symbol="2330"` 與 `display_name="台積電"`，且**每一項**的兩個欄位都非空（下拉選單不需自行輸入代號），關鍵字原樣傳給來源（`queries == [("台積", 20)]`）；`limit=2` 真的限制筆數並原樣傳給來源，`limit` 為 `0`／`-1`／`51`／`abc` 各回 400 且訊息指出 `limit`；缺 `q` 回 400 且訊息指出 `q`，未知 `source` 回 400 且訊息含該 id；**單一來源失敗不影響結果**（回 200、`items` 為空、`errors` 含失敗原因）；第一次寫入前 `GET /api/watchlist` 回 `configured=false`、`instruments=[]`、預設輪詢間隔 `60`、路徑以 `watchlist.json` 結尾、`monitor_running=false`；`POST /api/watchlist` 成功後檔案的 `poll_interval_seconds=30`、`app.watchlist` 已更新，且**下一輪** `run_monitor_round()` 的 `processed == 1`、假來源被問到 `("2330","1d")`、`instrument_status` 記到 `data_source="cache"`、`last_poll_at` 有值；新增／移除商品與變更週期都生效；7 種不合法內容（來源不支援的週期、清空 `instruments`、缺 `interval`、空 `symbol`、未知 `source_id`、輪詢間隔 `0`、未知鍵）各回 400 並指出對應欄位／鍵名，且**設定檔內容一位元都沒變**；設定檔所在目錄不可寫時回 502 且訊息含「寫入」。
- 實作：`routes.instruments`（薄轉接：`_require_query`／`_search_limit` → `Source.search`）、`routes.watchlist`／`save_watchlist`（`_watchlist_mapping` 併入變更 → `monitor.validate_config` → `monitor.save_config` → `app.watchlist`）、`monitor.validate_config`／`save_config`。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 見「Red 的重建」 | — | 端點不存在（404）：`test_instrument_search_*` 與 `test_watchlist_*` 皆失敗 | 尚未有端點／2026-09-24 |
| Green | `.venv/bin/python -m pytest tests/test_web_watchlist_status.py -q -k "instrument_search or watchlist_is_unconfigured or watchlist_save"` | 0 | `9 passed, 22 deselected in 6.04s` | snap-2026-09-24-ocaievo-web-watchlist／2026-09-25 |

- **驗證與寫入只有一份規則**：路由不自己檢查「週期是否被來源支援」或「清單是否為空」，而是把併好的候選交給 `monitor.validate_config`——與 CLI 讀設定檔是同一套規則（`supported_intervals` 由來源查詢，不是全域常數）。因此**設定檔損毀時端點不會覆蓋原內容**（驗證在寫入之前），這一點由「7 種壞輸入後檔案逐字不變」直接斷言。
- **監控清單不放在 `settings.json`**：`settings.json` 的鍵集是 TASK-019 的凍結契約（7 鍵），塞進 `instruments` 會讓那個契約分岔；本張改以 `watchlist.json` ＋ `monitor.save_config`（先驗證、暫存檔、`os.replace`）落地，與 CLI 的設定檔是**同一個檔案**。
- **「下一輪生效」不是宣稱**：測試在 `POST` 之後真的呼叫 `service.app.run_monitor_round()`，並斷言假來源收到的請求與 `instrument_status` 的內容，而不是只看記憶體裡的物件。

## Cycle 2：系統狀態、版本與事件落地（AC-048，5 個測試）

- 測試：尚未輪詢時 `/api/status` 回 `last_poll_at=null`／`last_result=null`／`monitor_running=false`（不是 500、也不是空白）；輪詢後 `last_poll_at` 有值、`last_result` 四項計數正確（`processed=1`、`alerted=1`）、逐商品項目同時帶 `source_id`（設定裡指定的）與 `data_source`（來源回報的）且 `error=null`；來源失敗時 `processed=0`、`warnings>=1`、該商品的 `error` 含上游訊息；同一事件連跑兩輪 → `alerted` 為 `1`、`0`，`Store` 內只有一筆事件且去重鍵只有一個（**跨重啟去重**由 TASK-018 的 `Store` 提供，這是它的第一個服務端消費者）；沒有 `UpdateState` 時 `/api/version` 的 `latest_version`／`released_at`／`notes` 皆為 `null`、`update_available=false`、訊息含「尚未檢查」；注入假 `UpdateState` 後四個欄位如實呈現且 `update_available=true`。
- 實作：`Application.run_monitor_round`（`monitor.run_once` ＋ `state=self.store`，並填 `last_result`／`last_poll_at`／`monitor_error`）、`Application.status_payload`、`Application.make_emit`（`store.record_event`）、`routes.status`、`routes.version`。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 見「Red 的重建」 | — | `GET /api/status`／`/api/version` 不存在（404） | 同上／2026-09-24 |
| Green | `.venv/bin/python -m pytest tests/test_web_watchlist_status.py -q -k "status_reports or events_are_written or version_page"` | 0 | `5 passed, 26 deselected in 3.54s` | 同上／2026-09-25 |

- **F-003 的紀律延伸到狀態頁**：「還沒輪詢」不是「輪詢後沒有事件」——`last_poll_at` 為 `null` 而不是某個假時間，前端顯示「尚未輪詢」。版本頁同理：「還沒檢查更新」與「檢查了、已是最新」在 API 上分別是 `latest_version=null` 與 `update_available=false`，訊息只有前者說「尚未檢查」。
- **`data_source` 的來源是來源回報的 `attrs`**，不是把 `source_id` 抄一次；狀態頁因此能區分 `cache`／`binance`／`cache-stale`（測試以假來源同時斷言兩者不同）。

## Cycle 3：授權頁與網頁啟用（AC-066／AC-052／AC-057，8 個測試）

- 測試：沒有 `lease.json` 時 `/api/license` 回 **200**、`state="inactive"`、`has_lease=false`、`reapply=true` 且 `reapply_url` 非空、`features=[]`、`days_remaining=null`（首次啟用表單的狀態）；有效期內回 `state="active"`、`reapply=false`、`expires_at` 逐字 `"2026-10-24T12:00:00Z"`、`days_remaining>0`、`features` 如實、`key_id` 如實、`reapply_url` 指向**頁面上真的存在的錨點**；落地撤銷標記 → `state="revoked"` 且訊息含「撤銷」，改成已過期的租約 → `state="expired"` 且訊息含「重新申請」，兩者 `reapply=true`；`lease.json` 損毀時仍回 200、`state="error"`、訊息含「無法解讀」（**不得 500**）；「重新申請」連結的片段必須真的存在於首頁（`test_reapply_link_points_at_an_anchor_that_exists`）；`POST /api/license/activate` 成功時以真實 `machine_fingerprint()` 送給授權服務、`key_id` 回傳正確、`lease.json` 原子落地（**契約檢查與簽章驗證重用 TASK-030 的 `activate`，網頁層不重寫一份**）；未設定 `EDIAAD_LICENSE_URL` 回 400 且訊息指名副檔名，缺 `key`／空白 `key` 也回 400；4xx（無效密鑰）→ 400 且**不落地任何租約檔**，5xx → 502；第二次啟用即為**更換密鑰**，以新租約為準。
- 實作：`routes.license_status`（`lease_status` 為唯一狀態來源；`LICENSE_STATES` 把 `unactivated` 對外映射為 `inactive`）、`routes.activate_license`（`_license_url` ＋ 可注入的 `app.license_http`／`app.license_public_key` ＋ `license.activate`）、`ediaad/license.py` 的 `http_post`。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 見「Red 的重建」 | — | `GET /api/license`／`POST /api/license/activate` 不存在（404） | 同上／2026-09-24 |
| Green | `.venv/bin/python -m pytest tests/test_web_watchlist_status.py -q -k "license_page or reapply_link or activate_endpoint"` | 0 | `9 passed, 22 deselected in 5.44s`（含 1 個同時屬於 Cycle 4 的 Node 輔助測試，故群組案例數為 8） | 同上／2026-09-25 |

- **四態＋error 的用語是單一映射**：`lease_status` 回 `unactivated`／`active`／`expired`／`revoked`，對外只有 `LICENSE_STATES` 一個轉換點（`unactivated` → `inactive`），前端 `STATE_LABELS` 再給文字。測試同時檢查狀態字串與**文字內容**（「首次啟用」「有效期內」「已過期」「重新申請」「撤銷」「無法解讀」），因此「只靠顏色」不可能通過。
- **啟用端點是薄轉接**：簽章範圍、30 天長度、機器比對、狀態碼分層全部沿用 TASK-030 的 `activate`。測試以真的 `machine_fingerprint()` 與測試夾具公鑰注入 `app.license_public_key`（`LICENSE_PUBLIC_KEY` 目前是 fail-closed 的 32 位元組佔位，**任何簽章都會被拒絕**），TASK-033 產生 Worker 金鑰後只需換掉那個常數。
- **「還沒啟用」不是錯誤**：缺檔回 200 `inactive`；**租約損毀也不是 500**，而是 `state="error"` 並附可讀原因——兩者都不會讓授權頁整頁失效。

## Cycle 4：監控執行緒、來源能力轉接與前端（9 個測試）

- 測試：監控執行緒啟動後真的輪詢（等到 `last_poll_at` 有值、`/api/status` 的 `monitor_running=true`、假來源真的被抓過），重複啟動是幂等的，停止後不留名為 `ediaad-monitor` 的執行緒，沒有監控清單時 `start_monitor()` 回 `False` 且 `monitor_error` 說明原因；支援 `cache_dir`／`max_age` 的來源會拿到 `app.cache_dir` 與設定的 `900`（並且 `data_source="cache-stale"` 如實呈現）；`monitor.save_config` 是公開 API，不合法（輪詢間隔 `0`）時丟 `ConfigError` 且**不寫檔**；四支前端模組以 Node 載入真實檔案後：清單主體會去空白並轉型（`poll_interval_seconds` 由字串 `"30"` 變數字 `30`）、缺 `symbol`／缺 `interval`／空清單／輪詢間隔 `0` 各自丟出**指出欄位名**的錯誤、清單／搜尋／狀態／版本／授權的文字（含「尚未輪詢」「尚未檢查」「有效期內」「已過期」「重新申請」「首次啟用」「無樣本」語氣）與啟用主體（去空白、空字串丟錯）逐項正確；首頁含八個必要的 `id` 標記、四個 script 標記，且四支 JS 以正確的 `Content-Type` 提供。
- 實作：`Application.start_monitor`／`stop_monitor`／`monitor_running`（`Event.wait` 等待，停止不必等一輪）、`Application.fetch_for`（以 `inspect.signature` 判斷來源是否支援 `cache_dir`／`max_age`，不在這裡寫死來源名稱）、`watchlist.js`／`status.js`／`version.js`／`license.js`（載入時不碰 DOM 的 IIFE）、`index.html`。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 見「Red 的重建」 | — | 四支靜態檔 404、首頁未接線；Node 輔助測試的 fixture 取不到檔案（3 errors） | 同上／2026-09-24 |
| Green | `.venv/bin/python -m pytest tests/test_web_watchlist_status.py -q -k "helpers_trim or page_text_helpers or three_states or served_and_wired or cache_dir or stop_monitor or monitor_cannot or monitor_thread or save_config_validates"` | 0 | `9 passed, 22 deselected in 3.70s` | 同上／2026-09-25 |

- **兩條跨 Task 缺口在這裡收斂**：TASK-013／TASK-024 的 A-1「來源未依 `Instrument.source_id` 分派，且非 CSV 來源拿不到 `cache_dir`」——`fetch_for` 以商品設定的 `source_id` 取得來源，並以**能力探測**（`inspect.signature`）而不是來源名稱清單決定要不要傳 `cache_dir`／`max_age`；測試注入的類別刻意命名為 `cached`（不在任何清單裡）也能拿到快取目錄。
- **監控迴圈沿用引擎**：`run_monitor_round` 呼叫的就是 `monitor.run_once`（與 CLI `monitor --once` 同一條路徑），`emit` 是 `Application.make_emit`（通知管道 ＋ `store.record_event`），去重狀態是 `Store`（跨重啟）而非記憶體 `AlertState`。
- **可測性手法沿用 TASK-022／TASK-023**：可判斷的部分（轉型、格式化、狀態文字）都是純函式並以 Node 載入真實檔案驗證；留在瀏覽器裡的只有送出表單與把結果畫進畫面。

## Red 的重建（原始 Red 輸出未留存）

原始 Red 執行的輸出**沒有留存下來**（測試檔案是在實作同一輪內逐步寫成並修正的；中途的失敗輸出被後續指令覆蓋）。為避免用「事後補跑」冒充當時的 Red，本紀錄採取兩件事：

1. **受控複本重建（僅涵蓋新增公開邊界）**：把實作樹複製到 `/tmp/red25`，移除 TASK-025 新增的**六個端點註冊與四個靜態檔**（`routes.py` 截到 TASK-025 區塊之前、刪除四支 JS），在複本中執行本張測試檔：

| 階段 | 命令（工作目錄 `/tmp/red25`） | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Red（重建） | `.venv/bin/python -m pytest tests/test_web_watchlist_status.py -q` | 1 | `24 failed, 3 passed, 3 errors in 16.78s`；六個新端點全部 404、四支靜態檔 404、Node fixture 取不到檔案（3 errors） |

   複本**只**還原了路由與靜態檔（`app.py`／`monitor.py` 的新增行為與既有程式交織，無法在不製造假狀態的前提下切除），因此 3 個通過的測試正是監控執行緒與設定驗證那 3 個（`test_monitor_cannot_start_without_a_watchlist`、`test_stop_monitor_really_ends_the_thread`、`test_save_config_validates_before_writing`）——**這 3 個的 Red 由上表的 24 個失敗與隨後的變異矩陣共同代表**，不宣稱複本重建涵蓋它們。
2. **變異矩陣作為反空洞證據**：凍結版把每一個新行為逐一還原成「實作前等價」（`if False:`／改回舊值）並確認**至少一個測試失敗**（`routes.py` 15＋`app.py` 10＋`monitor.py` 2＋前端 5＋`REAPPLY_URL` 2＝35 個變異，33 個被抓到、2 個已證等價），比單一次 Red 更強地證明斷言真的綁在實作上。

## 變異測試（凍結版）

- 工具：`/tmp/mutate_task025.py`（整行替換、`count(frm) == 1` 才套用、每輪逾時 180 秒、跑完立即還原並比對 sha256、`flock` 確保單一行程、`PYTHONDONTWRITEBYTECODE=1` 避免 `.pyc` 的 mtime 假偵測）。
- 矩陣：**35 個變異**（`routes.py` 17、`app.py` 10、`monitor.py` 2、`watchlist.js` 2、`status.js` 1、`version.js` 1、`license.js` 2），涵蓋搜尋關鍵字來源與 `limit` 上下限、來源選擇與單一來源失敗的隔離、`display_name` 回退、候選清單併入、驗證與寫入的順序、寫入失敗的狀態碼、`update_state`／`update_available`、租約讀取與狀態映射、啟用密鑰的解析與服務網址檢查、來源分派、`cache_dir` 能力探測、錯誤記錄、`data_source` 讀取、`last_poll_at`／`last_result`、去重狀態來源、事件落地、無清單時的啟動、執行緒停止、`save_config` 的驗證、前端的空白／空清單／錯誤／三態文字，以及**重新申請連結的目標**。
- **編號 M06 於凍結前移除**：它要替換的舊行在前一輪重構後已不存在，實測 `count=0`（上一次含它的執行紀錄為 `INVALID`），留著只會讓矩陣多一筆無效項。
- **最終結果：33／35 偵測到；2 個判讀為等價，如實保留並說明**：
  - `M15`（`key = _body_text(payload, "key")` → `key = payload.get("key") or ""`）：缺 `key` 時前者在路由層丟 `ConfigError`（訊息指名 `key`），後者把空字串交給核心 `activate`，核心同樣丟 `ConfigError`（密鑰不能是空的）→ 兩者對外都是 400，測試只斷言狀態碼。這是**同一條契約的兩個入口**，不是測試缺口；若要區分訊息就得多斷言一次訊息內容（訊息內容目前由核心擁有，屬 TASK-030 的契約）。
  - `M27`（`validate_config` 的「必須是 JSON 物件」型別檢查 → `if False:`）：非映射輸入在下一行的「缺少鍵」檢查就會被擋下，錯誤訊息不同但同為 `ConfigError`。同樣是**縱深防禦**（型別檢查讓訊息更可讀），保留。
- 兩處是**在 Review 修正後補入**的：`M35`（`REAPPLY_URL` 改空字串）與 `M36`（改回舊的、指向不存在頁面的值），兩者都被抓到（`27 passed, 4 failed`／`28 passed, 3 failed`）。
- 逐輪輸出形如 `30 passed, 1 failed`（31 個測試；Node 群以 `-k` 只跑相關 3 個測試，故顯示 `2 passed, 1 failed`）。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `.venv/bin/python -m pytest tests/test_web_watchlist_status.py -q` | 0 | `31 passed in 17.47s` |
| `.venv/bin/python -m pytest -q` | 0 | `919 passed, 2 warnings in 150.64s` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |
| 凍結版檔案樹 | — | sha256 `8e3a252c4cb202d11ef51f847c10687766c55064500170b970e04bf98da5eee8`（92 個檔案） |

## 如實記載的測試／實作錯誤（開發過程）

1. **測試自己送不出中文查詢字串**：`GET /api/instruments/search?q=台積` 讓 `http.client` 丟 `UnicodeEncodeError`（請求列必須是 ASCII）。已改用 `urllib.parse.quote`（端點本身沒問題）。
2. **假來源的候選名稱讓 `limit` 測試不只一筆**：`"台"` 只命中 1 筆，`limit=2` 的斷言因此失敗；已把候選改成「台積電／台塑／鴻海」（都含「台」），同時保留只命中 1 筆的 `"台積"` 案例驗證關鍵字原樣傳遞。
3. **快取轉接測試的序列太短**：`build_series(total=40)` 在植入偏移 30 ＋ 21 根時 `IndexError`；已改為 `total=120`。
4. **`save_config` 的測試用了未註冊的來源 id**：`validate_config` 會拿來源的 `supported_intervals` 驗週期，`"fake"` 未註冊 → 改為已註冊的 `"csv"`（這是實作正確、測試寫錯）。
5. **啟用端點的兩個注入點**：租約的 `machine` 必須是**真實** `machine_fingerprint()`（核心會比對），且必須注入 `app.license_public_key`（`LICENSE_PUBLIC_KEY` 是 fail-closed 佔位，任何簽章都會被拒）——兩者都是 TASK-025 刻意留的接縫（TASK-033 產生 Worker 金鑰後替換常數即可），不是為了讓測試通過而放寬實作。
6. **Review 抓到一個真實缺陷（已修正）**：`REAPPLY_URL` 原為 `/static/license_page.html#reapply`，但**那個頁面不存在**（`GET` 會 404，頁面上也沒有 `reapply` 錨點）——AC-066 的「重新申請連結」等於壞掉。已改為指向首頁授權區塊的既有錨點 `/#license-heading`，並新增 `test_reapply_link_points_at_an_anchor_that_exists`（把片段拿去首頁找 `id="…"`）＋`M35`／`M36` 兩個變異釘住；TASK-035 提供正式重新申請頁時再改欄位值。

## 未執行或受阻

1. **Chrome（Wayland）人工檢查未執行**（無瀏覽器自動化）：下拉搜尋的操作手感、監控清單編輯、三種授權狀態的實際畫面與「不以顏色為唯一區分」的目視確認。替代驗證：端點以真實 HTTP 請求驗證 JSON／狀態碼，前端以 Node 驗證純函式（含三態標籤與文字），首頁接線以內容斷言。仍待交付前在真實瀏覽器完成一次。
2. **原 Red 執行的輸出未留存**：本張的測試是在同一輪內寫成並隨實作修正的，中途的失敗輸出沒有落檔；已以「受控複本重建（24 failed／3 passed／3 errors，範圍僅新增公開邊界）」＋「35 個變異的逐項反空洞證據」替代，並在上一節完整揭露重建範圍。
3. **`attachWatchlist`／`attachLicenseForm` 的實際 DOM 流程未自動測試**（需要瀏覽器或 DOM 模擬器；本專案不引入新依賴）。
4. **監控執行緒的長時間穩定性未驗證**：測試只跑一輪（`interval=1` 秒、等待單次輪詢）並立即停止；數小時的輪詢漂移、來源暫時失敗的重試節奏不在自動測試範圍。
5. **`EDIAAD_LICENSE_URL` 指向的真實授權服務未驗證**：本張以假 HTTP 客戶端注入（TASK-033 才會提供 Worker；端到端由 TASK-037 驗收）。
