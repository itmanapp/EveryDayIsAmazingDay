# TASK-020 Code Review

- task_id：TASK-020
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-web-skeleton sha256:2b4134defb4de1c4415bdcafa76d8c04838c3fc7c1ab70be088e9e946f24b83a
- Task／Spec 版本：TASK-020 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 `shutdown()` 阻塞風險的修正、`create_server` 預設值的補測與 `paths.py` 的範圍追認）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `2b4134defb4de1c4415bdcafa76d8c04838c3fc7c1ab70be088e9e946f24b83a`；本張新增 `ediaad/paths.py` `b7054902…`、`ediaad/app.py` `8651106a…`、`ediaad/web/__init__.py` `ea2b4f51…`、`ediaad/web/routes.py` `81b9f767…`、`ediaad/web/server.py` `45009f3e…`、`ediaad/web/static/index.html` `dbff8294…`、`ediaad/web/static/app.js` `96dbabb3…`、`ediaad/web/static/style.css` `51e05c8e…`、`tests/test_web_api.py` `7cd3ba21…`；修改 `ediaad/markets/us.py` `b21ef346…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的已提交、未提交、新增檔案：上述十個檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`monitor.py`／`store.py`／`config.py`／`patterns.py`／`markets/*`（TASK-001～019 交付物）本張只**呼叫**；唯一例外是 `markets/us.py` 的路徑解析改由 `paths` 提供（見 A-5，附理由）
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-041、第 5 節模組表（`ediaad/web/` 的 `create_server`／`routes`／`sse_hub`、`ediaad/app.py` 的 `Application`／`start`／`stop`）、「輸入／輸出、驗證與錯誤格式」的 HTTP 錯誤格式、第 6 節品質需求（安全：只 bind `127.0.0.1`；可及性：不得只依賴顏色）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.1 節元件圖、第 6.3 節網頁層（標準庫 `ThreadingHTTPServer`、原生 HTML／CSS／JS、只做參數解析與錯誤轉譯）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-041 | `ediaad/web/server.py`／`routes.py`／`app.py`；`tests/test_web_api.py` 28 個案例 | 符合 | A-1～A-6（advisory） |

逐條核對：

- **AC-041「以 `create_server` 啟動的本機服務只 bind `127.0.0.1`」**：兩個入口都測了——`Application.start()`（預設 `host="127.0.0.1"`）與**直接呼叫 `create_server(port=0)`**（不傳 host）；都以 `getsockname()` 斷言且明確排除 `0.0.0.0`。符合。
- **AC-041「`GET /` 回原生 HTML 靜態頁」**：200、`Content-Type: text/html; charset=utf-8`、含 `<script>`、`/static/*` 的 CSS／JS 以正確的 `Content-Type` 提供。符合。
- **AC-041「JSON 端點至少 `GET /api/health`、`GET /api/patterns`」**：兩者都有；另加 `GET /api/settings`（見 A-3）。符合。
- **AC-041「每個端點只做參數解析、呼叫既有核心函式與序列化，不重複實作運算」**：`health` 只讀 `app` 的欄位；`patterns` **直接序列化** `NAMED_PATTERNS` 與 `MARKET_PATTERN_DEFAULTS`（以等值斷言固定）；`settings` 只呼叫 `config.load_settings`（以等值斷言固定）。三個 handler 各三行，無任何運算。符合。
- **AC-041「`EdiaadError` 子類別轉成 400／404 並附可讀訊息」**：`ConfigError`／`DataFormatError`／其他 `EdiaadError` → 400、`SourceError` → 502（見 A-3）、未知路徑 → 404、方法不符 → 405；錯誤主體一律 `{"error": {"code": ..., "message": ...}}`。符合。
- **AC-041「非預期例外回 500 且主體不含 `Traceback` 或堆疊內容」**：注入 `RuntimeError` 的測試斷言 500、`code == "internal_error"`、**例外訊息與 `Traceback` 都不在回應中**，且 `caplog` 確認伺服器日誌留有完整紀錄。符合。

## 品質 Review

- **路徑穿越防護是雙層且以「真實目標」驗證的**：先 `unquote`（把 `%2e%2e%2f` 還原成真正的 `..`，避免「靠不解碼來僥倖擋下」），再以 `resolve()` ＋ `is_relative_to(root)` 檢查。測試用**靜態目錄之外真實存在**的檔案（`ocaievo/pytest.ini`、repo 根的 `AGENTS.md`）並斷言回應**不含其內容**——這比只斷言 404 更強，能抓到「有回應但內容錯誤」。變異 M2（移除檢查）與 M3（改由工作目錄提供）都被抓到。
- **`shutdown()` 的永久阻塞風險（本張最重要的修正，由變異 M20 暴露）**：`BaseServer.shutdown()` 會等 `serve_forever()` 結束，若服務執行緒從未啟動或已死，`shutdown()` **永遠不會返回**——在測試中表現為 5 分鐘逾時，在產品中就是「按下關閉服務卻停不下來」。已改為只有當服務執行緒 `is_alive()` 時才呼叫 `shutdown()`，並補一個斷言「`stop()` 必須在 2 秒內返回」的測試。**這是變異檢查在功能之外抓到的可靠性缺陷。**
- **啟動不得因單一產物損毀而失敗**：使用者唯一的介面就是這個網頁；若設定檔或資料庫損毀就讓服務起不來，使用者沒有任何方法修它。`Application.create` 因此把 `EdiaadError` 記進 `problems` 並以可用值繼續（設定用預設、資料庫為 `None`），健康端點回報問題、`/api/settings` 回 400 說明原因。兩條路徑各有測試與變異（M15／M16）。
- **`/api/settings` 每次請求重讀檔案（M13）**：若改用啟動時的快取，損毀的檔案會被永遠掩蓋、使用者看到的仍是「正常」。重讀的成本可忽略（單機、每頁幾次），換來的是「錯誤一定看得到」。
- **錯誤轉譯集中在 `dispatch`，且 500 不外洩內容但一定要記日誌**：「錯誤一律靜默」不適用於此——對使用者靜默（固定訊息）、對開發者必須留下完整紀錄（`logger.exception`）。M5／M6 分別證明「不外洩」與「要記日誌」兩邊都有測試。
- **可及性從第一頁就遵循**：狀態以文字表達（不靠顏色）、狀態區是 `aria-live="polite"`、`style.css` 有 `:focus-visible` 樣式、頁面有 `lang="zh-Hant"` 與語意標題階層。有測試斷言文字與 `aria-live` 的存在。
- **依賴與零新增依賴**：只用標準庫（`http.server`／`socketserver`／`json`／`urllib.parse`／`logging`／`threading`）與既有 `ediaad` 模組；沒有 Flask／FastAPI／uvicorn。前端是原生 HTML／CSS／JS，無建置工具鏈。
- **測試品質**：`http.client` 對真實服務發請求（不是 mock）；每個錯誤路徑都斷言狀態碼、`code` 與「不含堆疊」；生命週期（stop／close／restart）以真實 socket 行為驗證；錯誤對應表以純函式邊界逐一測五種例外。未發現其他問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 缺口（沿用 TASK-013 A-1～019 A-2） | advisory（**需在後續 Task 處理**） | 本張建立了骨架，但**接線仍未發生**：`Application.sources` 只是清單、`Store` 沒接進監控迴圈（`run_once` 的 `state` 仍由 CLI 自己建立）、沒有 `GET/POST /api/watchlist`、沒有依 `Instrument.source_id` 的分派。使用者現在打開網頁只會看到健康狀態 | TASK-025 應一次收斂整條線：catalog → 商品來源對照、來源分派、市場別預設、日曆套用、除權息還原、金鑰狀態、catalog 狀態、`Store` 接線與 `GET/POST /api/watchlist`；TASK-037 的整合驗收應逐項確認 | 待辦（已記於 `STATE.md` 待決事項） |
| A-2 | 未實作範圍 | advisory | `serve` 子命令不存在（TASK-036），因此 `PROJECT.md` 的 `.venv/bin/python -m ediaad serve` 目前不能跑；SSE hub 只是 `None` 佔位（TASK-021） | 兩者都已在對應 Task 的範圍內；本張的 TDD 紀錄已明示，避免有人以為現在就能用 `serve` | 已記錄（TASK-021／036） |
| A-3 | 錯誤碼補充 | advisory（需追認） | `SourceError → 502` 不在 AC-041 的「400／404」之中；語意上上游失敗是本機服務之外的錯，用 502 更準確 | 於 SPEC 第 5 節的 HTTP 錯誤表補上 502（來源失敗）；若偏好嚴格照 AC 實作，改回 400 只要改一行＋更新參數化測試 | 待追認（已由 `error_response` 的純函式測試固定） |
| A-4 | 版本一致性 | advisory | 產品版本是 `ediaad.__version__`（`"1.0.0"`），而報告第 6.5 節的 manifest **範例**用 `"0.4.0"`；`/api/health` 回報的是前者 | TASK-032／036（更新與版本頁）需要決定發佈版本並讓 manifest、`__version__`、版本頁三者一致；目前沒有端點會比對版本，因此不影響本張 | 待辦（TASK-032／036） |
| A-5 | 範圍追加 | advisory（需追認） | 新增 `ediaad/paths.py` 並改 `markets/us.py` 的路徑匯入（不在 TASK-020 的預計觸及檔案中） | 這是 TASK-019 Review A-2 的落實（三個消費者出現時集中 `$EDIAAD_HOME` 解析）；`markets/us.py` 保留同名 re-export，TASK-016 的 64 個測試未修改即全綠。建議在 SPEC 第 5 節模組表補上 `ediaad/paths.py` | 待追認（已完成且回歸全綠） |
| A-6 | 流程紀律 | advisory（非程式） | 第一版的逃逸測試用了不存在的目標（等於沒在測）；M1／M17 因「同一性質有兩個入口／只看得到一邊」而存活；M20 讓測試掛住 5 分鐘 | 已全部在 TDD 紀錄如實記載。教訓：變異工具必須有 per-run 逾時並把「掛住」視為偵測到 | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-041 逐條符合；品質 Review 無 blocking。
- 依變異檢查修正 2 處實作／測試：`stop()` 加入執行緒存活檢查（修正 `shutdown()` 的永久阻塞）；補「直接呼叫 `create_server`」與「停止後服務執行緒必須結束」的測試（M1／M17）。
- 依 Review 修正 1 處測試：路徑穿越的逃逸目標改成真實存在的檔案（原版等於沒在測）。
- 重審：重跑單檔（28 passed）、相關回歸（130 passed）與全套（613 passed）；重讀 `app.py`／`routes.py`／`server.py` 複查生命週期、錯誤轉譯、靜態資源解析與執行緒安全。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-041 的六項宣稱逐條符合）
- 品質 Review：passed（無 blocking；A-1 需在後續 Task 落實，A-2 已在其他 Task 範圍內，A-3／A-5 需追認，A-4 待版本決策，A-6 為流程記載）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-025／037）、A-2（TASK-021／036）、A-3（需 Spec 補充）、A-4（TASK-032／036）、A-5（需 Spec 補充）、A-6（流程記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：`serve` 子命令未實作（現在無法用 CLI 啟動）；SSE 只是佔位；`Store` 與來源分派尚未接線；版本字串未與 manifest 對齊；服務無認證／HTTPS／CSRF（SPEC 已明確接受）
