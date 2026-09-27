# TASK-023 Code Review

- task_id：TASK-023
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-web-preview-learn sha256:eb91266c080c526e71d396a1137cae89ced033f976520e1b874f3aa301c915d6
- Task／Spec 版本：TASK-023 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含變異存活者的處理、冗餘分支的移除與前端可測性的檢討）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `a573a7f10592805a8755d74e62a0403e4678ec3246dc2fe6506e341a62d163ce`（60 個檔案）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `eb91266c080c526e71d396a1137cae89ced033f976520e1b874f3aa301c915d6`（63 個檔案）；本張新增 `ediaad/web/static/params.js` `2c60ec9f…`、`ediaad/web/static/learn.js` `8b42bcfd…`、`tests/test_web_preview_learn.py` `7f62eb32…`；修改 `ediaad/web/routes.py` `9f3ddc91…`、`ediaad/web/static/index.html` `60bcc253…`、`ediaad/web/static/style.css` `ab572dd9…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：上述六個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`patterns.py`／`data.py`／`config.py`／`markets/*`／`app.py`／`server.py`／`sse_hub.py` 本張只呼叫或沿用未修改（`_limit_from` 內部改為共用 `_limit_value` 屬同檔重構，已含在 `routes.py` 的雜湊內）
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-044／AC-045、第 5 節 `patterns.py` 的 `PatternSpec`（含 `to_json`／`from_json` 的嚴格還原）與 `data.load_csv` 契約、第 6 節效能與可及性、第 8 節風險 1／3；`docs/workflow/BRIEF.md` 第 21 行（白話參數清單）；`docs/architecture/ENGINEERING-REPORT.md` 第 3.2 節 G4／G5、第 5.7 節、第 6.3 節；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-044 | `ediaad/web/routes.py`（`pattern_preview`／`_spec_for_body`／`_body_*`）、`ediaad/web/static/params.js`、`index.html`；`tests/test_web_preview_learn.py`（Cycle 1 的 19 個案例＋前端 7 個） | 符合 | A-2～A-5（advisory） |
| AC-045 | `ediaad/web/routes.py`（`pattern_learn`／`_load_sample`）、`ediaad/web/static/learn.js`、`index.html`；`tests/test_web_preview_learn.py`（Cycle 2 的 10 個案例＋前端斷言） | 符合 | A-1、A-2、A-4、A-5（advisory） |

逐條核對：

- **AC-044「改動任一參數，不需存檔即在 1 秒內顯示命中次數」**：`POST /api/pattern/preview` 不回寫任何檔案（端點只讀序列、只算次數），`params.js` 以去抖動在輸入後送出；「1 秒內」有自動斷言（暖機後一次往返 `< 1` 秒）。**「不需存檔」是構造上的**：整條路徑沒有任何寫入設定的呼叫（設定的寫入屬 TASK-025）。符合（真實瀏覽器的手感量測見 A-2）。
- **AC-044「改回原值得到原本次數（無隨機性）」**：同一輸入兩次回應**位元相同**；`range_bars_min` 20→21 使次數 1→0、改回 20 回到 1。符合。
- **AC-044「命中次數」的定義**：`n` 等於以同一參數呼叫 `ediaad.patterns.detect` 的事件數——端點只有一個 `len(detect(...))` 呼叫點，並以「與 `detect` 逐筆相同」及「與 `GET /api/patterns/events` 相同」雙向固定。符合。
- **AC-044「實際採用的參數」**：回應的 `params` 與 `PatternSpec` 逐欄相同且鍵集合完整（另有 `spec` 供 TASK-022 的圖表對照）。符合。
- **AC-045「顯示推估參數」**：`POST /api/pattern/learn` 回 `spec`（物件）與 `spec_json`（`to_json` 的穩定鍵序，可由 `from_json` 嚴格還原）；前端以白話標籤逐列呈現。符合。
- **AC-045「命中預覽」**：有指定商品與週期時，以推估規格對目前序列呼叫 `detect` 並回報次數（測試以同一段範例推估 → 對目前商品命中 1 次，與直接呼叫逐值相同）；資料不足時回 `insufficient`（不是假裝 0 次命中），沒有商品時回 `no_preview` 且 `hits` 為 `None`。符合。
- **AC-045「無法推估時顯示明確原因」**：範例過短、找不到盤整區間、跌破後未回到區間均值等都由核心 `learn` 的 `ConfigError` 原文回報（400，回應**不含** `spec`，測試逐字比對核心訊息）；CSV 格式錯誤由 `load_csv` 的訊息回報並保留欄位名。符合。

## 品質 Review

- **網頁層仍然是薄轉接**：`pattern_preview` 是 `_fetch_series` → `detect` → 序列化；`pattern_learn` 是 `_load_sample`（`load_csv`）→ `learn` → 序列化。沒有任何判定或推估寫在 web 層。前端更以測試明確禁止重實作（`params.js`／`learn.js` 不得出現 `detect(`／`atr(`／`Math.exp`）——這讓「預覽與正式掃描一致」不只是當下的巧合。
- **`hits` 只有一個真相**：回應的次數沒有第二套計算路徑（唯一呼叫點），且以兩個方向的交叉斷言固定。這正是這類「即時預覽」最容易與實際掃描分岔的地方。
- **嚴格輸入，且不默默忽略**：未知欄位（頂層）／未知參數（`params` 內）／非數值／空白／顛倒的區間／未知 `recovery_target`／`limit` 非整數或超上限／主體不是物件／沒有主體，全部 400 並指出欄位名；`limit` 有值卻沒有商品時也 400（`INSTRUMENT_KEYS` 規則）。**這是本張由測試逼出來的一個真實設計修正**：原本 `limit` 會被默默忽略。
- **錯誤轉譯有分寸**：`DataFormatError` 只把伺服器暫存路徑換成「範例 CSV」（欄位名與列號保留，且有斷言不含 `/tmp/`），核心的 `ConfigError` 則**原樣**呈現（逐字比對）——呈現可以改寫，原因不可以。
- **F-003 三個層次一致**：後端 `status`＝`insufficient`／`evaluated`／`no_preview`，前端文字（`describeHits`）與學習結果（`describeLearnResult`）都分別對應，且有測試確保「資料不足」與「沒有命中」的文字不同。這是 SPEC 從 TASK-008 起反覆強調的語意，在預覽與學習兩條新路徑上都沒有退化。
- **前端可測性的架構決定**（與 TASK-022 的 `chart.js` 同型）：`params.js`／`learn.js` 是無依賴 IIFE、**載入時不碰 DOM**，把轉型、錯誤訊息、F-003 的文字與去抖動抽成純函式，因此需要判斷的部分都有自動證據，留在瀏覽器裡的只剩輸入事件與檔案讀取。**去抖動改用假計時器**後，「等待視窗等於宣告值」也變成可斷言的性質（原本只驗證同一輪輸入會合併）。
- **不引入新依賴**：後端只用標準庫（`tempfile`）；前端不用框架、不建置；`node` 只在測試期使用（`skipif`）。序列的解析完全沿用 `load_csv`，沒有第二套 CSV 解析器（報告 F-001 的教訓）。
- **可及性**：面板與學習表單的每個控制項都有 `label`、狀態用 `aria-live`、錯誤用 `role="alert"`、結果以文字呈現（不依賴顏色）。符合 SPEC 第 6 節。
- **冗餘碼的移除**：`_spec_for_body` 的 `if not overrides: return base` 提前返回在行為上與「一律重建」相同，屬等同變異的溫床，已直接移除（同 TASK-013 M16／TASK-019 M17／TASK-022 M11 的處理原則）。
- **變異測試的強度**：30 個變異在凍結版全數被抓到。第一階段抓到 2 個真實存活者（`strip()` 被拿掉、去抖動視窗被忽略）並各補一個**行為**斷言擊殺，而不是調整實作來遷就測試。
- **測試品質**：後端以真實 HTTP 請求觀察 JSON 與狀態碼；前端以 Node 執行真實檔案（不是重寫一份 JS）；範例與序列都是合成且離線（無網路、無真實憑證）；同一輸入的位元相同以實際回應主體比較。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 缺口（沿用 TASK-013 A-1～TASK-022 A-1） | advisory（**需在後續 Task 處理**） | 服務仍**不會自己跑監控**：`run_once` 沒人呼叫、`Store` 寫入端未接、沒有 `GET/POST /api/watchlist`；本張的預覽與學習都只讀快取序列 | TASK-025 應完成：監控執行緒（`run_once` ＋ `Store` 讀寫）、監控清單端點、系統狀態頁、**以及把「學到的規格」寫入設定的動作**（本張刻意只預覽、不自動儲存） | 待辦（已記於 `STATE.md` 待決事項） |
| A-2 | 真實瀏覽器檢查 | advisory（**未執行**） | SPEC 第 7 節要求 Chrome 目視／手感；本環境沒有瀏覽器。AC-044 的「1 秒內」已以伺服器端往返自動量測，但拖動時的感受、深色模式對比、上傳檔案的檔案挑選對話框仍未驗證 | 交付前在 Chrome（Wayland）量測一次拖動延遲，並各做一次「貼上」與「上傳」 | 待辦（替代驗證已記錄於 TDD 的「未執行或受阻」） |
| A-3 | 預覽的觀測窗 | advisory | `pattern_preview` 未指定 `limit` 時沿用序列端點的預設（最近 500 根），因此面板顯示的次數是「最近 500 根」的次數；快取更長時與全序列不同（但與 `GET /api/patterns/events` 的預設窗一致） | 面板或回應可顯示 `bars`（已回傳）並在說明文字標明觀測窗；若之後要改成全序列，需同步 `events` 端點的預設 | 已記錄（`bars` 已在回應中，測試有斷言） |
| A-4 | 單一範例可能過擬合 | advisory（SPEC 風險 3） | `learn` 由**一段**範例推估，容差雖朝「更容易命中範例」放寬，仍可能只對該段有效 | 本張已把推估參數完整回傳（`spec`／`spec_json`）供使用者檢視，且**不自動寫入設定**；後續可考慮多段範例或交叉驗證（需要 SPEC 變更） | 已緩解（不自動儲存＋回傳可檢視參數） |
| A-5 | SPEC 未列路由表 | advisory | 路由路徑（`/api/series`、`/api/patterns/events`、`/api/pattern/preview`、`/api/pattern/learn`）散落在各 Task 文件；`STATE.md` 的「下一步」曾把本張寫成 `/api/patterns/preview`（複數），與 TASK-023.md 的單數契約不一致 | 本張以 **TASK-023.md 為準**（單數）並修正 `STATE.md`；建議在 SPEC 第 5 節加一張路由表，避免後續 Task 對路徑產生兩種寫法 | 已修正（`STATE.md`）／待追認（Spec 補表） |
| A-6 | 型別註解 | advisory（非行為） | `routes._load_sample` 沒有回傳型別註解（同檔其他函式都有）；要標註 `pd.DataFrame` 需在 web 層匯入 pandas（型別檢查專用） | 若後續要動這一帶，可加 `TYPE_CHECKING` 匯入並補註解；本張**刻意不動**——凍結版已跑完變異矩陣（30／30），為了一個裝飾性註解改動位元會使 `checked_version` 與變異結果的配對失效 | 延後（零行為影響；已記錄） |
| A-7 | 流程紀律 | advisory（非程式） | 變異矩陣第一次以 `nohup … &` 啟動時行程未隨外層 shell 結束，與受控背景執行同時改同一批檔案（觀察到 `R1` 無效與互有差異的兩份統計） | 已終止殘留行程、確認 sha256 還原、加入 `flock` 後單獨重跑，並在 TDD 紀錄如實記載、作廢先前輸出。教訓：**變異測試必須確保單一行程獨占受測檔案** | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-044／AC-045 逐條符合；品質 Review 無 blocking。
- 依測試回饋修正實作 1 處：`limit`（或其他商品欄位）沒有搭配商品時不得默默忽略 → `INSTRUMENT_KEYS` 規則。
- 依變異檢查移除 1 處冗餘分支（`_spec_for_body` 的提前返回）；依 2 個存活變異各補 1 個行為斷言（`strip()`、去抖動視窗改以假計時器斷言 `delay`）。
- 移除 1 個測試夾具錯誤（「最近 25 根」被當成仍含完整結構）與 1 個 harness 別名問題（陣列存成參照）。
- 重審：重跑單檔（40 passed）、相關回歸（web 三檔 80 passed）與全套（**709 passed**）、兩個流程驗證器（exit 0），並重新凍結後重跑變異矩陣（**30／30 偵測到，0 存活**）；重讀 `routes.py` 的新增段落複查輸入驗證、規格推導、F-003 語意、錯誤轉譯與暫存檔清理（`finally` 一律刪除）。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-044 的四項宣稱、AC-045 的三項宣稱逐條符合）
- 品質 Review：passed（無 blocking；A-1 需在後續 Task 落實，A-2 為交付前人工檢查，A-3～A-6 已記錄或延後，A-7 為流程記載）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-025）、A-2（交付前人工檢查）、A-3（已回傳 `bars`，窗的說明留待交付頁面）、A-4（需 SPEC 變更才做多段範例）、A-5（Spec 補路由表）、A-6（零行為影響，避免使變異結果與 `checked_version` 脫鉤）、A-7（已記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：真實瀏覽器的拖動手感與上傳對話框未驗證（已有伺服器端效能斷言與純函式證據）；`attachPanel`／`attachLearnForm` 的 DOM 流程未自動測試；`style.css` 的視覺效果無自動證據；預覽的預設觀測窗為最近 500 根；`learn` 由單一範例推估可能過擬合（不自動儲存、參數可檢視）；服務仍不會自己跑監控（A-1）
