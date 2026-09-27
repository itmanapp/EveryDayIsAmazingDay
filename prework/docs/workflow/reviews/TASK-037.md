# TASK-037 Code Review（整合驗收與交付報告）

- task_id：TASK-037
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-cli-serve-license sha256:ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab
- Task／Spec 版本：TASK-037 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-25，第 1 輪（含對照表完整性檢查的 Red → Green、狀態一致性複核與未驗證項的逐項核對）
- 基準 SHA／前置快照：開工前 `ocaievo/` 檔案樹 sha256 `ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab`（122 個檔案，即 TASK-036 的 `checked_version`）；本張**未修改產品程式碼**，驗收後的檔案樹 sha256 相同
- 審查目標／檔案雜湊：四份文件（`docs/workflow/DELIVERY.md`、`TASKS.md`、`STATE.md`、`tdd/TASK-037.md`／`reviews/TASK-037.md`）；產品樹與 TASK-036 相同（逐檔 sha256 見各張 Review）
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以檔案快照 sha256 與唯讀檢查腳本比對
- 納入的檔案：`docs/workflow/DELIVERY.md`（本張主要產物）、`docs/workflow/TASKS.md`、`docs/workflow/STATE.md`、本張 TDD／Review 紀錄
- 排除的既有修改及理由：**所有產品程式碼**（`ocaievo/` 內 122 個檔案）本張只讀取未修改；各張 Task 的 TDD／Review 只被引用未改寫
- 程式規範來源：`docs/workflow/SPEC.md` AC-065、第 7 節（全部測試策略列、「必要的人工／視覺檢查」、「不適用的方式及原因」）、第 8 節（假設、未決與風險）；`docs/workflow/PROJECT.md`（「必須通過的最終檢查」與「確認與授權」）；`docs/workflow/tasks/TASK-037.md`；`docs/architecture/ENGINEERING-REPORT.md` 第 8.1／8.2 節與附錄 C；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-065「執行最終整合驗收」 | `DELIVERY.md` §1（三次 pytest ＋ `node --test` ＋ `validate_workflow.py` ＋ 契約檢查的 exit code 與輸出）、`tdd/TASK-037.md` 的 Cycle 1 | 符合 | A-1 |
| AC-065「全套 pytest 與 `node --test` exit 0」 | 三次 `.venv/bin/python -m pytest -q` → `1007 passed`；`node --test` → `82 passed / 0 failed` | 符合 | A-1、A-4 |
| AC-065「每項 active AC 都有實作與驗證證據」 | `DELIVERY.md` §2 的 66 列對照表；`/tmp/check_delivery.py` 檢查「66 列、每項 AC 恰一次、所有證據與實作路徑存在」exit 0 | 符合 | A-2 |
| AC-065「DELIVERY 列出已完成、未驗證與已知限制」 | `DELIVERY.md` §2（已完成：66 列結果欄）、§3（未驗證清單）、§4（已知限制）、§5（未執行或失敗的檢查） | 符合 | A-3、A-5 |

逐條核對（AC-065）：

- **同一份檔案快照上實際執行**：三個命令都在 `ocaievo/` 檔案樹 sha256 `ca155909…`（122 檔）上執行，且本張未修改任何產品檔案，因此驗收後雜湊不變——「驗收的就是交付的版本」是可驗證的。
- **如實記錄 exit code 與輸出摘要**：§1 逐一列出命令、工作目錄、exit code、輸出摘要與日期；三次全套刻意都跑（用於複核 TASK-036 的間歇性測試）。
- **66 項 AC 的對照表**：每列都有 AC ID、負責 Task、實作位置（產品檔案）、驗證證據（預期檢查＋實際測試檔）、結果、證據路徑；人工檢查未執行的 AC 在結果欄以「；…未執行」明示，並在 §3／§5 說明原因與解除條件。
- **已完成／未驗證／已知限制三份清單都有**：§2 的結果欄、§3 的 11 項未驗證、§4 的 10 項已知限制（客戶端授權只能防君子、統計未處理片段相關性、預設規格偏保守、除權息還原依 TWSE 欄位，以及四項本專案額外誠實記錄的限制）。
- **未執行或失敗的檢查逐項標示**：§5 列出 4 項未執行（外部驗收）與 5 項歷史失敗（含修正內容與複核方式）；**沒有任何整體性的「全部通過」宣告**。
- **狀態同步**：37 張 Task 全部 `done`，`TASKS.md`／`STATE.md` 與單張 Task 檔一致，兩個流程驗證器 exit 0。符合。

## 品質 Review

- **對照表是產生出來的，不是手寫的**：`/tmp/gen_ac_rows.py` 由 `TASKS.md` 的 AC 覆蓋表與各張 TDD 的交付檔案表產生 66 列；前 10 張（TASK-001～010）沒有交付檔案表，其「實作位置」以各張 Task 檔的模組介面與 SPEC 第 5 節模組表**逐項人工對照**補上並在產生器中明列。這讓「66 列、每項恰一次」可以機器檢查，而不是靠人眼。
- **完整性檢查先失敗再通過（真實的 Red → Green）**：第一次執行時 AC-065 的證據路徑與 TASK-037 的狀態尚未就位，腳本以 4 個問題 exit 1；補齊後 exit 0。檢查腳本本身也驗證「負責 Task 是 done 且具備 `test_evidence`／`review_evidence`」，這一點讓「Task 標 done」與「對照表有證據」互相牽制。
- **驗收的證據是命令輸出而不是宣告**：§1 的每一列都有可重跑的命令與 exit code；三次全套的輸出讓「間歇性測試是否真的修好」有可觀察的答案（三次皆 1007 passed，時間也正常）。
- **未驗證項的分類與來源一致**：§3 與 SPEC 第 2 節 out of scope、`PROJECT.md` 的未授權／未驗證邊界逐項對齊；沒有把「未授權做的事」寫成「做不到」，也沒有把「沒做的事」寫成「已驗證」。
- **已知限制區分了「設計取捨」與「缺陷」**：§4 的每一項都指向出處（報告節次、ADR、TASK 的 A 編號），讀者可以追到決策理由；例如「客戶端授權只能防君子」直接對應報告第 6.4 節的誠實邊界表。
- **對外動作的聲明可稽核**：§8 逐項聲明未執行 `git`／部署／發布／發布版本／連線真實服務；本專案未初始化 Git（版本識別一律用 sha256），`wrangler.toml` 只有佔位值。
- **交付範圍與重跑方式**：§6 列出檔案樹、模組與測試數量、外部依賴與三個重跑指令，讓接手者不需要讀完整份文件就能重跑驗收。
- **本張沒有偷改產品程式碼**：唯一的檔案變更是四份文件；`ocaievo/` 的 sha256 與 TASK-036 驗收時相同，因此各張 Task 的證據仍然有效。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 驗收的可重現性 | advisory | §1 的完整原始輸出（pytest 的 2 個 warning 內容、node 的逐檔統計）沒有全文貼進 DELIVERY，只留摘要與 exit code | 需要完整輸出時可由任何人重跑同一命令（§6 給了指令）；若要存證，可把輸出存進 `docs/workflow/evidence/`（會讓交付樹變大，因此目前只留摘要） | 已記錄（`tdd/TASK-037.md` 的 Cycle 1 有逐次輸出摘要） |
| A-2 | 對照表的「驗證證據」粒度 | advisory | 每列引用的是「該 Task 的測試檔」而不是**逐一案例名**；66 列若逐案名列會膨脹數倍且難以維護 | 需要追到案例時，各張 TDD 的 Cycle 表已列出案例名與命令；本表以檔案為粒度並明示這是刻意的 | 已記錄（`DELIVERY.md` §2 的欄位說明） |
| A-3 | 人工檢查仍未執行 | advisory（**未執行**） | SPEC 第 7 節的四項人工／視覺檢查（K 線標註、Chrome 互動、Linux 桌面通知、除權息前後差異）在非互動式環境無法執行；對應 AC（034／042～050／051／066）因此在結果欄標示「…未執行」 | 交付後由使用者在 Chrome（Wayland）與 Linux 桌面逐項完成；替代驗證已記於各張 TDD | 待辦（`DELIVERY.md` §3／§5） |
| A-4 | 間歇性測試的長期觀察 | advisory | 三次全套連續通過，但根因未完全確定（疑似高負載下的執行緒排程）；長期（CI 或不同機器）仍可能再現 | 若在 CI 再現，以 `faulthandler`／`threading.enumerate()` 快照定位；目前的 join 寫法已比輪詢穩健 | 已記錄（`DELIVERY.md` §5 歷史失敗 4） |
| A-5 | 對照表的「結果」欄語意 | advisory | 「通過（自動）」代表有可重跑的自動證據，但不等於「使用者在真實環境試過」；這個區別靠 §3／§5 補足，欄位本身沒有更細的分級 | 若要把「自動／人工／未驗證」變成機器可讀，可在表格加一欄狀態碼（新需求） | 已記錄（`DELIVERY.md` §2 的欄位說明） |
| A-6 | 跨 Task 測試變更的歷史 | advisory | 四處跨 Task 的測試變更使該檔的 sha256 與各張 Task 的 `checked_version` 不同；本張以「現行檔案樹」重跑為準並在 §7 列表說明 | 若日後要嚴格的「每個 Task 的證據都對應它當時的雜湊」，需要在每次變更時重跑該 Task 的矩陣（成本高）；目前的處置是明示差異與複核方式 | 已記錄（`DELIVERY.md` §7） |
| A-7 | 交付報告的最終讀者驗收 | advisory | `DELIVERY.md` 是否對使用者有用，只能由使用者閱讀後回饋；本張只能證明每一列都指向存在的證據、且未驗證項都被標示 | 由使用者閱讀後提出補充需求 | 待辦（本張 TDD 的「未執行或受阻」第 3 點） |

## 修正與重審

- 第 1 輪 Spec Review：AC-065 的四項宣稱逐條符合（同一份快照、exit code 與輸出、66 項對照表、三份清單＋未執行項揭露）。
- 第 1 輪品質 Review 修正 1 處：完整性檢查第一次失敗（AC-065 的證據路徑與 TASK-037 狀態尚未就位），補齊 TDD／Review 與狀態後通過；檢查腳本也調整為只驗產品路徑（文件路徑不屬於 `ocaievo/`）。
- 重審：重跑完整性檢查（exit 0）、三次全套（`1007 passed` ×3）、`node --test`（82 passed）、兩個流程驗證器（exit 0），並確認 `ocaievo/` 檔案樹 sha256 未變（本張只動文件）。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-065 逐條符合）
- 品質 Review：passed（無 blocking；A-1／A-2／A-5／A-6 為已記錄的取捨，A-3／A-7 待人工／讀者驗收，A-4 為長期觀察）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（完整輸出可由任何人重跑；存證會膨脹交付樹）、A-2（以檔案為粒度並明示）、A-3（需互動式環境與實機）、A-4（需 CI 或不同機器再現）、A-5（欄位分級屬新需求）、A-6（跨 Task 變更已明示差異）、A-7（需使用者回饋）
- 能否標為 done：**可以**
- 限制與未驗證事項：SPEC 第 7 節的四項人工／視覺檢查未執行；真實 Cloudflare 後端與部署未驗證；CLI → 真實授權服務的端到端未驗證；長期執行穩定性未量測；`DELIVERY.md` 的實用性待使用者回饋
