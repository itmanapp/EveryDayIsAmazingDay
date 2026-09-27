# TASK-020 測試紀錄

- task_id：TASK-020
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-web-skeleton sha256:2b4134defb4de1c4415bdcafa76d8c04838c3fc7c1ab70be088e9e946f24b83a
- alternative_reason：無（AC-041 的行為全部可由 HTTP 端點與 `getsockname()` 自動觀察）
- Task／Spec 版本：TASK-020 / SPEC-001 v0.4
- 測試邊界：對**真實啟動**的服務（`Application.start()` ＋ `create_server`，綁 `127.0.0.1` 的臨時埠）以標準庫 `http.client` 發請求，觀察狀態碼、`Content-Type`、JSON 主體與 `server.socket.getsockname()`；完全離線。另外以純函式邊界直接測 `routes.error_response` 的五種對應。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-019 的交付物，全套 **585 passed**（本張完成後為 613 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/paths.py` | `b7054902` | 新增：`$EDIAAD_HOME` 與各產物路徑的單一解析點（見下「範圍追加」） |
| `ediaad/app.py` | `8651106a` | 新增：`Application`（`create`／`start`／`stop`／`close`／`problems`） |
| `ediaad/web/__init__.py` | `ea2b4f51` | 新增：匯出 `create_server`／`routes`／`static_dir` |
| `ediaad/web/routes.py` | `81b9f767` | 新增：路由註冊表、`dispatch`、`error_response`、三個端點 |
| `ediaad/web/server.py` | `45009f3e` | 新增：`create_server`、handler、靜態資源服務（含路徑穿越防護） |
| `ediaad/web/static/index.html` | `dbff8294` | 新增：原生 HTML 骨架 |
| `ediaad/web/static/app.js` | `96dbabb3` | 新增：讀取健康狀態並以文字呈現 |
| `ediaad/web/static/style.css` | `51e05c8e` | 新增：原生 CSS（含深色模式與 focus 樣式） |
| `ediaad/markets/us.py` | `b21ef346` | 修改：`default_home`／`keys_path` 改由 `paths` 提供（見下） |
| `tests/test_web_api.py` | `7cd3ba21` | 新增：28 個測試 |

## 範圍追加（如實記載，兩處）

1. **新增 `ediaad/paths.py`**（不在 TASK-020 的預計觸及檔案中）：TASK-019 的 Review A-2 指出 `default_home()`／`keys_path()` 住在 `markets/us.py`，而 `config.py`／`app.py` 也需要同一組路徑。本張把解析集中到中立模組（`paths` 不依賴任何其他 `ediaad` 模組），`markets/us.py` 改為從那裡匯入並**保留同名 re-export**（TASK-016 的 64 個測試因此不需修改，全部仍綠）。這是把當時的 advisory 付諸實作，不是在範圍外新增功能。
2. **`ediaad/web/static/` 三個檔案**：在預計觸及清單中，但內容是本張撰寫的最小前端骨架（後續 Task 會擴充）。

## Cycle 1：服務骨架、綁定與靜態頁（AC-041，真實 Red → Green）

- 測試：`getsockname()` 是 `127.0.0.1`（且不是 `0.0.0.0`）；`GET /api/health` 回 200 且 `status == "ok"`、帶版本、`problems` 為空；`GET /` 回 200、`Content-Type` 為 `text/html`、含 `<script>`；`/static/style.css` 與 `/static/app.js` 的 `Content-Type` 正確；未知靜態檔回 404；**頁面不得只靠顏色表達狀態**（`aria-live` ＋ 文字）；**路徑穿越防護**（五種寫法都回 404 且不外洩內容），共 7 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_web_api.py -q` | 1 | `7 errors`：`ModuleNotFoundError: No module named 'ediaad.app'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `7 passed in 4.70s` | snap-2026-09-24-ocaievo-web-skeleton／2026-09-24 |

- 實作：`paths.py`；`Application`（`create` 讀設定／開資料庫／載監控清單／列來源，`start` 建 server ＋ 背景執行緒，`stop`／`close`）；`web/routes.py`（註冊表 ＋ 健康端點 ＋ 404／405）；`web/server.py`（`ThreadingHTTPServer` handler、JSON 與靜態回應、`static/` 三個檔案）。
- **靜態資源的防護是雙層的**：先 `unquote`（讓 `%2e%2e%2f` 這類編碼被還原成真正的 `..`），再以 `Path.resolve()` ＋ `is_relative_to(root)` 檢查是否仍在靜態目錄內。測試用**真實存在於靜態目錄之外**的目標（`ocaievo/pytest.ini` 與 repo 根的 `AGENTS.md`）並斷言回應不含其內容——這比「回 404」更強，因為它能抓到「有回應但內容錯誤」的情況。
- **如實記載的測試錯誤**：第一版把逃逸目標寫成 `PROJECT_DIR / "AGENTS.md"`，但 `AGENTS.md` 在 workspace 根、不在 `ocaievo/`；而且用 `../` 一層的目標其實落在 `ediaad/web/`（不存在），等於**沒有真的在測逃逸**。測試自己的 `assert outside.is_file()` sanity check 抓到這件事；已改用 `../../../pytest.ini`（真實存在、三層外）與五層的 `AGENTS.md`。

## Cycle 2：端點對應核心函式、錯誤轉譯與生命週期（AC-041，真實 Red → Green）

- 測試：`/api/patterns` **直接序列化** `NAMED_PATTERNS` 與 `MARKET_PATTERN_DEFAULTS`（以等值斷言證明沒有重算）；`/api/settings` 的值等於 `load_settings(路徑)`（每次請求重新讀檔）；損毀設定 → 400、`code == "invalid_request"`、訊息含檔名、無 `Traceback`；未知 API 路徑 → 404 `not_found`；方法不符 → 405 `method_not_allowed`；畸形主體不會讓連線斷掉；**`error_response` 的五種對應**（`ConfigError`／`DataFormatError`→400、`SourceError`→502、其他 `EdiaadError`→400、未預期→500 且訊息不含例外內容）；注入 `ConfigError` → 400、注入 `RuntimeError` → 500 且**主體不含例外訊息或堆疊**但**伺服器日誌有完整紀錄**（`caplog`）；註冊表列出三個路由且擋重複註冊；`stop()` 關閉 listener 且幂等、**可由其他執行緒呼叫且服務執行緒確實結束**；可重新啟動；`close()` 幂等且釋放資料庫；**損毀的產出物不阻止啟動**（`problems` 有兩項、健康端點看得到、`/api/settings` 回 400），共 21 個（其中 5 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `8 failed`：`/api/patterns`／`/api/settings` 尚未註冊（404）、畸形主體讓連線斷掉、400 對應未實作、損毀產物阻止啟動 | 同上／2026-09-24 |
| Green | 同上 | 0 | `26 passed in 12.39s` | 同上／2026-09-24 |

- 實作：`patterns` 與 `settings` 兩個 handler（各三行，全是既有函式的薄轉接）；`routes.dispatch` 的 `try/except`（把 `EdiaadError` 與未預期例外都轉成 `(狀態碼, 主體)`，500 時 `logger.exception`）；`server._dispatch` 把**主體解析**也納入同一套錯誤轉譯；`error_response` 的五路對應。
- **兩處設計決定**：
  1. `SourceError → 502`（不是 400）：來源失敗代表上游有問題、本機服務本身沒問題；AC-041 只列 400／404，這裡以 `error_response` 的純函式測試把 502 也固定下來（見 Review A-3）。
  2. `/api/settings` **每次請求重新讀檔**（不用 `app.settings` 快取）：損毀的檔案必須能被回報而不是被啟動時的快取掩蓋；`app.settings` 只是「啟動時可用的值」。變異 M13 證明這條有被測試守住。
- **啟動不得因單一產物損毀而失敗**：`Application.create` 對設定與資料庫的 `EdiaadError` 只記錄在 `problems` 並以替代值繼續（設定用預設、資料庫為 `None`），健康端點會回報。理由：使用者唯一的介面就是這個網頁，若服務起不來就沒有任何方法修它。變異 M15／M16 證明兩條都有測試。

## Cycle 3（補測）：變異檢查抓到的三個真實問題

1. **M1（`create_server` 的預設 host 改成 `0.0.0.0`）存活**：我的測試驗證的是 `Application.start` 的預設值（它明確傳 `host`），**不是** `create_server` 自己的預設值。已補 `test_create_server_defaults_to_localhost`（直接呼叫 `create_server` 不傳 host）→ M1 立刻被抓到。這是「同一個性質有兩個入口，只測了一個」的典型缺口。
2. **M17（`stop()` 不呼叫 `shutdown()`）存活**：因為 `server_close()` 就足以釋放 listener，我的斷言只看得到「連不上」。已補「停止後**服務執行緒必須結束**」的斷言（洩漏的執行緒會繼續接受連線並持有資料庫，公開介面看不到，因此測試直接觀察該執行緒物件）→ M17 被抓到。
3. **M20（`start()` 不啟動執行緒）讓測試掛住 5 分鐘**：這暴露了**實作的當機風險**——`BaseServer.shutdown()` 會等 `serve_forever()` 結束，若迴圈從未啟動（或已死）就會**永久阻塞**。已修：只有當服務執行緒 `is_alive()` 時才呼叫 `shutdown()`，並補 `test_stop_returns_promptly_when_the_serve_loop_never_started`（斷言 `stop()` 在 2 秒內返回）。變異工具也加了 per-run 逾時，把「掛住」視為偵測到並如實標示。

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | `create_server` 預設 host 改 `0.0.0.0` | **首次存活 → 補「直接呼叫 `create_server`」測試後被抓到** |
| M2 | 不檢查靜態路徑是否逃出目錄 | 被抓到 |
| M3 | 靜態資源改由工作目錄提供 | 被抓到 |
| M4 | `ConfigError` 映射成 500 | 被抓到 |
| M5 | 500 主體外洩例外內容 | 被抓到 |
| M6 | 500 不寫伺服器日誌 | 被抓到 |
| M7 | 未知路徑回 500 | 被抓到 |
| M8 | 方法不符回 404 | 被抓到 |
| M9 | `dispatch` 不攔例外 | 被抓到 |
| M10 | 健康端點不回報問題 | 被抓到 |
| M11 | 健康端點不回報版本 | 被抓到 |
| M12 | `patterns` 不序列化既有常數 | 被抓到 |
| M13 | `settings` 端點用快取而非重讀檔案 | 被抓到 |
| M14 | 註冊表不擋重複 | 被抓到 |
| M15 | 損毀設定阻止啟動 | 被抓到 |
| M16 | 損毀資料庫阻止啟動 | 被抓到 |
| M17 | `stop` 不關閉 serve 迴圈 | **首次存活 → 補「執行緒必須結束」斷言後被抓到** |
| M18 | `stop` 不重設狀態 | 被抓到 |
| M19 | `close` 不關資料庫 | 被抓到 |
| M20 | `start` 不啟動執行緒 | 被抓到（**並暴露 `shutdown()` 的永久阻塞風險，已修**） |
| M21 | 主體解析失敗不轉譯 | 被抓到 |
| M22 | 靜態 404 改回 200 | 被抓到 |

工具紀律：整行比對、`count(frm) == 1` 才執行、每次變異後立即還原並比對檔案 sha256。矩陣在**最終版檔案**上重跑過，22／22 全數被抓到；還原後 `ediaad/app.py` `8651106a`、`web/routes.py` `81b9f767`、`web/server.py` `45009f3e` 與變異前一致，單檔 `28 passed`。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_web_api.py -q` | 0（`28 passed in 12.51s`） | snap-2026-09-24-ocaievo-web-skeleton |
| 相關回歸（設定＋資料庫＋來源） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_config.py tests/test_store.py tests/test_markets_twelvedata.py -q` | 0（`130 passed in 5.22s`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`613 passed in 36.42s`） | 同上 |
| 未使用匯入掃描 | `ocaievo/`：AST 粗檢 `ediaad/` | 0（無發現） | 同上 |
| 變異後還原驗證 | 同本張單檔 | 0（`28 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 已知邊界（記錄）：
  - **`serve` 子命令尚未存在**（TASK-036）：本張以測試夾具直接呼叫 `Application.start()`／`create_server()`；`PROJECT.md` 的 `.venv/bin/python -m ediaad serve` 目前**不能跑**。這是 TASK-036 的工作，且 SPEC 的模組表把 `cli.py` 的 `serve` 歸在那裡。
  - **SSE hub 只是佔位**（`Application.hub = None`）：TASK-021 實作。
  - **`Application` 還沒有把 `Store` 接進監控迴圈**：`Application.create` 會開資料庫，但 `run_once` 的 `state` 仍由 CLI 自己建立；把 `Store.seen_keys()` 接進監控迴圈是 TASK-025（沿用 TASK-018 A-1，見 Review A-1）。
  - **來源分派仍未發生**：`Application.sources` 只是 `all_sources()` 的清單，沒有任何端點或監控路徑依 `Instrument.source_id` 取得資料；`/api/watchlist` 也還不存在（TASK-025）。TASK-013 以來的接線缺口清單不變。
  - 產品版本字串是 `ediaad.__version__`（`"1.0.0"`，TASK-001 時設定），而報告第 6.5 節的 manifest **範例**用 `"0.4.0"`。兩者尚未對齊；TASK-032／036 需要決定發佈版本（見 Review A-4）。
  - 服務沒有認證、沒有 HTTPS、沒有 CSRF 防護——SPEC 第 6 節已明確接受（只 bind `127.0.0.1` 的單機單使用者）。
  - `POST` 已可運作（`do_POST` ＋ 註冊表 ＋ 405 偵測），但本張沒有會讀主體的端點；`POST /api/watchlist` 屬 TASK-025。
- 未涵蓋：SSE 與事件歷史（TASK-021）、K 線圖（TASK-022）、參數預覽與範例學習（TASK-023）、歷史回看（TASK-024）、監控清單與系統狀態頁（TASK-025）、啟動器與 `stop.sh`（TASK-026）、通知（TASK-027）。
