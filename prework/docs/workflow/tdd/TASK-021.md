# TASK-021 測試紀錄

- task_id：TASK-021
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-web-sse sha256:855a7ad90c1d679acb61de85289ae7b2ee905d32705c79d16269d95dc1ed89dd
- alternative_reason：無自動測試的替代；但 SPEC 第 7 節人工檢查第 2 項（「事件從引擎到瀏覽器畫面」的端到端延遲）**未執行**——見「未執行或受阻」
- Task／Spec 版本：TASK-021 / SPEC-001 v0.4
- 測試邊界：對真實服務的 SSE 串流（標準庫 HTTP client 建立連線後逐行讀取，`http.client` 會自動解 chunked）與 `GET /api/events` 的 JSON；`SSEHub`／`format_sse` 以單元測試觀察誰收到、誰沒收到與幀格式。完全離線。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-020 的交付物，全套 **613 passed**（本張完成後為 637 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/web/sse_hub.py` | `25468d0b` | 新增：`format_sse`、`event_id_for`、`SSEHub` |
| `ediaad/web/routes.py` | `5113f6ee` | 修改：串流路由（`stream_route`／`stream_for`／`stream_events`）與事件歷史端點 |
| `ediaad/web/server.py` | `775b99fb` | 修改：`_send_stream`（chunked 逐幀輸出、客戶端斷線隔離） |
| `ediaad/app.py` | `dde4b028` | 修改：`hub` 由佔位改為真正的 `SSEHub`；新增 `make_emit()` |
| `ediaad/web/static/events.js` | `42bbccc2` | 新增：`EventSource` 訂閱、以 id 去重、歷史載入與篩選 |
| `ediaad/web/static/index.html` | `0022e0d2` | 修改：即時提醒區塊（含 label 的篩選表單、`aria-live` 狀態、事件清單） |
| `ediaad/store.py` | `09b5ed3e` | 修改：**允許跨執行緒使用**（見下「整合缺陷」） |
| `tests/test_web_sse.py` | `eb756e08` | 新增：22 個測試 |
| `tests/test_store.py` | `df9c02e0` | 修改：新增多執行緒與反轉區間兩個測試（35 passed） |

## 接線時發現的真實缺陷（本張最重要的一項）

**SQLite 連線預設綁定建立它的執行緒**。`Application.create()` 在主執行緒開資料庫，而 HTTP
handler 跑在 `ThreadingHTTPServer` 的工作執行緒 → `GET /api/events` 回 500：

```
sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread.
The object was created in thread id ... and this is thread id ...
```

這是**只有接線才會出現**的缺陷（TASK-018 的 35 個測試全綠，因為它們都在同一個執行緒裡
用 store）。價值在於：錯誤訊息在回應中被正確地收斂成固定字串（不外洩內部細節），同時
伺服器日誌留下完整 traceback——這兩件事都是 TASK-020 建立的機制，這次真的派上用場。

**修正**（改了 TASK-018 的 `store.py`）：`open_store` 以 `check_same_thread=False` 開啟，
並由 `Store` 內部的 `RLock` 序列化所有存取。單一連線 ＋ WAL ＋ 序列化，對「每分鐘幾次
寫入、偶爾查詢」的本機服務足夠，且不必處理「每個執行緒一條連線、關閉時跨執行緒」的麻煩
（`sqlite3` 對 `close()` 也有同樣的執行緒限制）。

**先紅後綠**：先在 `tests/test_store.py` 補 `test_the_store_can_be_used_from_several_threads`
（4 個執行緒各寫 5 筆並讀取）→ 紅；再改 `store.py` → 綠。變異 M20（拿掉
`check_same_thread=False`）與 M21（拿掉鎖）都會被抓到。

## Cycle 1：幀格式、推播中樞與串流端點（AC-042，真實 Red → Green）

- 測試：`format_sse` 產生合法的 `id:`／`event:`／`data:` ＋空行；含換行的內容仍是**單一合法幀**（見下）；沒有 id 時不產生 `id:` 行；`event_id_for` 對同一事件穩定、對不同事件不同；`SSEHub` 廣播給**每一位**訂閱者、取消訂閱後不再收到、**同一 id 不重複廣播**、`client_count` 正確增減（`unsubscribe` 幂等）；**慢速訂閱者不得阻塞發布端**；`GET /api/events/stream` 在 **1 秒內**送達 `event: alert` 且 `data` 可還原為同一事件、`Content-Type` 為 `text/event-stream; charset=utf-8` 且 `Cache-Control` 含 `no-cache`、沒有事件時持續送 `: keep-alive`，共 12 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_web_sse.py -q` | 1 | `12 failed`：`ModuleNotFoundError: No module named 'ediaad.web.sse_hub'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `12 passed in 3.10s` | snap-2026-09-24-ocaievo-web-sse／2026-09-24 |

- 實作：`sse_hub.py`（`format_sse`／`event_id_for`／`SSEHub`）、`routes.stream_route`／`stream_for`／`stream_events`、`server._send_stream`（chunked）、`Application.hub`。
- **先做技術驗證再寫測試**：SSE 需要「無 Content-Length 的持續輸出」，我用一個小腳本先確認「`Transfer-Encoding: chunked` ＋ 手動 chunk 框架」能被 `http.client` 自動解塊並用 `readline()` 逐行讀取，之後才寫正式的串流測試——省下在正式測試裡反覆試錯。
- **「1 秒內」的量測要排除訂閱競態**：客戶端收到標頭時，伺服器端可能還沒訂閱（訂閱發生在生成器第一次迭代）。測試因此先 `wait_until(hub.client_count == 1)` 再開始計時，量到的才是真正的推播延遲。
- **`data:` 的多行處理是防禦性程式碼（如實記載）**：`json.dumps` 會把換行**轉義**，所以序列化後的文字永遠不含真實換行——`format_sse` 內部的逐行拆分在構造上無法從這個函式觸及。我保留了那兩行（若日後改成縮排輸出就會用到），但把測試改成斷言**可達的不變式**：含換行的 payload 仍然是單一合法幀、沒有裸 `\r`、能還原成同一個值。**不宣稱那段程式碼被測試覆蓋。**
- **如實記載的測試錯誤**：我第一版把多個 `data:` 行用空字串串接，但 SSE 規格是**以 `\n` 串接**（客戶端行為），所以還原出的 JSON 少了換行。是我的測試錯，不是實作錯。

## Cycle 2：事件歷史、斷線重連與引擎接線（AC-042，真實 Red → Green）

- 測試：`GET /api/events` 回傳落地的事件且**逐欄等於寫入值**；依商品與時間區間篩選（各別與合併）；無符合條件（未知商品／區間外）回 200 空清單；區間反轉回 400 且訊息含「不得早於」；時間格式錯誤回 400；**資料庫不可用回 503**；以 `Last-Event-ID` 重連後**同一 id 不再收到**（且新事件帶新 id）；**一個訂閱者中途斷線不影響其他人**（`client_count` 正確下降、另一個仍收到後續事件、伺服器不留 traceback）；`Application.make_emit()` 會把事件推入 SSE；首頁載入 `events.js` 且篩選表單有 `label`；`events.js` 使用 `EventSource` 與串流路徑，共 10 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `8 failed`：`/api/events` 不存在（404）、`make_emit` 不存在、`events.js` 不存在、資料庫不可用時回 500 | 同上／2026-09-24 |
| Green | 同上 | 0 | `22 passed in 12.74s` | 同上／2026-09-24 |

- 實作：`routes.events`（薄轉接 `store.query_events`；store 為 `None` 時 `_HttpError(503, ...)`）、`stream_events`（訂閱 → `queue.get(timeout=1.0)` → 逾時送 `KEEP_ALIVE_FRAME`；`finally` 取消訂閱）、`Application.make_emit`、`static/events.js` 與首頁區塊。
- **`Last-Event-ID` 的處理方式（設計決定）**：`SSEHub` 對**每一個 event id 只廣播一次**，因此重連的客戶端在傳輸層就不可能收到已顯示過的事件——路由不需要保存「每個客戶端看到哪裡」。重連期間漏掉的事件由 `GET /api/events` 補齊，前端以 id 合併（`events.js` 的 `seen` 集合）。這比在 hub 裡做重播緩衝簡單，且不會與儲存層的權威資料重複。
- **發布端絕不阻塞**：`publish` 由監控執行緒呼叫，慢速或已死的客戶端只會讓自己的佇列滿；滿了就**丟棄**該幀（歷史端點補得回來）。測試同時斷言「佇列不會超過上限」與「六次發布在 0.5 秒內完成」。
- **反轉區間回 400 的實作位置**：我選擇把檢查放進 `store.query_events`（而不是網頁層），與 TASK-015 的 `fetch_ex_rights` 一致——「結束不得早於開始」是查詢 API 的輸入規則，屬於儲存層。這改了 TASK-018 的模組並在其測試檔補了一個案例。

## Cycle 3（補測）：把兩個存活變異變成可偵測

首次變異檢查有 2 個存活者，都是**我的測試不夠強**（不是等效變異）：

1. **M3（事件 id 不穩定）**：變異讓「缺少去重鍵」的 fallback 加上 `id(payload)`。我的穩定測試寫成兩次字面值呼叫，而**CPython 會重用剛被回收的臨時 dict 的記憶體位址**，兩次因此拿到同一個 `id()` → 僥倖通過。修正：改成先建立兩個 dict 並**同時保持存活**（`is not` 斷言），再比較 id → M3 立刻被抓到。這是「測試不只要寫對，還要避免語言的巧合」。
2. **M6（佇列滿時阻塞發布端）**：變異把 `put_nowait` 換成 `put(timeout=5)`——因為 `queue.Full` 仍被既有的 `except` 接住，**斷言全部成立**，只是每次丟棄要等 5 秒（整個測試從 0.1 秒變成 25 秒）。這暴露我的測試只看結果、沒看**時間**。修正：加上「六次發布必須在 0.5 秒內完成」的量測 → M6 立刻被抓到。

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 幀不含 `id:` 行 | 被抓到 |
| M2 | 幀不以空行結束 | 被抓到 |
| M3 | 事件 id 不穩定（fallback 加物件身分） | **首次存活 → 補「兩個 dict 同時存活」的斷言後被抓到** |
| M4 | 事件 id 少用一個去重欄位 | 被抓到 |
| M5 | 不抑制重複的 event id | 被抓到 |
| M6 | 佇列滿時阻塞發布端 | **首次存活 → 補發布耗時斷言後被抓到** |
| M7 | `unsubscribe` 不移除訂閱者 | 被抓到 |
| M8 | `client_count` 永遠回 0 | 被抓到 |
| M9 | 串流不送 keep-alive | 被抓到 |
| M10 | 串流結束不取消訂閱 | 被抓到 |
| M11 | 歷史端點忽略商品篩選 | 被抓到 |
| M12 | 歷史端點忽略時間區間 | 被抓到 |
| M13 | 資料庫不可用時回 500 | 被抓到 |
| M14 | 串流不用 chunked 框架 | 被抓到 |
| M15 | 串流不攔客戶端斷線 | 被抓到 |
| M16 | `emit` 不推播 | 被抓到 |
| M17 | `emit` 推播錯誤內容 | 被抓到 |
| M18 | 首頁不載入 `events.js` | 被抓到 |
| M19 | 前端不用 `EventSource` | 被抓到 |
| M20 | `store` 不允許跨執行緒 | 被抓到 |
| M21 | `store` 不用鎖保護共用連線 | 被抓到 |

工具紀律：整行比對、`count(frm) == 1` 才執行、每次變異後立即還原並比對檔案 sha256；每次執行有 90 秒上限（串流測試掛住時視為「偵測到（掛住）」並如實標示）。矩陣在**最終版檔案**上重跑過，21／21 全數被抓到；還原後 `ediaad/web/sse_hub.py` `25468d0b`、`routes.py` `5113f6ee`、`server.py` `775b99fb`、`app.py` `dde4b028`、`store.py` `09b5ed3e` 與變異前一致，兩檔共 `57 passed`。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_web_sse.py -q` | 0（`22 passed in 12.76s`） | snap-2026-09-24-ocaievo-web-sse |
| 相關回歸（儲存層，含新增的多執行緒案例） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_store.py -q` | 0（`35 passed in 4.86s`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`637 passed in 49.48s`） | 同上 |
| 未使用匯入掃描 | `ocaievo/`：AST 粗檢 `ediaad/` | 0（無發現） | 同上 |
| 變異後還原驗證 | 同本張單檔與相關回歸 | 0（`57 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- **SPEC 第 7 節人工檢查第 2 項（事件從引擎到瀏覽器畫面的端到端延遲）未執行**：需要 Chrome（Wayland）人工操作，本環境沒有瀏覽器自動化。自動測試已覆蓋「伺服器 → HTTP 客戶端」的 1 秒內推播與「引擎 → hub」的接線，但**沒有**量測「引擎 → 真實瀏覽器畫面」的總延遲。此項留待交付前的人工檢查（與 TASK-022 的 K 線圖人工檢查一併執行），並已在 Review A-4 記錄。
- 已知邊界（記錄）：
  - **事件歷史只讀**：`Store.record_event` 的寫入路徑仍在監控端（TASK-025 接線），web 不寫入（本張邊界明訂）。
  - **SSE 沒有重播緩衝**：重連期間漏掉的事件由 `GET /api/events` 補齊；前端以 id 合併。這是刻意的取捨（見 Cycle 2 的設計決定），代價是前端必須記得在 `onopen` 時重新載入歷史。
  - **`sse_hub` 的 id 去重是無界之外的有限集合**：`recent_limit`（預設 512）之外的 id 會被淘汰；若同一個非常舊的事件被重新發布（正常流程不會，因為引擎自己也去重），理論上會被再次廣播。已記錄。
  - **`store.py` 的執行緒模型改變**（TASK-018 的交付物）：單一連線 ＋ `check_same_thread=False` ＋ `RLock`。這對本機服務足夠，但**不是**為了高並發設計的；若日後寫入量大增，應改為連線池或每執行緒連線（並重新處理 `close()` 的跨執行緒限制）。
  - `events.js` 沒有自動化測試（沒有 JS 執行環境）：只有「檔案存在、被首頁載入、包含 `EventSource` 與串流路徑、表單有 label」的內容斷言。前端行為靠人工檢查（見上）。
  - 沒有事件數量上限或自動清理（報告第 8.2 節已列為已知限制）。
- 未涵蓋：K 線圖（TASK-022）、參數預覽與範例學習（TASK-023）、歷史回看（TASK-024）、監控清單與系統狀態頁（TASK-025）、啟動器（TASK-026）、通知管道（TASK-027）。
