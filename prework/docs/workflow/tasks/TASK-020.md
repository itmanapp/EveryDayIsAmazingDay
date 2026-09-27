# TASK-020：Web 服務骨架與 API 對應核心函式

- id：TASK-020
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-041"]
- depends_on：["TASK-011", "TASK-018", "TASK-019"]
- test_evidence：["docs/workflow/tdd/TASK-020.md"]
- review_evidence：["docs/workflow/reviews/TASK-020.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：以 `ediaad.web.create_server` 啟動的本機服務只 bind `127.0.0.1`，監聽埠預設 8787（`server.socket.getsockname()` 可被斷言為 `127.0.0.1`）；`GET /` 回傳原生 HTML 靜態頁，JSON 端點（至少 `GET /api/health`、`GET /api/patterns`）可用；每個端點只做參數解析、呼叫既有核心函式（例如 `ediaad.patterns.NAMED_PATTERNS`、`ediaad.monitor.load_config`、`ediaad.config.load_settings`）與序列化，網頁層不含任何重複實作的運算；`EdiaadError` 子類別被轉成 400／404 並附 `{"error": {"code": ..., "message": ...}}` 的可讀訊息，非預期例外回 500 且回應主體不含 `Traceback` 或堆疊內容。
- 本張不做：不做 SSE 與事件歷史（TASK-021）、K 線圖（TASK-022）、參數預覽與範例學習頁（TASK-023）、歷史回看（TASK-024）、監控清單管理與系統狀態／版本頁（TASK-025）、啟動器與 `stop.sh`（TASK-026）、三管道通知（TASK-027）、授權頁（TASK-030 之後）；不重實作任何核心運算；不引入 `requirements.txt` 以外的依賴（不使用 Flask／FastAPI／uvicorn）；不 bind `0.0.0.0`、不對外開放、不做認證／HTTPS／CSRF。
- 每個 AC 在本張負責的範圍：AC-041 全部（僅 `127.0.0.1:8787` 綁定、靜態頁與 API 可用、每個操作對應既有核心函式且不重複實作、錯誤轉譯為可讀訊息而非 traceback）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-041、第 5 節模組表的 `ediaad/web/`（`create_server`、`routes`、`sse_hub`）與 `ediaad/app.py`（`Application`、`start`、`stop`）、第 5 節「輸入／輸出、驗證與錯誤格式」的 HTTP 錯誤格式；`docs/architecture/ENGINEERING-REPORT.md` 第 6.1 節元件圖與第 6.3 節網頁層（標準庫 `ThreadingHTTPServer`、原生 HTML／CSS／JS、只 bind `127.0.0.1`、「網頁層只做參數解析、錯誤轉譯與呈現，不重實作任何邏輯」）；`docs/workflow/PROJECT.md` 的技術棧與執行指令表。
- 模組與公開介面：新增 `ediaad/web/__init__.py`（匯出 `create_server`、`routes`）、`ediaad/web/server.py`（`create_server(host="127.0.0.1", port=8787, app=None) -> http.server.ThreadingHTTPServer`，handler 以 `BaseHTTPRequestHandler` 實作）、`ediaad/web/routes.py`（`route(method, path, handler)` 註冊表與 `dispatch(app, method, path, query, body) -> tuple[int, dict]`，逐一轉呼叫核心函式）；`ediaad/app.py` 新增 `Application`（持有 `Watchlist`、`Store`、來源 registry 與 `SSEHub` 佔位）及 `start()`／`stop()`，`stop()` 需可由其他執行緒安全呼叫，供 TASK-026 的優雅關閉複用；新增 `ediaad/web/static/index.html`、`app.js`、`style.css` 作為最小可用的原生前端骨架。
- 預計觸及的檔案：`ediaad/web/__init__.py`、`ediaad/web/server.py`、`ediaad/web/routes.py`、`ediaad/web/static/index.html`、`ediaad/web/static/app.js`、`ediaad/web/static/style.css`、`ediaad/app.py`、`tests/test_web_api.py`；實作前重新查證。
- 必要環境／依賴：Python 3.12.3 的 `.venv`（TASK-001）；只用標準庫 `http.server`、`socketserver`、`json`、`urllib.parse`、`logging`；被呼叫的核心模組來自 TASK-011（CLI 與提醒輸出）、TASK-018（`ediaad/store.py`）、TASK-019（`ediaad/config.py`）；測試以標準庫 `http.client`／`urllib.request` 對真實服務發請求，完全離線。

## 測試計畫

- 測試公開邊界：對真實啟動的 `create_server` 服務（綁 `127.0.0.1` 的臨時埠）以標準庫 HTTP client 發出請求，觀察狀態碼、`Content-Type` 與 JSON 主體；以 `server.socket.getsockname()` 觀察實際綁定位址。
- 第一個失敗行為與預期斷言：`tests/test_web_api.py` 先寫「`GET /api/health` 回 200 且 `body["status"] == "ok"`；`GET /` 回 200 且 `Content-Type` 開頭為 `text/html`」。實作前執行同一命令，預期收集期失敗 `ModuleNotFoundError: No module named 'ediaad.web'`（服務不存在，任何請求都無法成立）；實作後兩項斷言成立。
- 後續例外／邊界情境：未知路徑回 404 且主體為 `{"error": {"code": "not_found", ...}}`；注入的 `ediaad.config.load_settings` 丟出 `ConfigError` 時端點回 400、訊息可讀且主體不含 `Traceback`；核心函式丟出非領域例外時回 500 但不外洩堆疊；`getsockname()` 必須是 `127.0.0.1` 而非 `0.0.0.0`；靜態資源路徑不得跳出 `ediaad/web/static/`（路徑穿越防護）。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_web_api.py -q`；相關回歸 `.venv/bin/python -m pytest -q`；人工啟動沿用 `docs/workflow/PROJECT.md` 的 `.venv/bin/python -m ediaad serve`（`serve` 子命令的完整接線在 TASK-036，本張先以測試夾具直接呼叫 `Application.start()`／`create_server()` 驗證）。
- 非程式任務的替代驗證與理由：不適用（本張為程式任務，AC-041 的行為全部可由 HTTP 端點自動觀察）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-019 的交付物（全套 585 passed）；本次新增 `ediaad/paths.py`、`ediaad/app.py`、`ediaad/web/`（含 `static/` 三檔）與 `tests/test_web_api.py`，並修改 `ediaad/markets/us.py` 的路徑匯入（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-020.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-020.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-web-skeleton` sha256:2b4134defb4de1c4415bdcafa76d8c04838c3fc7c1ab70be088e9e946f24b83a（原始碼樹，53 檔）；新增 `ediaad/paths.py` `b7054902…`、`ediaad/app.py` `8651106a…`、`ediaad/web/__init__.py` `ea2b4f51…`、`ediaad/web/routes.py` `81b9f767…`、`ediaad/web/server.py` `45009f3e…`、`ediaad/web/static/index.html` `dbff8294…`、`ediaad/web/static/app.js` `96dbabb3…`、`ediaad/web/static/style.css` `51e05c8e…`、`tests/test_web_api.py` `7cd3ba21…`；修改 `ediaad/markets/us.py` `b21ef346…`；全套 `613 passed`
- 取消、重開或變更原因：無
