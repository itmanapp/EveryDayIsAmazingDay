# TASK-024：歷史回看頁（表單化 match）

- id：TASK-024
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-046"]
- depends_on：["TASK-020", "TASK-011"]
- test_evidence：["docs/workflow/tdd/TASK-024.md"]
- review_evidence：["docs/workflow/reviews/TASK-024.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：歷史回看頁以表單選擇商品、週期、時間範圍（或根數）、`window`、`top` 與 `horizon` 後，`POST /api/match` 回傳與 CLI `match` 同構的結果：`params`、`data_source`、`matches`（排行，含 index／score／feature_distance）與 `outlook`（`samples`、`up_probability`、`mean_return`、`median_return`、`std_return`）；排序與 `ediaad.similarity.rank` 一致（完全相同者分數 1.0、同分以索引升冪）；頁面明確標示樣本數，`samples == 0` 時顯示「無樣本」而非 0%。
- 本張不做：不做 K 線圖與三相位標註（TASK-022）、參數即時預覽與範例學習（TASK-023）、監控清單管理（TASK-025）、SSE（TASK-021）；不重實作相似度、掃描與後續走勢統計（呼叫 TASK-004／TASK-005／TASK-006 的公開函式）；不改動 CLI `match` 的輸出契約與 exit code 語意（AC-027 由 TASK-011 負責）。
- 每個 AC 在本張負責的範圍：AC-046 全部（以表單方式得到 `match` 的結果：相似片段排行與後續統計，並標示樣本數）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-046、第 5 節 `ediaad/similarity.py` 的 `rank`／`Match`、`ediaad/scan.py` 的 `scan_similar`／`ScanMatch`、`ediaad/outlook.py` 的 `forward_stats`／`OutlookStats`（含 `end_attr` 的雙路線）與 `ediaad/data.py` 的 `load_csv`、第 5 節 HTTP 錯誤格式；`docs/architecture/ENGINEERING-REPORT.md` 第 4.5 節資料流 A（歷史回看：載入 → 特徵 → 掃描 → 統計）與第 3.2 節 G8；`docs/workflow/TASKS.md` 中 TASK-011 已交付 CLI `match`（報表頂層鍵 sample／params／data_source／matches／outlook）作為同構基準。
- 模組與公開介面：`ediaad/web/routes.py` 新增 `POST /api/match`（表單欄位：`symbol`、`interval`、`start`／`end` 或根數、`window`、`top`、`horizon`；回傳 `{"params": ..., "data_source": ..., "matches": [...], "outlook": {...}}`）；實作時優先重用 TASK-011 為 CLI `match` 抽出的共用流程函式（同名或等價的 `run_match(...)`），若不存在則在本張抽出後同時讓 CLI 與 web 共用，不得複製第二份流程；新增 `ediaad/web/static/match.js` 與 `ediaad/web/static/match_page.html`（表單、結果表格與樣本數欄位）。
- 預計觸及的檔案：`ediaad/web/routes.py`、`ediaad/web/static/match.js`、`ediaad/web/static/match_page.html`、`ediaad/web/static/style.css`、`tests/test_web_match.py`；若需抽出共用流程則另動 `ediaad/cli.py` 與其測試；實作前重新查證。
- 必要環境／依賴：TASK-011 的 CLI 流程與報表契約、TASK-004／005／006 的核心函式、TASK-020 的服務骨架；以合成 CSV 與假來源注入，測試不需網路。

## 測試計畫

- 測試公開邊界：`POST /api/match` 的狀態碼與 JSON 結構；與 CLI `match` 報表在頂層鍵與欄位語意上的一致性；排序結果本身（自動）；表單互動與表格顯示（人工）。
- 第一個失敗行為與預期斷言：先寫「當範例視窗與序列中某視窗完全相同時，`matches[0]["score"] == 1.0`，且 `len(matches) <= top`」。實作前該端點回 404；實作後兩項斷言成立。
- 後續例外／邊界情境：無樣本時 `outlook.samples == 0` 且其餘統計欄位為 `null`，回應與頁面皆標示「無樣本」；`start` 晚於 `end`、`window` 大於序列長度或 `top` 不合法時回 400 並指出不合法處；`end + horizon` 超出序列的片段被排除且 `samples` 與排除後的筆數相符；同一輸入重跑結果位元相同（排序同分以索引升冪）。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_web_match.py -q`；相關回歸 `.venv/bin/python -m pytest -q`，並以 `.venv/bin/python -m ediaad match --data ... --sample ... --top ... --horizon ... --out report.json` 比對同一輸入的 `matches`／`outlook`（沿用 `docs/workflow/PROJECT.md` 的指令表）。
- 非程式任務的替代驗證與理由：不適用（AC-046 的後端契約可自動驗證）；表單操作與結果表格（含樣本數可見）以 Chrome（Wayland）人工檢查一次並記錄。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-023 的交付物（全套 **709 passed**），檔案樹 sha256 `eb91266c080c526e71d396a1137cae89ced033f976520e1b874f3aa301c915d6`（63 檔）；本次新增 `ediaad/match.py`、`ediaad/web/static/match.js`、`ediaad/web/static/match_page.html` 與 `tests/test_web_match.py`，並修改 `ediaad/cli.py`（改呼叫共用流程）、`ediaad/web/routes.py`、`ediaad/web/static/index.html`、`ediaad/web/static/style.css`、`tests/test_cli_match_monitor.py`（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-024.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-024.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-web-match` sha256:92a48f6f6039b811521ef6b55d0a6491742e0679922f311fa5f8a14c104f241b（原始碼樹，67 檔）；`ediaad/match.py` `d3f3e4ba…`、`ediaad/cli.py` `23e8152c…`、`ediaad/web/routes.py` `3d45347f…`、`ediaad/web/static/match.js` `f621f0ff…`、`match_page.html` `b82a1fe2…`、`index.html` `3298b747…`、`style.css` `6ed28647…`、`tests/test_web_match.py` `2a90048e…`、`tests/test_cli_match_monitor.py` `32d7c053…`；全套 **753 passed**；變異矩陣 39／39 偵測到（0 存活）
- 取消、重開或變更原因：無
