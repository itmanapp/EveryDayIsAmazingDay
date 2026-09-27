# TASK-021：SSE 即時提醒與事件歷史篩選

- id：TASK-021
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-042"]
- depends_on：["TASK-020"]
- test_evidence：["docs/workflow/tdd/TASK-021.md"]
- review_evidence：["docs/workflow/reviews/TASK-021.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：命中經去重後推入 `SSEHub.publish`，所有已連線的 `GET /api/events/stream` 連線在 1 秒內收到一個含 `event: alert` 與 `data:` JSON 的 SSE 幀（同一事件帶穩定 `id`）；以 `Last-Event-ID` 重連後，已去重事件的同一 `id` 不會被重播，頁面也不重複顯示；`GET /api/events?symbol=&start=&end=` 依商品與時間區間回傳事件清單（資料來自 TASK-018 已落地的儲存層 `query_events`），無符合條件時回 200 與空清單；`Content-Type` 為 `text/event-stream; charset=utf-8` 且 `Cache-Control: no-cache`。
- 本張不做：不做 K 線圖（TASK-022）、參數預覽與範例學習（TASK-023）、歷史回看（TASK-024）、監控清單管理與系統狀態／版本頁（TASK-025）、啟動器（TASK-026）、通知管道（TASK-027）、授權頁；不在網頁層重算去重或重新實作偵測（沿用 TASK-018 的跨程序去重與 TASK-008 的偵測結果）；不引入 WebSocket 或任何第三方推送套件；不把事件寫入路徑搬進 web（web 只讀）。
- 每個 AC 在本張負責的範圍：AC-042 全部（連線後 1 秒內收到事件、斷線重連不重複顯示已去重事件、事件歷史可依商品與時間區間篩選）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-042、第 5 節 `ediaad/web/`（`sse_hub`）與 `ediaad/store.py`（`query_events`、`seen_keys`、`record_event`）、第 6 節效能（SSE 推播 1 秒內）與可及性；`docs/architecture/ENGINEERING-REPORT.md` 第 6.3 節（SSE 為標準庫可實作的單向推播）與第 5.9 節提醒去重（去重鍵為「商品、週期、規律 ID、事件開始時間」，用時間而非索引）；`docs/workflow/CONTEXT.md` 的「SSE」與「提醒去重鍵」。
- 模組與公開介面：新增 `ediaad/web/sse_hub.py`：`format_sse(payload, event="alert", event_id=None) -> bytes`（純函式，產生合法的 `id:`／`event:`／`data:` 幀並正確處理多行 JSON）與 `SSEHub`（`subscribe() -> queue.Queue`、`unsubscribe(q)`、`publish(event: dict) -> None`、`client_count`）；`ediaad/web/routes.py` 新增串流端點與歷史端點；`ediaad/app.py` 的 `Application` 持有單一 `SSEHub`，並把 `monitor.run_once` 的 `emit` 接到 `hub.publish`（沿用既有可注入 emit，引擎不改行為）。
- 預計觸及的檔案：`ediaad/web/sse_hub.py`、`ediaad/web/routes.py`、`ediaad/web/static/events.js`（前端 `EventSource` 訂閱、重連與清單渲染）、`ediaad/web/static/index.html`、`ediaad/app.py`、`tests/test_web_sse.py`；實作前重新查證。
- 必要環境／依賴：標準庫 `http.server`、`queue`、`threading`、`json`；瀏覽器原生 `EventSource`；人工檢查需 Chrome（Wayland）與已啟動的服務；測試完全不需網路。

## 測試計畫

- 測試公開邊界：對真實服務的 SSE 串流（以標準庫 HTTP client 建立連線後逐行讀取）與 `GET /api/events` 的 JSON；`SSEHub` 本身以多訂閱者的單元測試觀察誰收到、誰沒收到。
- 第一個失敗行為與預期斷言：先寫「連上 `/api/events/stream` 後呼叫 `hub.publish({"symbol": "BTCUSDT", ...})`，在 1 秒內讀到含 `event: alert` 的行且 `data` 可被 `json.loads` 還原為同一事件」。實作前同一測試對端點取得 404；實作後預期 200 與幀內容一致。
- 後續例外／邊界情境：以 `Last-Event-ID` 重連後不重播同 `id` 的幀，且前端不重複渲染已去重事件；單一訂閱者中途斷線（`ConnectionResetError`／`BrokenPipeError`）不得讓其他訂閱者或監控執行緒失敗，`client_count` 需正確增減；`format_sse` 對含換行的訊息輸出多行 `data:` 且不產生非法幀；`start` 晚於 `end` 的篩選回 400 可讀錯誤；不存在的商品代號回 200 空清單而非 500；未發布事件時連線維持以 `: keep-alive` 註解行保活且不中斷。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_web_sse.py -q`；相關回歸 `.venv/bin/python -m pytest -q`。
- 非程式任務的替代驗證與理由：不適用（本張為程式任務，推播與篩選皆可自動驗證）；但「事件從引擎到瀏覽器畫面」的端到端延遲需以 Chrome 人工檢查補足並記錄實際量測值（SPEC 第 7 節人工檢查第 2 項）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-020 的交付物（全套 613 passed）；本次新增 `ediaad/web/sse_hub.py`、`ediaad/web/static/events.js` 與 `tests/test_web_sse.py`，並修改 `ediaad/web/routes.py`、`ediaad/web/server.py`、`ediaad/app.py`、`ediaad/web/static/index.html`、`ediaad/store.py`（跨執行緒修正，見 Review B-1）與 `tests/test_store.py`（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-021.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-021.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-web-sse` sha256:855a7ad90c1d679acb61de85289ae7b2ee905d32705c79d16269d95dc1ed89dd（原始碼樹，56 檔）；新增 `ediaad/web/sse_hub.py` `25468d0b…`、`ediaad/web/static/events.js` `42bbccc2…`、`tests/test_web_sse.py` `eb756e08…`；全套 `637 passed`
- 取消、重開或變更原因：無
