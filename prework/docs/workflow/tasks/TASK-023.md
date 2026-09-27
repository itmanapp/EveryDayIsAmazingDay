# TASK-023：規律參數即時預覽與範例學習頁

- id：TASK-023
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-044","AC-045"]
- depends_on：["TASK-020", "TASK-008", "TASK-009"]
- test_evidence：["docs/workflow/tdd/TASK-023.md"]
- review_evidence：["docs/workflow/reviews/TASK-023.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：在已選商品與週期的參數面板改動任一白話參數後，`POST /api/pattern/preview` 在 1 秒內回傳該商品在此參數下的命中次數（`{"hits": n, "params": {...}}`，`n` 等於以同一參數呼叫 `ediaad.patterns.detect` 的事件數）；改回原值得到原本次數、同一輸入重跑結果位元相同（無隨機性）；範例學習頁可貼上或上傳 CSV，按「學習」後 `POST /api/pattern/learn` 回傳推估的 `PatternSpec`（依 `PatternSpec` 契約序列化）與在目前商品上的命中預覽；無法推估時回 400 並附明確原因訊息。
- 本張不做：不做設定的儲存與監控清單管理（屬 TASK-025）、K 線圖（TASK-022）、歷史回看（TASK-024）、SSE（TASK-021）；不重實作規律判定與範例學習（呼叫 TASK-008 的 `detect`、TASK-009 的 `learn`）；不在瀏覽器端實作任何判定或推估；不引入前端框架或新依賴。
- 每個 AC 在本張負責的範圍：AC-044 全部（不需存檔即在 1 秒內顯示命中次數、改回原值可重現）；AC-045 全部（顯示推估參數與命中預覽、無法推估時顯示明確原因）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-044／AC-045、第 5 節 `ediaad/patterns.py` 的 `detect`／`learn`／`PatternSpec`（含 `to_json` 的穩定鍵序）與 `ediaad/data.py` 的 `load_csv` 契約、第 6 節效能（參數預覽與 SSE 推播 1 秒內）與第 8 節風險 1、3（預設值保守、單一範例可能過擬合，需顯示推估參數供檢視）；`docs/architecture/ENGINEERING-REPORT.md` 第 5.7 節範例學習與第 3.2 節 G4／G5；`docs/workflow/CONTEXT.md` 的「範例學習」與「規律規格」。
- 模組與公開介面：`ediaad/web/routes.py` 新增 `POST /api/pattern/preview`（body 至少含 `symbol`、`interval` 與白話參數；只回命中次數與實際採用的參數，不回傳完整事件清單）與 `POST /api/pattern/learn`（body 為範例 CSV 文字或上傳內容；成功回 `PatternSpec` JSON 與命中預覽，失敗回 `ConfigError` 的訊息與欄位位置）；新增 `ediaad/web/static/params.js`（白話參數 ↔ `PatternSpec` 欄位對應、輸入變更後的去抖動呼叫與次數顯示）與 `ediaad/web/static/learn.js`（貼上／上傳、結果與錯誤渲染）。
- 預計觸及的檔案：`ediaad/web/routes.py`、`ediaad/web/static/params.js`、`ediaad/web/static/learn.js`、`ediaad/web/static/index.html`、`ediaad/web/static/style.css`、`tests/test_web_preview_learn.py`；實作前重新查證（特別是 TASK-009 的 `learn` 回傳值與失敗訊息格式）。
- 必要環境／依賴：TASK-008（`detect`）、TASK-009（`learn`）、TASK-020（服務骨架）；範例 CSV 沿用 `ediaad/data.py` 的 `load_csv`（TASK-002）；合成序列與合成範例即可，測試不需網路；人工量測需 Chrome（Wayland）。

## 測試計畫

- 測試公開邊界：`POST /api/pattern/preview` 與 `POST /api/pattern/learn` 的 JSON 回應與狀態碼；以合成序列與合成範例注入，完全離線。
- 第一個失敗行為與預期斷言：先寫「同一商品與同一參數呼叫 `/api/pattern/preview` 兩次，兩次 `hits` 相等，且等於直接以該參數呼叫 `ediaad.patterns.detect` 的事件數」。實作前該端點回 404；實作後兩次相等且與核心函式一致。
- 後續例外／邊界情境：不合法參數（`range_bars_min > range_bars_max`、負數、未知 `recovery_target`）回 400 並附 `ConfigError` 的可讀訊息、不落 traceback；非數值或空白參數回 400 並指出欄位；範例長度不足或無法推估時回 400 並附明確原因，且不得回傳隨意參數；同一範例重跑兩次推估結果完全相同；把參數改回原值時 `hits` 回到原本次數。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_web_preview_learn.py -q`；相關回歸 `.venv/bin/python -m pytest -q`。
- 非程式任務的替代驗證與理由：不適用（兩個 AC 的後端行為皆可自動驗證）；「1 秒內」的使用者感受需在 Chrome（Wayland）實際拖動參數量測一次並記錄，貼上與上傳兩種範例輸入各測一次。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-022 的交付物（全套 **669 passed**），檔案樹 sha256 `a573a7f10592805a8755d74e62a0403e4678ec3246dc2fe6506e341a62d163ce`（60 檔）；本次新增 `ediaad/web/static/params.js`、`ediaad/web/static/learn.js` 與 `tests/test_web_preview_learn.py`，並修改 `ediaad/web/routes.py`、`ediaad/web/static/index.html`、`ediaad/web/static/style.css`（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-023.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-023.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-web-preview-learn` sha256:eb91266c080c526e71d396a1137cae89ced033f976520e1b874f3aa301c915d6（原始碼樹，63 檔）；`ediaad/web/routes.py` `9f3ddc91…`、`ediaad/web/static/params.js` `2c60ec9f…`、`ediaad/web/static/learn.js` `8b42bcfd…`、`ediaad/web/static/index.html` `60bcc253…`、`ediaad/web/static/style.css` `ab572dd9…`、`tests/test_web_preview_learn.py` `7f62eb32…`；全套 **709 passed**；變異矩陣 30／30 偵測到（0 存活）
- 取消、重開或變更原因：無
