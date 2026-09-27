# TASK-023 測試紀錄

- task_id：TASK-023
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-web-preview-learn sha256:eb91266c080c526e71d396a1137cae89ced033f976520e1b874f3aa301c915d6
- alternative_reason：**部分替代**——真實瀏覽器的拖動感受與上傳檔案的檔案挑選對話框無法在無瀏覽器自動化的環境驗證。AC-044 的「1 秒內」改以**伺服器端往返時間**自動量測（暖機後 `< 1` 秒）＋ 前端轉型／去抖動以 Node 載入真實檔案驗證；Chrome（Wayland）的目視與手感量測仍**未執行**（見「未執行或受阻」）。
- Task／Spec 版本：TASK-023 / SPEC-001 v0.4
- 測試邊界：（1）`POST /api/pattern/preview` 與 `POST /api/pattern/learn` 的 JSON 契約、狀態碼與「`hits` 等於直接呼叫 `ediaad.patterns.detect` 的事件數」；（2）`params.js`／`learn.js` 的純函式（標籤對應、轉型、錯誤訊息、去抖動）以 Node 載入真實檔案驗證；（3）靜態資源與頁面接線。全部離線，無網路。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-022 的交付物，全套 **669 passed**（本張完成後為 **709 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `a573a7f10592805a8755d74e62a0403e4678ec3246dc2fe6506e341a62d163ce`（60 個檔案）。
- TDD 不適用的理由與替代驗證（若有）：見「未執行或受阻」第 1 點（Chrome 手感與上傳對話框）。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/web/routes.py` | `9f3ddc91` | 修改：`POST /api/pattern/preview`、`POST /api/pattern/learn`、`_body_object`／`_body_text`／`_limit_value`／`_limit_from_body`／`_source_id_from_body`／`_spec_for_body`／`_load_sample`（`_limit_from` 改為共用 `_limit_value`） |
| `ediaad/web/static/params.js` | `2c60ec9f` | 新增：白話標籤 ↔ `PatternSpec` 欄位、`parseValue`／`toParams`／`buildBody`／`describeHits`／`describeError`／`makeDebouncer`／`readValues`／`fillValues`／`attachPanel` |
| `ediaad/web/static/learn.js` | `8b42bcfd` | 新增：`buildLearnBody`／`describeLearnResult`／`describeLearnError`／`attachLearnForm`（貼上／上傳） |
| `ediaad/web/static/index.html` | `60bcc253` | 修改：規律參數面板（10 個 `data-param` 控制項）與範例學習表單 |
| `ediaad/web/static/style.css` | `ab572dd9` | 修改：面板與學習表單的樣式（以文字表達狀態，顏色只是輔助） |
| `tests/test_web_preview_learn.py` | `7f62eb32` | 新增：40 個測試（含 1 個效能斷言與 7 個 Node 純函式斷言組） |

## Cycle 1：參數即時預覽端點（AC-044，真實 Red → Green）

- 測試（18 個）：`hits` 等於直接以同一參數呼叫 `detect` 的事件數；**同一輸入兩次回應位元相同**；改 `range_bars_min` 20→21 使次數 1→0、改回原值回到 1；回應帶實際採用的 `params`（與 `PatternSpec` 逐欄相同、鍵集合完整）；省略參數時用「設定 → 市場別預設 ＋ `pattern_id`」；白話參數可放頂層或 `params` 內且結果相同；只送一個參數時其餘沿用設定；`hits` 與 `GET /api/patterns/events` 的事件數一致；回應為 JSON；`limit` 取最近 N 根（52→1 次、25→評估後 0 次、20→資料不足）；不合法輸入各回 400 並指出欄位名（`range_bars_min > range_bars_max`、負數、非數值、空白、未知 `recovery_target`、未知參數名、未知欄位、`limit` 非整數／超過上限、未知來源、缺 `symbol`／`interval`、主體不是物件／沒有主體、`params` 不是物件）；所有錯誤都不含 `Traceback`；**「資料不足」與「評估後沒有命中」以 `status` 明確區分**（F-003）。
- 另外補一個 **效能斷言**：暖機後一次預覽往返必須 `< 1` 秒（SPEC 第 6 節）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_web_preview_learn.py -q` | 1 | `18 failed`：端點不存在（404）→ `KeyError: 'status'` | 尚未有端點／2026-09-24 |
| Green | 同上 | 0 | `18 passed in 11.36s` | snap-2026-09-24-ocaievo-web-preview-learn／2026-09-24 |

- 實作：`routes.pattern_preview`（薄轉接：`_fetch_series` → `detect` → 序列化）；`_spec_for_body` 由設定的市場別預設（`_spec_for`）＋ 請求覆寫組成規格，覆寫可放頂層或 `params`，**未知鍵一律 400**（打錯字被默默忽略會讓使用者看到的次數與他以為的參數不符）；`_body_object`／`_body_text`／`_limit_value` 集中驗證；`_limit_from` 改為呼叫 `_limit_value`，讓 `GET` 與 `POST` 共用同一套上限政策。
- **`hits` 的語意是構造上的保證**：回應只有一個 `len(detect(frame, spec))` 呼叫點，沒有第二套計數邏輯；測試再從外部以「與 `detect` 逐筆相同」與「與事件端點相同」雙向固定。
- **F-003 在預覽上同樣明確**：`insufficient`（附需要與實際根數）／`evaluated`（附「沒有命中」），`hits` 都是 0 但意義相反——與 TASK-022 的 `status` 語意一致。
- **如實記載的夾具錯誤**：`test_preview_honours_limit` 第一版把「最近 25 根」當成仍含完整結構（其實 74 根中回歸之後還有 22 根，尾端 25 根只剩 1 根盤整 K 線）→ 一度斷言 1 次命中。已改為三個明確情境：`limit=52`（完整結構 → 1 次）、`limit=25`（切掉盤整 → 評估後 0 次）、`limit=20`（不足 `min+1` → 資料不足）。

## Cycle 2：範例學習端點（AC-045，真實 Red → Green）

- 測試（10 個）：範例（目前商品索引 25～55 的 31 根）推估出的 `spec` 與直接呼叫 `learn` 相同、`spec_json` 等於 `to_json` 且可被 `from_json` 還原、`spec` 鍵集合完整；命中預覽等於以推估規格對目前商品呼叫 `detect` 的事件數（此夾具為 1）；同一範例兩次回應位元相同；沒有目前商品時回 `no_preview` 且 `hits` 為 `None`（不得假裝有預覽）；範例 < `LEARN_MIN_BARS` 回 400 且**不含** `spec`；單調上升的範例回 400 附「跌破」原因；缺欄位的 CSV 回 400 指出欄位名、訊息含「範例 CSV」且**不含** `/tmp/`；空檔與缺 `csv`／非字串 `csv`／未知欄位回 400；`limit` 與來源生效、未知來源回 400；缺 `interval` 回 400；核心 `learn` 的 `ConfigError` 訊息**原樣呈現**（與直接呼叫核心的訊息逐字相同）。
- 驗證「範例學習沿用 `load_csv`」：請求中的 CSV **文字**寫入暫存檔後交給 `data.load_csv`（不另寫解析器）；唯一改寫是把訊息中的暫存路徑換成「範例 CSV」。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_web_preview_learn.py -q` | 1 | `10 failed, 18 passed in 17.46s`：端點不存在（404） | 同上／2026-09-24 |
| Green | 同上 | 0 | `28 passed in 17.65s` | 同上／2026-09-24 |

- 實作：`routes.pattern_learn`；`_load_sample`（`tempfile` ＋ `load_csv` ＋ 訊息路徑改寫）；`INSTRUMENT_KEYS`（`symbol`／`interval`／`source`／`limit` 只要出現任一項，就必須同時提供 `symbol` 與 `interval`）。
- **一個測試逼出真正的設計問題**：`limit` 有值但沒有商品時，第一版會直接回「沒有預覽」而**默默忽略** `limit`。這與「未知鍵必須 400」是同一件事的兩面（不明確的表達不該被猜測），因此改成上面的 `INSTRUMENT_KEYS` 規則，並保留該測試案例。
- **錯誤轉譯的分寸**：`DataFormatError` 只把暫存檔路徑換成「範例 CSV」（欄位名與列號保留），核心 `learn` 的 `ConfigError` 則原樣呈現並有測試逐字比對——網頁層可以改寫「呈現」，不可以改寫「原因」。
- **如實記載的測試錯誤**：`test_learn_reports_a_malformed_csv_with_the_column_name` 原本送 `"\n"` 想觸發 `load_csv` 的空檔錯誤，但路由自己的空白檢查會先擋下（訊息不含「範例 CSV」）→ 改送「只有表頭」的 CSV，才真的走到解析路徑。

## Cycle 3：前端面板與學習表單（AC-044／AC-045，真實 Red → Green）

- 測試（11 個）：`/static/params.js`、`/static/learn.js` 以正確的 `Content-Type` 提供且含各自端點字串；**前端不得重實作引擎**（兩支檔案都不得出現 `detect(`／`atr(`／`Math.exp`）；首頁含面板與學習表單的 id、10 個 `data-param` 控制項與兩支 script；以 **Node 載入真實檔案**驗證：標籤覆蓋全部 `PatternSpec` 欄位且不是英文欄位名照抄、`toParams` 的整數／浮點／字串轉型正確、六種不合法值都丟出**指出欄位名**的錯誤、`describeHits` 四種狀態（命中／沒有命中／資料不足／沒有預覽）互不混淆、`buildBody`／`buildLearnBody` 的主體形狀（沒有商品時不得帶 `symbol`）、`describeLearnResult` 用白話標籤列出推估參數與命中數、`describeLearnError` 呈現後端訊息與固定備援訊息、去抖動的排程視窗與合併行為。
- 去抖動以**假計時器**驗證（覆寫 `setTimeout`／`clearTimeout` 並記錄 delay）：三次連續輸入只留一個未取消的計時器、其 `delay` 等於宣告的 `DEBOUNCE_MS`、觸發後只呼叫最後一次；之後再輸入也必須再送一次。這讓「等待視窗」本身可被斷言，而不依賴牆上時鐘。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_web_preview_learn.py -q` | 1 | `3 failed, 29 passed, 7 errors in 20.25s`：兩個 JS 檔 404、首頁未接線、Node 讀不到檔案 | 同上／2026-09-24 |
| Green | 同上 | 0 | `39 passed in 20.44s` | 同上／2026-09-24 |

- 實作：`params.js`（純函式 ＋ `attachPanel` 黏著層，載入時不碰 DOM，因此可在 Node 裡載入；面板一開始的數值由 `GET /api/patterns` 填入，不在前端另抄一份預設值）；`learn.js`（純函式 ＋ `attachLearnForm`，上傳檔以 `FileReader` 讀成文字後走同一個 JSON 端點）；`index.html`（面板／學習區塊與 script）；`style.css`。
- **為什麼前端可測**：與 TASK-022 的 `chart.js` 同一手法——無依賴 IIFE、載入時不碰文件、把可判斷的部分抽成純函式。因此「轉型、錯誤訊息、去抖動、F-003 的文字」都有自動證據；只有真正需要瀏覽器的互動（拖動、檔案挑選對話框）留給人工。
- **如實記載的測試錯誤**：Node harness 把 `calls` 陣列**存成參照**，導致 `debounceCalls` 與 `debounceCallsAfter` 看到同一份最終內容（`["c","d"]`）→ 改為 `.slice()`；新測試檔漏了 `PROJECT_DIR` 定義 → 補上。

## 變異測試（兩階段：先殺存活者，再跑凍結版）

- 工具：`/tmp/mutate_task023.py`（整行替換、`count(frm) == 1` 才套用、每輪 `subprocess` 逾時 120 秒（逾時視為偵測到）、跑完立即還原並比對 sha256；以 `flock` 確保同時只有一個行程）。
- 矩陣：**30 個變異**（`routes.py` 22 個、`params.js` 5 個、`learn.js` 3 個），涵蓋 `limit` 上限與型別、主體型別、`strip`、未知欄位／未知參數、覆寫合併、`minimum`、`hits` 計算、F-003 三處訊息、`no_preview` 三欄、`INSTRUMENT_KEYS` 規則、暫存路徑改寫、`spec` 來源、CSV 空白檢查、前端整數轉型、未知欄位、去抖動視窗、命中文字分支、學習結果分支、上傳主體。
- **第一階段抓到 2 個真實存活者，都補強測試後擊殺**：
  1. `R5`（`_body_text` 的 `strip()` 拿掉）存活 → 補「商品代號與週期前後空白正規化」斷言。
  2. `J3`（去抖動的 `delay` 固定為 0、忽略等待視窗）在**真實計時器**版本存活（同一輪同步輸入仍會合併）→ 改為假計時器並斷言 `delay == DEBOUNCE_MS`、前兩個計時器被取消，三個斷言都與時間無關。
- 另外為避免「等同變異」而**移除冗餘碼**（同 TASK-013 M16／TASK-019 M17／TASK-022 M11 的處理）：`_spec_for_body` 原本有 `if not overrides: return base` 的提前返回，改為一律由 `asdict(base)` ＋ 覆寫重建（結果相同、少一條分支）；`R3`（`body is None` 分支）也因為補了「必填」訊息斷言而不再是等同變異。
- **最終凍結版結果：30／30 全數偵測到（0 存活、0 無效）**，逐輪輸出形如 `39 passed, 1 failed`（40 個測試）。
- **如實記載的流程錯誤**：第一次以 `nohup … &` 啟動變異矩陣時，該行程沒有隨外層 shell 結束，與隨後的受控背景執行**同時改同一批檔案**（觀察到 `R1` 無效、`count=0` 與兩份互有差異的統計）。已終止殘留行程、確認檔案 sha256 回到原值、加入 `flock` 後**單獨重跑一次**，並以該次結果為準；先前的兩份輸出全部作廢。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `.venv/bin/python -m pytest tests/test_web_api.py tests/test_web_sse.py tests/test_web_chart.py -q` | 0 | `80 passed in 40.46s`（`_limit_value` 重構後） |
| `.venv/bin/python -m pytest -q` | 0 | `709 passed, 2 warnings in 85.81s` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |

## 未執行或受阻

1. **Chrome（Wayland）人工檢查未執行**（無瀏覽器自動化、無可用瀏覽器）：SPEC 第 7 節的目視與手感項目中，與本張有關的是「拖動參數的 1 秒內感受」「貼上與上傳兩種輸入各一次」。替代驗證：`test_preview_answers_within_one_second` 量測伺服器端往返（暖機後遠低於 1 秒），`params.js`／`learn.js` 的轉型與去抖動以 Node 驗證，上傳路徑的程式碼是把檔案讀成文字後走與貼上**完全相同**的請求。仍待交付前在真實瀏覽器完成一次目視與拖動量測。
2. **`attachPanel`／`attachLearnForm` 的實際 DOM 流程未自動測試**（需要瀏覽器或 DOM 模擬器；本專案不引入新依賴）。已測到的是內容接線（id、`data-param`、script）與所有純函式。留待交付前的人工檢查一併涵蓋。
3. **`style.css` 的視覺效果無自動證據**（無畫面快照機制）；僅確認樣式規則存在且不依賴顏色傳達狀態。
