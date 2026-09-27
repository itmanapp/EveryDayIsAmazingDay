# TASK-022 Code Review

- task_id：TASK-022
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-web-chart sha256:a573a7f10592805a8755d74e62a0403e4678ec3246dc2fe6506e341a62d163ce
- Task／Spec 版本：TASK-022 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含冗餘驗證的移除、夾具修正與人工目視的替代做法）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `a573a7f10592805a8755d74e62a0403e4678ec3246dc2fe6506e341a62d163ce`；本張新增 `ediaad/web/static/chart.js` `e46b8504…`、`chart_page.html` `054b8ae3…`、`chart_page.js` `05a9b194…`、`tests/test_web_chart.py` `478e0ff1…`；修改 `ediaad/web/routes.py` `364c3ff0…`、`ediaad/app.py` `e20bf1c2…`、`ediaad/markets/custom.py` `ceb58953…`、`ediaad/web/static/index.html` `017b6934…`、`tests/test_markets_base.py` `70fd170c…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的已提交、未提交、新增檔案：上述九個檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`patterns.py`／`store.py`／`config.py`／`markets/{base,twse,crypto,us,adjust,calendar,catalog}.py` 本張只呼叫未修改；`markets/custom.py` 例外（補 `limit`，見 A-4）
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-043、第 5 節 `patterns.py` 的 `PatternEvent` 與 `detect`、第 6 節可及性（形狀／文字標註 ＋ 文字摘要）、第 7 節人工檢查第 1 項；`docs/architecture/ENGINEERING-REPORT.md` 第 2.4 節相位定義、第 4.4 節 `PatternEvent`、第 6.3 節（canvas 從 JSON 繪製、不需 matplotlib）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-043 | `ediaad/web/routes.py`（`series`／`pattern_events`）、`ediaad/web/static/chart.js`、`chart_page.html`；`tests/test_web_chart.py` 30 個案例 | 符合 | A-1～A-6（advisory） |

逐條核對：

- **AC-043「`GET /api/series` 回傳六個欄位的陣列」**：六個等長平行陣列 ＋ 時間為 ISO 字串；內容與來源檔逐值相同（有斷言）。符合。
- **AC-043「`GET /api/patterns/events` 的四個索引與直接呼叫 `detect` 完全相同」**：以同一個序列分別走端點與 `detect`，逐筆比對四個索引、`pattern_id` 與事件數。符合。
- **AC-043「canvas 繪出 OHLC」**：`candleGeometry` 對每一根產生 `{x, highY, lowY, openY, closeY, rising}` 並由 `drawCandles` 畫出影線與實體（漲跌不同色）；以 Node 驗證 74 根的幾何與首末 x。符合。
- **AC-043「盤整／跌破／回歸以不同形狀與文字標註」**：三個標記的 `shape` 為 `rect`／`triangle-down`／`triangle-up`（有斷言），`drawPhases` 為每個標記畫出對應形狀**並以文字寫出相位名稱**；另有 `summaryLines`／`renderSummary` 提供與圖相同的文字摘要。符合。
- **AC-043「標記的水平位置由事件索引換算並與 JSON 索引一致」**：`phaseMarkers` 直接以 `xFor(index)` 決定位置，測試斷言每個標記的 `x` 等於該索引 K 線的 `x`（並以縮放後的序列證明 x 與價格無關）。符合。

## 品質 Review

- **「標記位置與索引一致」是構造上的保證，不是靠對齊**：`phaseMarkers` 與 `candleGeometry` 都只經過同一個 `xFor(index, viewport)`，因此標記不可能偏移。測試再從外部以 Node 驗證，形成雙重保障。這比「在畫圖時另外算一次位置」可靠得多（那正是這類標註最容易出現 off-by-one 的地方）。
- **幾何可測（本張最重要的架構決定）**：`chart.js` 是無依賴 IIFE、**載入時不碰 DOM**、把幾何抽成純函式，因此可以在 Node 裡載入並斷言像素值。否則 AC-043 中「位置與索引一致」只能靠肉眼，而肉眼對 off-by-one 與 y 軸反向都不敏感。代價是測試期需要 `node`（以 `skipif` 處理，正式執行不需要）。
- **接線缺口開始收斂（三項）**：`_source_id_for`（明示來源 → **catalog 商品對照** → 預設來源）、`_spec_for`（`pattern_spec` 覆寫 → 市場別預設 ＋ `pattern_id`）、`_limit_from`。TASK-013 以來記錄的缺口清單中，「來源分派」「市場別預設」「設定生效」三項在此首次有了實際消費者，且各有測試（catalog 的案例用「twse 只支援日線」來證明來源真的被 catalog 決定）。
- **F-003 的語意在 API 上明確化**：`status` 分成 `insufficient`（附需要與實際根數）與 `evaluated`（附「沒有命中」訊息），兩者不得混淆——這讓前端不會把「無法評估」畫成「沒有訊號」。變異 M3／M4 分別證明兩條路徑都有測試。
- **超出範圍的索引由後端過濾**：前端只呈現（不自行推導），因此「索引在序列範圍內」必須由後端保證；越界事件被丟棄、記 warning、並以 `dropped` 回報。以注入越界事件驗證。
- **冗餘驗證的移除（M11 的收穫）**：路由自己寫的 `limit` **下限**檢查與四個來源的重複；已移除、把下限交給來源，只保留路由層才有的**上限政策**（避免無界 JSON）。與 TASK-013 M16、TASK-019 M17 同型：**移除冗餘碼而不是補測試**。
- **可及性**：相位用**不同形狀 ＋ 文字**（不只顏色）、`<canvas role="img" aria-label="…">`、表單每個控制項都有 `label`、`aria-live` 狀態、並提供與圖相同的文字摘要區（`summaryLines` 逐條列出相位與索引）。符合 SPEC 第 6 節。
- **依賴與邊界**：`chart.js` 無外部依賴（不用圖表庫、不用 Node 建置）；`routes.py` 只呼叫既有核心函式；web 層沒有重跑偵測、沒有自行推導相位；四個來源的 `fetch` 介面統一為 `(symbol, interval, limit=…)`（本張為 `CsvSource` 補上 `limit`）。
- **測試品質**：後端以真實 HTTP 請求觀察 JSON；幾何以 Node 執行真實檔案（不是重寫一份 JS）；事件索引以「與 `detect` 逐筆相同」與「植入的固定索引」雙重固定；尺度不變以 ×0.5 與 +1000 兩個方向對照。未發現新的問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 缺口（沿用 TASK-013 A-1～021 A-1） | advisory（**需在後續 Task 處理**） | 服務仍**不會自己跑監控**：`Application.make_emit()` 有接縫但沒人呼叫 `run_once`；`Store` 的寫入端也還沒接上。網頁只能看歷史與已快取的序列 | TASK-025 應完成：監控執行緒（`run_once` ＋ `Store` 讀寫）、`GET/POST /api/watchlist`、系統狀態頁（含各商品來源與除權息狀態） | 待辦（已記於 `STATE.md` 待決事項） |
| A-2 | 真實瀏覽器檢查 | advisory（**未執行**） | SPEC 第 7 節人工檢查第 1 項要求 Chrome 目視核對；本環境沒有瀏覽器，改以「同一組幾何值輸出 PNG 並目視」替代 | 交付前在 Chrome（Wayland）打開 `/static/chart_page.html`，核對標註位置、字型、HiDPI 與深色模式對比 | 待辦（交付前人工檢查；替代驗證已記錄於 TDD） |
| A-3 | 前端流程未自動測試 | advisory | `chart_page.js`（取序列 → 繪製 → 列摘要）只有內容斷言；實際流程靠人工 | 交付前的人工檢查應涵蓋：改週期、切換來源、無命中與資料不足兩種狀態的畫面文字 | 待辦（交付前人工檢查） |
| A-4 | 範圍調整 | advisory（需追認） | `ediaad/markets/custom.py`（TASK-012 的交付物）補上 `limit` 參數，使四個來源的 `fetch` 介面一致 | 已在 `tests/test_markets_base.py` 補兩個測試；建議在 SPEC 第 5 節的 `Source` 契約註明 `limit` 的語意（取最近 N 根） | 待追認（已完成） |
| A-5 | 圖表功能範圍 | advisory | `chart.js` 是最小實作：無縮放／平移、無成交量副圖、無座標軸刻度標籤 | 報告的 G 系列只要求「畫得出並標註相位」；若日後要做縮放與刻度，需另外設計（並保留幾何可測的結構） | 延後（無現時需求） |
| A-6 | 流程紀律 | advisory（非程式） | 第一版夾具照抄 TASK-008 的序列卻用錯常數、且沒有注意端點用的是命名規格（TASK-008 的 oracle 用自訂規格）；Node harness 的 `argv` 取錯索引；`x[3]-x[2]` 誤認為一格 | 已全部在 TDD 紀錄如實記載。教訓：重用別人的夾具時要連「它用哪個規格」一起確認；跨語言呼叫先驗證參數傳遞 | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-043 逐條符合；品質 Review 無 blocking。
- 依變異檢查移除一處冗餘驗證（`limit` 下限，M11）；依測試回饋修正夾具（植入位置與規格認定）、Node harness 的參數索引與幾何斷言的索引間距。
- 移除 1 個未使用的匯入（`SERIES_COLUMNS`）並在最終版檔案上重跑變異矩陣（21／21 全數被抓到）。
- 重審：重跑單檔（30 passed）、相關回歸（43 passed）與全套（669 passed）；重讀 `routes.py`／`chart.js` 複查來源解析、規格推導、F-003 的狀態語意、越界過濾與幾何集中性。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-043 的五項宣稱逐條符合）
- 品質 Review：passed（無 blocking；A-1 需在後續 Task 落實，A-2／A-3 為交付前人工檢查，A-4 需追認，A-5／A-6 已記錄）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-025）、A-2／A-3（交付前人工檢查）、A-4（需 Spec 補充）、A-5（無現時需求）、A-6（流程記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：真實瀏覽器渲染未驗證（已用幾何渲染替代）；`chart_page.js` 的流程未自動測試；圖表無縮放／成交量／刻度；序列範圍預設最近 500 根；服務仍不會自己跑監控
