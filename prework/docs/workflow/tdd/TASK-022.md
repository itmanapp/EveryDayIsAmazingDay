# TASK-022 測試紀錄

- task_id：TASK-022
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-web-chart sha256:a573a7f10592805a8755d74e62a0403e4678ec3246dc2fe6506e341a62d163ce
- alternative_reason：**部分替代**——canvas 的實際渲染外觀無法在無瀏覽器自動化的環境驗證；本張以「同一組幾何值輸出 PNG 並人工目視核對」作為替代驗證（見下），真實 Chrome（Wayland）的目視檢查仍**未執行**
- Task／Spec 版本：TASK-022 / SPEC-001 v0.4
- 測試邊界：（1）後端 JSON 契約與「端點回傳的四個相位索引與直接呼叫 `patterns.detect` 完全相同」；（2）`chart.js` 的索引 → 像素換算以 Node 載入該檔並用假 canvas 驗證；（3）canvas 外觀以 PNG 目視核對。完全離線。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-021 的交付物，全套 **637 passed**（本張完成後為 669 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：見「未執行或受阻」第 1 點（canvas 外觀）與第 2 點（人工目視的程序）。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/web/routes.py` | `364c3ff0` | 修改：`GET /api/series`、`GET /api/patterns/events`、來源解析與規格推導 |
| `ediaad/app.py` | `e20bf1c2` | 修改：`cache_dir`、`catalog` 載入（可選） |
| `ediaad/markets/custom.py` | `ceb58953` | 修改：`CsvSource.fetch` 支援 `limit`（四個來源介面一致） |
| `ediaad/web/static/chart.js` | `e46b8504` | 新增：`makeViewport`／`xFor`／`yFor`／`candleGeometry`／`phaseMarkers`／`summaryLines`／`drawCandles`／`drawPhases`／`renderSummary` |
| `ediaad/web/static/chart_page.html` | `054b8ae3` | 新增：K 線圖頁（canvas ＋ 篩選表單 ＋ 文字摘要區） |
| `ediaad/web/static/chart_page.js` | `05a9b194` | 新增：頁面黏著層（取序列與事件、繪製、列摘要） |
| `ediaad/web/static/index.html` | `017b6934` | 修改：連到 K 線圖頁 |
| `tests/test_web_chart.py` | `478e0ff1` | 新增：30 個測試 |
| `tests/test_markets_base.py` | `70fd170c` | 修改：`CsvSource.limit` 的兩個測試 |

## Cycle 1：序列與事件端點（AC-043，真實 Red → Green）

- 測試：`/api/series` 回六個等長平行陣列 ＋ 時間為 ISO 字串；內容與來源檔逐值相同；`limit` 生效；缺檔回 **502**（`source_failed`，訊息含預期檔名）；未支援週期（以 `source=twse` 驗證，**在連網之前**擋下）回 400；未知來源回 400 並列出可用來源；`limit` 為 `0`／`-5`／`10001`／`abc` 各自 400；**`/api/patterns/events` 的四個索引與直接呼叫 `detect` 逐筆相同**；植入的事件是 `[30, 49, 50, 51]`；**「資料不足」與「評估後沒有命中」以 `status` 區分**（F-003）；事件帶文字摘要所需的欄位；**四索引在 ×0.5 與 +1000 後不變**；索引超出序列範圍的事件被丟棄並記 warning；回報實際使用的 `spec`；市場別（`stock` vs `crypto`）真的改變規格；設定的 `pattern_spec` 覆寫生效；**catalog 決定商品的來源**（要求 twse 不支援的週期 → 400），共 19 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_web_chart.py -q` | 1 | `15 errors`：端點不存在（404）＋ `Application` 沒有 `cache_dir` | 尚未有端點／2026-09-24 |
| Green | 同上 | 0 | `15 passed in 9.71s` | snap-2026-09-24-ocaievo-web-chart／2026-09-24 |

- 實作：`routes.series`／`routes.pattern_events`／`_source_id_for`／`_fetch_series`／`_spec_for`／`_limit_from`；`Application.cache_dir`（監控清單有設定時用它，否則 `<home>/cache`）與 `Application.catalog`（有 `catalog.json` 才載入，壞檔只記 `problems`）。
- **三條接線缺口在本張開始收斂**（都是前面 Task 反覆記錄的項目）：
  1. **來源分派**：`_source_id_for` ＝ 明示 `source` → **catalog 的商品對照** → 預設來源。這是 catalog（TASK-017）第一次真的被用來回答「哪個商品該問哪個來源」，有專門測試（catalog 說 2330 屬 twse → 要求 1h 就必須在連網前被擋下）。
  2. **市場別預設**：`_spec_for` 用 `default_spec_for(settings["market"], {...})`（TASK-015），因此設定裡的 `market` 真的會改變偵測規格；`GET /api/patterns/events` 也回報實際使用的 `spec`（可被斷言、也供 TASK-023 的參數面板對照）。
  3. **設定覆寫**：`pattern_spec` 有值時優先於市場別預設（TASK-019 的鍵在此生效）。
- **F-003 的語意在 API 上明確化**：`status` 為 `insufficient`（資料不足，附需要與實際根數）或 `evaluated`（附「評估後沒有命中」訊息）；兩者都有測試且**不得互相混淆**。
- **超出範圍的索引由後端過濾**（前端只呈現）：`max(indices) >= len(frame) or min(indices) < 0` 時丟棄並 `logger.warning`，回應帶 `dropped` 計數。以 monkeypatch 注入越界事件驗證。
- **如實記載的夾具錯誤**：我第一版照抄了 TASK-008 的**序列**但用錯常數（6／29／30／31），而且端點用的是**命名規格**（`range_fakeout_reversion`，盤整 20～120 根）。TASK-008 的 oracle 用的是**自訂規格**（盤整 5～20 根），兩者條件不同 → 我的夾具在命名規格下完全不命中。已改為 TASK-008 的實際植入位置（盤整 30～49、跌破 50、回歸 51）並以命名規格實測（1 筆命中，索引完全符合）才寫進斷言。

## Cycle 2：前端幾何與頁面（AC-043，真實 Red → Green）

- 測試（**以 Node 載入 `chart.js`**，沒有 `node` 時跳過）：`xFor` 隨索引單調且在繪圖區內、不同索引不同 x；**x 只由索引決定**（相鄰索引差一格、索引 51→73 差 22 格、**將整段價格 ×0.5＋1000 後 x 完全不變**）；`yFor` 反向（價格越高 y 越小）且落在繪圖區內；**三個相位用不同形狀**（`rect`／`triangle-down`／`triangle-up`）且索引正確；**每個標記的 x 等於該索引 K 線的 x**（AC-043 的核心）；`candleGeometry` 畫滿每一根且首末根 x 對應；文字摘要包含三個相位與四個索引與信心值；`chart.js` 以正確的 `Content-Type` 提供；K 線圖頁可取得、含 `canvas` 與 `label`、且首頁有連到它，共 11 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `2 failed, 6 errors`：`chart.js`／`chart_page.html` 不存在、`PROJECT_DIR` 未定義 | 同上／2026-09-24 |
| Green | 同上 | 0 | `23 passed in 10.76s` | 同上／2026-09-24 |

- 實作：`chart.js`（幾何集中在 `xFor`／`yFor`，其餘函式只使用它們；`phaseMarkers` 直接以 `xFor(index)` 決定標記位置，因此「標記與索引一致」是構造上的保證；載入時不碰 DOM，因此可在 Node 裡載入）；`chart_page.html`／`chart_page.js`。
- **為什麼可以在 Node 裡測前端**：`chart.js` 是無依賴的 IIFE、載入時只讀 `window`（以 `typeof window !== "undefined" ? window : globalThis` 兼容 Node），DOM 只在 `renderSummary` 內被碰到。這讓「索引 → 像素」這個 AC 明確要求的性質有**自動**證據，而不是只能靠肉眼。這是**測試期**依賴 Node（正式執行時瀏覽器直接載入該檔，不需要 Node），已用 `pytest.mark.skipif` 讓沒有 Node 的環境仍能跑完其餘測試。
- **如實記載的兩處測試錯誤**：
  1. Node harness 用 `process.argv[2]` 取路徑，但 `node -e <script> <arg>` 的 `argv` 是 `[execPath, arg]`（沒有 script 名稱）→ 改成取最後一個參數。
  2. 「x 只由索引決定」的斷言把 `x[3] - x[2]` 當成一格，但那兩個是索引 49 與 30（19 格）。已改為相鄰索引（29→30）並讓 harness 真的用縮放後的序列再算一次 x 來比較。

## 人工目視核對（替代驗證的實際執行方式）

SPEC 第 7 節人工檢查第 1 項要求「三個相位的 K 線圖標註與偵測結果目視一致」。這個環境沒有瀏覽器自動化，因此我：

1. 以 Node 執行 `chart.js`，取出 `candleGeometry` 與 `phaseMarkers` 的**實際幾何值**。
2. 用同一組幾何值寫出 PNG（純 Python，`zlib` ＋ `struct`，無額外依賴）。
3. 親自檢視該 PNG。

**核對結果**（`/tmp/chart_preview.png`，sha256 `9de1deeb…`）：虛線矩形正好涵蓋索引 30～49 的 K 線（x 345→535）、紅色下三角位於區間右緣的**下一根**且在其低點之下（x 545）、綠色上三角再往後一根且在其高點之上（x 555）；三者互不重疊；索引 29 的深谷（低點 90）與索引 55 的尖峰（高點 120）都落在正確的價格位置（垂直位置與 y 軸一致）。

**這個替代驗證的界線（如實記載）**：它驗證的是**幾何值畫出來的位置正確**，不是瀏覽器 `<canvas>` 的實際渲染（線寬、字型、抗鋸齒、HiDPI 縮放、深色模式下的對比）。後者仍需 Chrome 人工檢查。

## Cycle 3（補測）：變異檢查後移除一處冗餘驗證

- **M11（移除 `limit` 的範圍檢查）首次存活**，追查後發現路由自己寫的**下限**檢查是多餘的：四個來源的 `fetch` 都會驗證 `limit >= 1`（本張也讓 `CsvSource` 支援 `limit` 並驗證），因此 `limit=0` 仍會得到 400。但**上限**（`MAX_SERIES_LIMIT`）是路由層才有的政策（避免任何來源都能讓這個端點產生無界 JSON）。已改成只檢查上限、把下限交給來源，並補 `10001` 的測試 → M11 立刻被抓到。**與 TASK-013 M16、TASK-019 M17 同型：移除冗餘驗證而不是補測試。**

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 序列端點少回一個陣列 | 被抓到 |
| M2 | 事件端點不過濾超出範圍的索引 | 被抓到 |
| M3 | 資料不足與無命中共用同一狀態 | 被抓到 |
| M4 | 無命中的訊息說成資料不足 | 被抓到 |
| M5 | 忽略設定裡的 `pattern_spec` 覆寫 | 被抓到 |
| M6 | 一律使用 crypto 預設（忽略市場別） | 被抓到 |
| M7 | 序列端點忽略 `limit` | 被抓到 |
| M8 | 忽略明示的 `source` 參數 | 被抓到 |
| M9 | 不查 catalog（一律用預設來源） | 被抓到 |
| M10 | 事件端點不回報規格 | 被抓到 |
| M11 | 序列端點不管 `limit` 上限 | **首次存活 → 移除冗餘下限並補上限測試後被抓到** |
| M12 | 自訂 CSV 的 `limit` 不生效 | 被抓到 |
| M13 | app 不載入 catalog | 被抓到 |
| M14 | `xFor` 不取槽位中心 | 被抓到 |
| M15 | `yFor` 不反向 | 被抓到 |
| M16 | 相位標記的索引對調 | 被抓到 |
| M17 | 三個相位共用同一形狀 | 被抓到 |
| M18 | 文字摘要不含相位索引 | 被抓到 |
| M19 | `candleGeometry` 只畫一根 | 被抓到 |
| M20 | `chart.js` 不匯出 `phaseMarkers` | 被抓到 |
| M21 | 首頁不連到 K 線圖頁 | 被抓到 |

工具紀律：整行比對、`count(frm) == 1` 才執行、每次變異後立即還原並比對檔案 sha256；每次執行有 90 秒上限。矩陣在**最終版檔案**上重跑過（另移除一個未使用的匯入之後），21／21 全數被抓到；還原後 `ediaad/web/routes.py` `364c3ff0`、`app.py` `e20bf1c2`、`markets/custom.py` `ceb58953`、`chart.js` `e46b8504` 與變異前一致，單檔 `30 passed`。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_web_chart.py -q` | 0（`30 passed in 15.60s`） | snap-2026-09-24-ocaievo-web-chart |
| 相關回歸（來源介面） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_markets_base.py -q` | 0（`43 passed`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`669 passed in 64.28s`） | 同上 |
| 未使用匯入掃描 | `ocaievo/`：AST 粗檢 `ediaad/` | 0（先抓到 `SERIES_COLUMNS` 未使用並移除） | 同上 |
| 人工目視核對（替代驗證） | `/tmp`：以同一組幾何值輸出 PNG 後目視 | 位置與索引一致（見上節） | `/tmp/chart_preview.png` sha256 `9de1deeb…` |
| 變異後還原驗證 | 同本張單檔 | 0（`30 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

1. **SPEC 第 7 節人工檢查第 1 項的「真實瀏覽器」版本未執行**：沒有瀏覽器自動化環境，因此沒有在 Chrome（Wayland）實際打開 `chart_page.html` 目視。替代驗證（幾何值渲染 ＋ 目視）已完成並記錄，但它**不涵蓋** canvas 的實際渲染細節（線寬、字型、HiDPI、深色模式對比）。交付前應在 Chrome 補做並記錄。
2. **`chart_page.html` 的前端流程未自動測試**：`chart_page.js`（取序列、繪製、列摘要）只有「檔案存在、被頁面載入、頁面含 canvas 與 label」的內容斷言；實際的取資料→繪圖流程靠人工檢查。
3. 已知邊界（記錄）：
   - `/api/series` 與 `/api/patterns/events` 的序列範圍是**最近 `limit` 根**（預設 500），因此相位索引相對於該範圍；若資料檔很長，兩者一致但與整份檔案不同（已在回應帶 `count`／`bars`）。
   - `Application.catalog` 目前只被用來決定來源；商品清單的管理（`GET/POST /api/watchlist`）仍是 TASK-025。
   - 來源的 `fetch` 簽名統一為 `(symbol, interval, limit=...)`：本張為 `CsvSource` 補上 `limit`（TASK-012 的交付物），另外三個來源原本就支援。
   - `chart.js` 的繪圖是最小實作（無縮放、平移、十字游標、成交量副圖）；報告的 G 系列只要求「畫得出並標註相位」。
   - 圖表沒有成交量面板與座標軸刻度標籤（只畫價格走勢）；文字摘要補足可讀性。
- 未涵蓋：參數即時預覽與範例學習（TASK-023）、歷史回看（TASK-024）、監控清單與系統狀態頁（TASK-025）、啟動器（TASK-026）、通知（TASK-027）。
