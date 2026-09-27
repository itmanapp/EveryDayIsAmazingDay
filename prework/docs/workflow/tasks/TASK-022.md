# TASK-022：K 線圖與三相位標註

- id：TASK-022
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-043"]
- depends_on：["TASK-020", "TASK-008"]
- test_evidence：["docs/workflow/tdd/TASK-022.md"]
- review_evidence：["docs/workflow/reviews/TASK-022.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`GET /api/series?symbol=&interval=&limit=` 回傳序列的 `time`／`open`／`high`／`low`／`close`／`volume` 陣列，`GET /api/patterns/events?symbol=&interval=` 回傳的事件含 `range_start_index`、`range_end_index`、`breakdown_index`、`recovery_index`，四者與直接呼叫 `ediaad.patterns.detect` 同一序列的結果完全相同；頁面以 `<canvas>` 繪出 OHLC，盤整／跌破／回歸以不同形狀與文字標註，標記的水平位置由事件索引換算並與 JSON 索引一致；另提供與圖相同的文字摘要（不得只靠顏色辨識相位）。
- 本張不做：不做相似片段路線與歷史回看（AC-046 屬 TASK-024）、參數即時預覽與範例學習（TASK-023）、SSE 即時更新（TASK-021）、監控清單管理（TASK-025）；不在瀏覽器端重跑 `detect` 或自行推導相位（相位一律由後端核心函式產生，前端只呈現）；不引入 matplotlib、前端圖表庫或 Node 建置工具鏈。
- 每個 AC 在本張負責的範圍：AC-043 全部（canvas 繪出 OHLC、三個相位以不同標記標出、標記位置與事件索引一致）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-043、第 5 節 `ediaad/patterns.py` 的 `PatternEvent`（四個相位索引）與 `detect`、第 6 節可及性（K 線圖以形狀／文字標註相位並提供文字摘要）與第 7 節人工檢查第 1 項；`docs/architecture/ENGINEERING-REPORT.md` 第 2.4 節相位定義、第 4.4 節 `PatternEvent`、第 6.3 節（K 線圖用瀏覽器 `<canvas>` 從 JSON 繪製，不需要 matplotlib）；`docs/workflow/CONTEXT.md` 的「相位」與「規律事件」。
- 模組與公開介面：`ediaad/web/routes.py` 新增 `GET /api/series`（序列化來源 `fetch` 的結果，缺欄位或缺資料時回可讀訊息）與 `GET /api/patterns/events`（只呼叫 `ediaad.patterns.detect` 並序列化事件，不新增判定邏輯）；新增 `ediaad/web/static/chart.js`，對外為 `drawCandles(ctx, bars, viewport)`、`drawPhases(ctx, phases, viewport)`、`renderSummary(el, event)`，座標換算集中在單一 `xFor(index)`／`yFor(price)`；新增 `ediaad/web/static/chart_page.html` 掛載 canvas 與摘要區。
- 預計觸及的檔案：`ediaad/web/routes.py`、`ediaad/web/static/chart.js`、`ediaad/web/static/chart_page.html`、`ediaad/web/static/style.css`、`tests/test_web_chart.py`；實作前重新查證（特別是 TASK-008 的 `PatternEvent` 欄位名與 `detect` 簽名）。
- 必要環境／依賴：TASK-008 的 `ediaad.patterns.atr`／`detect`／`PatternEvent`；TASK-012 起的來源 registry 與 TASK-020 的服務骨架；瀏覽器原生 `<canvas>`；人工檢查需 Chrome（Wayland）。

## 測試計畫

- 測試公開邊界：`GET /api/series` 與 `GET /api/patterns/events` 的 JSON 契約與索引一致性（自動）；canvas 實際繪製與標註外觀（人工視覺檢查）。
- 第一個失敗行為與預期斷言：先寫「對 TASK-008 的 oracle 植入序列呼叫 `GET /api/patterns/events`，回傳事件的 `range_start_index`／`range_end_index`／`breakdown_index`／`recovery_index` 與直接呼叫 `patterns.detect` 的同一事件逐一相等」。實作前該端點回 404；實作後 200 且四索引相等、事件數相同。
- 後續例外／邊界情境：序列長度不足回「資料不足／無法評估」訊息（不得回空圖，也不得與「評估後無命中」混淆，對應 F-003 的語意）；事件索引超出回傳序列範圍時不得被畫出並記 warning；整段價格乘 0.5 或加常數後重取事件，四索引不變（尺度不變在呈現層的對照）；`GET /api/series` 對未支援的週期回可讀錯誤而非 500。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_web_chart.py -q`；相關回歸 `.venv/bin/python -m pytest -q`。
- 非程式任務的替代驗證與理由：不適用（後端契約可自動驗證）；canvas 的相位標註外觀無法在無瀏覽器自動化工具的環境自動驗證，依 SPEC 第 7 節以 Chrome（Wayland）人工目視核對「三個相位的標記位置與文字摘要和事件索引一致」，並將檢查結果記入 TDD 紀錄的替代驗證欄位。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-021 的交付物（全套 637 passed）；本次新增 `ediaad/web/static/chart.js`、`chart_page.html`、`chart_page.js` 與 `tests/test_web_chart.py`，並修改 `ediaad/web/routes.py`、`ediaad/app.py`、`ediaad/markets/custom.py`（補 `limit`）、`ediaad/web/static/index.html`、`tests/test_markets_base.py`（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-022.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-022.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-web-chart` sha256:a573a7f10592805a8755d74e62a0403e4678ec3246dc2fe6506e341a62d163ce（原始碼樹，60 檔）；新增 `ediaad/web/static/chart.js` `e46b8504…`、`chart_page.html` `054b8ae3…`、`chart_page.js` `05a9b194…`、`tests/test_web_chart.py` `478e0ff1…`；全套 `669 passed`；人工目視替代驗證的 PNG sha256 `9de1deeb…`
- 取消、重開或變更原因：無
