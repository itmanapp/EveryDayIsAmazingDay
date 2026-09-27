# TASK-037：整合驗收、AC 對照與 DELIVERY

- id：TASK-037
- type：docs
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-065"]
- depends_on：["TASK-001", "TASK-002", "TASK-003", "TASK-004", "TASK-005", "TASK-006", "TASK-007", "TASK-008", "TASK-009", "TASK-010", "TASK-011", "TASK-012", "TASK-013", "TASK-014", "TASK-015", "TASK-016", "TASK-017", "TASK-018", "TASK-019", "TASK-020", "TASK-021", "TASK-022", "TASK-023", "TASK-024", "TASK-025", "TASK-026", "TASK-027", "TASK-028", "TASK-029", "TASK-030", "TASK-031", "TASK-032", "TASK-033", "TASK-034", "TASK-035", "TASK-036"]
- test_evidence：["docs/workflow/tdd/TASK-037.md"]
- review_evidence：["docs/workflow/reviews/TASK-037.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：在**同一份檔案快照**上實際執行並如實記錄三個命令的 exit code 與輸出摘要——專案根 `.venv/bin/python -m pytest -q`、`cloudflare/` 下 `node --test`、專案根 `python3 .project-workflow/scripts/validate_workflow.py .`；產出 `docs/workflow/DELIVERY.md`，內容包含（a）66 項 active AC 的對照表，每列有 AC ID、負責 Task、實作位置（檔案與公開函式）、驗證證據（測試檔／案例名／人工檢查）、結果與證據路徑，（b）已完成清單，（c）未驗證清單（真實 Cloudflare 帳號／D1／網域與部署、macOS／Windows 桌面通知、Twelve Data 真實金鑰與額度、自動下載安裝、跨瀏覽器視覺回歸），（d）已知限制（客戶端授權只能防君子、統計未處理片段相關性、預設規格偏保守、除權息還原依 TWSE 欄位），（e）任何未執行或失敗的檢查逐項標示原因與解除條件；並使 `docs/workflow/TASKS.md` 與 `docs/workflow/STATE.md` 與各張 Task 檔的實際狀態同步。
- 本張不做：不修改產品程式碼（只做唯讀檢查與文件；發現缺陷時開新 Task、把原 Task 標為 blocked，或記入 DELIVERY 的未驗證／未通過清單，不就地偷改）；不部署任何東西；不執行 `git`／`push`／開 Issue／合併；不發布版本；**不宣稱任何未實際執行的檢查通過**；不以既有 `~/桌面/DSH/ediaad` 的 185 個案例通過代替本專案驗證；不修改 SPEC 的 AC 內容。
- 每個 AC 在本張負責的範圍：AC-065 全部。本張是 SPEC 第 7 節與 `TASKS.md` 指定的「全部 active AC 的最終整合驗證負責 Task」，負責彙整證據與揭露未驗證項，但不重複各 AC 的單元實作，也不把各張 Task 的自我宣告當成證據（以可重跑的命令輸出與證據檔案為準）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-065、第 7 節全部測試策略列與「必要的人工／視覺檢查」、「不適用的方式及原因」（無瀏覽器自動化、無 macOS／Windows 實機、無 Cloudflare 部署授權）、第 8 節風險與未決；`docs/workflow/TASKS.md` 的 AC 覆蓋表；`docs/workflow/PROJECT.md` 的「必須通過的最終檢查」（pytest、`validate_workflow.py`、`node --test`）與「確認與授權」（commit／push／Issue／合併／部署一律未授權、未 `git init`）；`docs/architecture/ENGINEERING-REPORT.md` 第 8.1／8.2 節設計取捨與已知限制、附錄 C 程式碼規模；`.project-workflow/references/validation.md`（穩定欄位與證據契約）。
- 模組與公開介面：不新增程式模組；交付文件 `docs/workflow/DELIVERY.md`。觀察邊界只有三個既有命令（pytest、`node --test`、`validate_workflow.py`）與各張 Task 的 `test_evidence`／`review_evidence` 所指的紀錄檔。
- 預計觸及的檔案：`docs/workflow/DELIVERY.md`（本張建立）、`docs/workflow/TASKS.md`（同步狀態與 AC 對照）、`docs/workflow/STATE.md`（同步階段與統計）；唯讀查閱 `docs/workflow/tdd/*`、`docs/workflow/reviews/*`、各 `docs/workflow/tasks/TASK-0NN.md`、`docs/workflow/evidence/`；實作前重新查證。
- 必要環境／依賴：`.venv`（含 `pytest`）＋ Node v24.21.0；全部自動測試需離線可跑（假 HTTP／假來源／假 D1）；Cloudflare 部分只在本機執行 `node --test`；不得使用網路或任何真實外部服務作為驗收依據。

## 測試計畫

- 測試公開邊界：三個命令的 exit code 與輸出摘要，加上 `docs/workflow/DELIVERY.md` 的 AC 對照表本身（每項 active AC 恰一列、含實作位置、證據路徑與結果）。
- 第一個失敗行為與預期斷言：`docs/workflow/DELIVERY.md` 不存在時，檢查 `test -f docs/workflow/DELIVERY.md` 失敗；建立後斷言檔案中 65 個 active AC ID 各出現恰一次於對照表，且每一列指向的證據路徑都存在（以 `.venv/bin/python - <<'PY'` 或等價的唯讀檢查腳本核對，不改動產品程式碼）。
- 後續例外／邊界情境：
  1. 任一 AC 找不到實作位置或證據 → 該列標為「未驗證」並寫明原因；DELIVERY 不得整體宣告「全部通過」。
  2. 對照表指到的證據路徑不存在 → 檢查失敗並列出缺漏清單。
  3. 全套測試有失敗案例 → 如實記錄 exit code、失敗案例名稱與原始輸出摘要，不得改寫成通過；對應 Task 不得標為 done。
  4. `validate_workflow.py` 失敗（例如引用不存在的 AC 或 Task、`depends_on` 循環、`done` 缺少證據）→ 阻擋交付，先修正文件再重跑。
  5. 各張 Task 的 `test_evidence`／`review_evidence` 與 TASKS／STATE 摘要不一致 → 以單張 Task 檔為權威來源修正摘要，並在 DELIVERY 記錄差異與處理方式。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest -q` 與 `python3 .project-workflow/scripts/validate_workflow.py .`；`cloudflare/` 下執行 `node --test`；沿用 `docs/workflow/PROJECT.md` 的「必須通過的最終檢查」。
- 非程式任務的替代驗證與理由：本張為 `docs`，主要產物是驗收與對照文件，「文件內容是否忠實」無法用單元測試證明；因此改以可重跑的命令 exit code、證據路徑存在性、66 項 active AC 的覆蓋計數，以及 DELIVERY 是否逐項標示未驗證／失敗作為替代驗證，並在 TDD 紀錄保存實際命令與原始輸出摘要。本張不新增測試檔。
- 必要的人工檢查：逐項核對 DELIVERY 的未驗證清單與 SPEC 第 2 節 out of scope、PROJECT.md「已知的未授權／未驗證邊界」是否一致；確認沒有把未執行的檢查寫成通過；確認未執行任何部署或 git 指令。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：開工前 `ocaievo/` 已有 TASK-001～TASK-036 的交付物，檔案樹 sha256 `ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab`（122 檔，即 TASK-036 的 `checked_version`）。**本張未修改任何產品程式碼**，驗收後檔案樹 sha256 相同；唯一的變更是四份文件（`docs/workflow/DELIVERY.md`、`TASKS.md`、`STATE.md`、本張 TDD／Review）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-037.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-037.md`）
- 目前被驗證版本／檔案狀態：產品樹 `snap-2026-09-24-ocaievo-cli-serve-license` sha256:ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab（122 檔，與 TASK-036 相同）；驗收：`.venv/bin/python -m pytest -q` **1007 passed ×3**、`node --test` **82 passed**、`validate_workflow.py` exit 0、`check_tasks.py` exit 0、對照表完整性檢查 exit 0（66 列）；交付報告 `docs/workflow/DELIVERY.md`
- 取消、重開或變更原因：無
