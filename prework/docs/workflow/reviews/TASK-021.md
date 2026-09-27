# TASK-021 Code Review

- task_id：TASK-021
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-web-sse sha256:855a7ad90c1d679acb61de85289ae7b2ee905d32705c79d16269d95dc1ed89dd
- Task／Spec 版本：TASK-021 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 SQLite 跨執行緒缺陷的修正與兩個存活變異的判讀）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `855a7ad90c1d679acb61de85289ae7b2ee905d32705c79d16269d95dc1ed89dd`；本張新增 `ediaad/web/sse_hub.py` `25468d0b…`、`ediaad/web/static/events.js` `42bbccc2…`、`tests/test_web_sse.py` `eb756e08…`；修改 `ediaad/web/routes.py` `5113f6ee…`、`ediaad/web/server.py` `775b99fb…`、`ediaad/app.py` `dde4b028…`、`ediaad/web/static/index.html` `0022e0d2…`、`ediaad/store.py` `09b5ed3e…`、`tests/test_store.py` `df9c02e0…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的已提交、未提交、新增檔案：上述九個檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`monitor.py`／`config.py`／`patterns.py`／`markets/*` 本張只呼叫未修改；**`store.py` 例外**（見 B-1）
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-042、第 5 節模組表（`ediaad/web/` 的 `sse_hub`、`ediaad/store.py` 的 `query_events`／`seen_keys`／`record_event`）、第 6 節效能（SSE 推播 1 秒內）與可及性、第 7 節測試策略與人工檢查第 2 項；`docs/architecture/ENGINEERING-REPORT.md` 第 6.3 節（SSE 為標準庫可實作的單向推播）、第 5.9 節與 F11（去重鍵）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-042 | `ediaad/web/sse_hub.py`、`routes.py`、`server.py`、`app.py`、`static/events.js`；`tests/test_web_sse.py` 22 個案例 | 符合 | A-1～A-5（advisory） |

逐條核對：

- **AC-042「命中經去重後推入 `SSEHub.publish`，已連線的串流在 1 秒內收到 `event: alert` 與 `data:` JSON」**：`Application.make_emit()` 是引擎（`run_once`）的 `emit` 接縫，會推入 hub；端到端測試量到「發布 → HTTP 客戶端讀到幀」的時間並斷言 < 1 秒（**並先等訂閱建立**，排除競態）。同一事件帶穩定 `id`（`event_id_for` 用 TASK-010／018 完全相同的四個去重欄位）。符合。
- **AC-042「以 `Last-Event-ID` 重連後同一 id 不會被重播、頁面不重複顯示」**：hub 對每個 id 只廣播一次，因此重連不可能收到已顯示的事件（測試：重連並帶 `Last-Event-ID` 後重新發布同一事件 → 只收到 keep-alive）；前端另有以 id 為鍵的 `seen` 集合與 `onopen` 時重新載入歷史（`events.js`），兩道防線互補。符合。
- **AC-042「事件歷史可依商品與時間區間篩選、無符合回 200 空清單」**：`GET /api/events?symbol=&start=&end=` 直接轉呼叫 `store.query_events`（含起訖端點、UTC 正規化比較由儲存層負責）；未知商品與區間外都回 200 與 `[]`。符合。
- **`Content-Type: text/event-stream; charset=utf-8` 與 `Cache-Control: no-cache`**：有斷言。符合。

## 品質 Review

- **B-1（blocking，已修正）——SQLite 連線跨執行緒使用**：`GET /api/events` 首次整合時回 500，根因是 `sqlite3` 連線**預設只能由建立它的執行緒使用**（`Application.create` 在主執行緒開檔、HTTP handler 在工作執行緒查詢）。TASK-018 的 35 個測試全綠卻完全看不到，因為它們都在同一個執行緒裡使用 store——**這是「只有接線才會出現」的缺陷**。修正：`check_same_thread=False` ＋ `Store` 內部的 `RLock` 序列化所有存取；並先在 `tests/test_store.py` 補多執行緒測試（紅）再修（綠），變異 M20／M21 證明兩者都被守住。
- **錯誤轉譯機制在真實缺陷中證明有效**：上述 500 的回應主體是固定的「內部錯誤（詳見伺服器日誌）」，金鑰與堆疊都沒有外洩，而伺服器日誌留下完整 traceback 讓我一次就定位問題。這是 TASK-020 的設計第一次在真實缺陷上被驗證。
- **「先做技術驗證再寫測試」**：SSE 需要「無 Content-Length 的持續輸出」，我先用一個小腳本確認 chunked ＋ 手動框架能被 `http.client` 解塊並逐行讀，才寫正式測試。這避免了在測試裡反覆猜 HTTP 框架的行為，也讓後續的除錯集中在真正的邏輯。
- **發布端絕不阻塞（監控執行緒的安全）**：`publish` 用 `put_nowait`，滿了就丟棄並記 warning（歷史端點補得回來）。這是「掃描迴圈不得被網頁拖慢」的具體保證，且以**時間**（六次發布 < 0.5 秒）而非僅結果斷言（M6 的收穫）。
- **`Last-Event-ID` 的取捨**：沒有做重播緩衝，而是靠「同一 id 只廣播一次」＋「歷史端點補齊」。理由：儲存層已經是事件的權威來源，在 hub 再放一份重播緩衝會出現兩份真相；代價是前端必須在 `onopen` 重新載入歷史（已在 `events.js` 實作並記錄）。
- **客戶端斷線的隔離**：寫入失敗只結束該條串流（`except (BrokenPipeError, ConnectionResetError, OSError)`），`finally` 取消訂閱，`client_count` 正確下降；測試同時斷言「另一個訂閱者仍收到後續事件」與「伺服器輸出沒有 traceback」。
- **可及性**：狀態以文字（`aria-live="polite"`）、篩選表單的三個欄位都有 `label`、事件清單是語意化 `<ul>`、`style.css` 已有 `:focus-visible`。有內容斷言（`for="`）。
- **依賴與邊界**：`sse_hub.py` 只用標準庫（`json`／`hashlib`／`queue`／`threading`／`collections`）；`routes.py` 只呼叫 `config`／`patterns`／`markets.calendar`／`store`；沒有第三方推送套件、沒有 WebSocket、web 層只讀事件（不寫入）。
- **測試品質**：串流測試用真實 HTTP 連線並逐行解析幀（不是 mock）；每次發布都先等訂閱建立（消除競態）；斷線、重連、慢速客戶端各有專門案例；錯誤路徑斷言狀態碼、`code` 與「不含堆疊」。**兩個存活變異都是測試強度問題**（語言的記憶體重用巧合、只看結果沒看時間），已補強而非宣布等效。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| B-1 | 正確性／整合 | **blocking（已修正）** | `ediaad/store.py`：SQLite 連線綁定執行緒，`GET /api/events` 在 `ThreadingHTTPServer` 的工作執行緒使用主執行緒建立的連線 → 500。觸發情境：任何跨執行緒使用 store 的路徑（web handler、未來的監控執行緒） | `check_same_thread=False` ＋ `RLock` 序列化存取；並補多執行緒測試 | **已修正並驗證**：`09b5ed3e…`；`test_the_store_can_be_used_from_several_threads`（先紅後綠）、`tests/test_web_sse.py` 的歷史端點測試；變異 M20／M21 被抓到 |
| A-1 | 跨 Task 缺口（沿用 TASK-013 A-1～020 A-1） | advisory（**需在後續 Task 處理**） | 引擎仍**沒有**在服務中執行：`Application.make_emit()` 提供了接縫，但沒有人呼叫 `run_once`；`Store` 的寫入端（`record_event`）也還沒接上。因此網頁目前只會顯示「沒有事件」 | TASK-025 應一次收斂：來源分派、市場別預設、日曆、除權息、金鑰狀態、catalog 對照、`Store` 讀寫接線與 `GET/POST /api/watchlist` | 待辦（已記於 `STATE.md` 待決事項） |
| A-2 | 狀態集合有限 | advisory | `SSEHub` 的 id 去重集合有上限（預設 512）；超出後被淘汰，理論上極舊的事件若被重新發布會被再次廣播（正常流程不會，因為引擎自己也去重） | 若日後需要更強的保證，可改為「同時查 `Store.seen_keys()`」（但那會讓推送路徑依賴資料庫，需權衡） | 已實作並記錄 |
| A-3 | 前端未自動化測試 | advisory | `events.js` 只有內容斷言（存在、含 `EventSource`、被首頁載入、表單有 label）；行為（重連、去重、篩選）靠人工檢查 | 交付前的人工檢查（SPEC 第 7 節第 2 項）應涵蓋：開兩個分頁、觸發事件、重新整理、切換篩選 | 待辦（交付前人工檢查） |
| A-4 | 未執行的必要檢查 | advisory（**如實記載**） | SPEC 第 7 節人工檢查第 2 項要求量測「引擎 → 瀏覽器畫面」的端到端延遲；本環境沒有瀏覽器自動化，**未執行** | 交付前以 Chrome（Wayland）人工檢查並記錄實際量測值；自動測試已覆蓋伺服器端 1 秒內推播 | 待辦（與 TASK-022 一併執行） |
| A-5 | 流程紀律 | advisory（非程式） | 兩個存活變異都是測試強度不足（CPython 記憶體重用巧合、只看結果沒看時間）；另有一處測試把 SSE 多行 `data:` 用空字串而非 `\n` 串接 | 已全部在 TDD 紀錄如實記載。教訓：時間相關的保證要用時間斷言；身分相關的比較要避免物件位址的巧合 | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-042 逐條符合；品質 Review 找到 **B-1（blocking）並修正**。
- 依變異檢查修正 2 處測試強度（事件 id 穩定性、發布端不阻塞的時間斷言）；依測試回饋修正 1 處斷言（`data:` 多行的 `\n` 串接）。
- 重審：重跑單檔（22 passed）、相關回歸（35 passed，含新增的多執行緒案例）與全套（637 passed）；重讀 `sse_hub.py`／`routes.py`／`server.py` 複查去重、串流生命週期、chunked 框架與錯誤轉譯。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-042 的四項宣稱逐條符合）
- 品質 Review：passed（B-1 已修正並重驗；無其他 blocking）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-025）、A-2（無現時需求）、A-3／A-4（交付前人工檢查）、A-5（流程記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：引擎尚未在服務中執行（事件寫入端未接線）；SSE 無重播緩衝（靠歷史端點補齊）；id 去重集合有上限；前端行為與端到端延遲待人工檢查；`store.py` 的執行緒模型改為單連線＋鎖（非為高並發設計）
