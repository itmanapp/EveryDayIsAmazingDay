# 流程文件驗證

`validate_workflow.py` 是唯讀的文件一致性檢查器，使用 Python 3.10+ 標準庫。它檢查固定 Markdown 欄位、ID、相依關係、AC 歸屬及本機證據引用；不執行產品測試、不判斷任意敘述、不核發實作授權，也不是流程引擎。

## 執行方式

從工具包執行，目標根目錄可含空白：

```bash
python3 scripts/validate_workflow.py "/path/to/project"
```

初始化後，整份 skill 可獨立複製使用，無須原工具包或第三方套件：

```bash
python3 "/path/to/project/.project-workflow/scripts/validate_workflow.py" "/path/to/project"
```

預設讀目標根目錄的 `docs/workflow/`。檢查工具包中的規劃示例：

```bash
python3 scripts/validate_workflow.py . --workflow-dir examples/notes-cli
```

位置參數一律是專案根目錄；`--workflow-dir` 與所有證據路徑相對於它，不受目前 shell 工作目錄影響。成功 exit 0；文件或一致性錯誤 exit 1；命令列參數錯誤 exit 2。檢查器只輸出診斷，不修改文件。

## 有限 Markdown 契約

固定欄位使用獨立、未縮排的清單行，例如 `- status：draft` 或 `- status: draft`。值不包反引號，不在同一行附加說明；說明另起一段。已知欄位在同一文件中重複宣告會報錯，即使值相同也不接受。fenced code block 內的示例不算宣告；其他正文不做語意解析。

| 文件 | 必填穩定欄位 |
| --- | --- |
| SPEC.md | `Spec ID`、`版本`、`狀態` |
| STATE.md | `目前階段` |
| tasks/*.md | `id`、`status`、`spec_version`、`ac_ids`、`depends_on`、`test_evidence`、`review_evidence` |
| 被 test_evidence 引用的紀錄 | `task_id`、`verification`、`result`、`checked_version`；alternative 時另需 `alternative_reason` |
| 被 review_evidence 引用的紀錄 | `task_id`、`spec_result`、`quality_result`、`blocking_count`、`checked_version` |

Task ID 使用 `TASK-001`、AC ID 使用 `AC-001`、Spec ID 使用 `SPEC-001` 形式，數字至少三位。`spec_version` 以 `SPEC-001 v0.1` 形式對應 Spec ID 與版本。其他說明欄位可保留，檢查器不驗證其內容。

`ac_ids`、`depends_on`、`test_evidence`、`review_evidence` 使用 JSON 字串清單，空清單寫 `[]`，不接受未加引號的 `[AC-001]`、重複值或附加註解。例如：

```markdown
- id：TASK-001
- status：draft
- spec_version：SPEC-001 v0.1
- ac_ids：["AC-001"]
- depends_on：[]
- test_evidence：[]
- review_evidence：[]
```

新增 Task 時將 [TASK 範本](../assets/templates/TASK.md) 的 `TASK-NNN` 換成正式 ID；範本自身不是可執行任務。Task 狀態使用 [workflow 的狀態表](workflow.md) 定義的七種值。

## 唯一資料來源與閘門

SPEC 恰有一張第一欄為 `AC ID` 或 `AC` 的驗收表格，其中唯一的 `status` 欄記 `active` 或 `retired`。它是 AC 清單的權威，不另外維護 machine-readable AC 陣列。表格使用一般 Markdown 分隔列；儲存格內的直線字元寫 `\|`。ID 不得重複，移除的 AC 保留為 retired。

單張 Task 文件是狀態及 `ac_ids`、`depends_on` 的權威。檢查器不從 TASKS 的索引或 STATE 的統計文字推導狀態，不自動同步摘要。索引可供人閱讀，但變更後仍需核對更新。

- 所有階段：Task ID 唯一；AC 和相依 Task 的引用存在；相依沒有自循環或多張循環。
- `discover`、`spec`、`tasks`：draft 可有空 AC 表及尚未建立的 tasks 目錄，通過只表示草稿結構有效。
- `ready`、`implement`、`verify`、`complete`：Spec 狀態必須是 ready；至少一項 active AC 與一張未取消 Task；每項 active AC 由至少一張未取消 Task 承接；未取消 Task 的 spec_version 對應目前 Spec。
- `ready` 階段不可留有 draft Task；`ready` Task 可等待尚未 done 的有效依賴；`in_progress`、`in_review`、`done` Task 的全部依賴必須已 done。
- cancelled Task 保留 ID、相依與歷史 AC。它不計入完成要求，也不承接 active AC 的有效歸屬；任何未取消 Task 都不可繼續依賴它。先修正相依及 AC 歸屬才能通過。
- `verify`、`complete`：所有未取消 Task 必須 done。只要仍有 draft、ready、in_progress、in_review 或 blocked Task，即使 STATE 統計說已完成仍失敗。

檢查器不靠單次快照推斷歷史狀態轉移，也不保證規格內容足以實作。[ready 的需求、測試邊界與授權條件](workflow.md) 仍由實際工作及紀錄判斷。

## 本機證據

Task 的證據欄位指向已存在的紀錄，例如：

```markdown
- test_evidence：["docs/workflow/tdd/TASK-001.md"]
- review_evidence：["docs/workflow/reviews/TASK-001.md"]
```

每個已填引用都必須能讀取為非空 UTF-8 一般檔案，且包含對應 `task_id`、穩定欄位和紀錄本文。只有標題與通過宣告不算本文。引用只允許專案根內的相對路徑，拒絕 URL、絕對路徑、`..`、Windows 反斜線及經 symlink 越出專案的路徑。報告本文中的其他連結不由此檢查器遞迴驗證。

當 Task 是 done 時，兩種清單均不得空白，並檢查所有引用紀錄：

- 測試紀錄 `result` 是 passed；`verification` 使用 tdd、existing（既有覆蓋）或 alternative（替代驗證）。alternative 需寫具體 `alternative_reason`，不必捏造 Red。
- Review 的 `spec_result`、`quality_result` 均為 passed，`blocking_count` 為 0。
- 所有測試與 Review 的 `checked_version` 非空白／待填／未執行，且字串完全相同，指向本張最後驗證的 SHA 或檔案快照。

未完成紀錄可用 `not_run`、`failed`，Review 尚未檢查的 blocking_count 用 `unknown`；它們不能支持 done。範本預設均為未執行。完成時讓 Task 的引用清單指向目前有效紀錄，歷史失敗及舊版本結果留在紀錄本文或另存文件。

這些條件只驗證**宣告及引用的一致性**。能填 `passed` 不表示真的執行過測試；相同 checked_version 不證明當前檔案未變，也不會自動校驗 SHA 或內容雜湊。實際命令、工作目錄、exit code、輸出、Red 原因、測試涵蓋、Review 範圍與發現，仍需依 [TDD](tdd.md) 及 [Review](review.md) 閱讀並查證。檢查成功亦不等於已完成整合測試或最終交付驗收。

## 維護者驗證

工具包的 `tests/fixtures/workflow/` 保存 draft、done 加 cancelled 的有效結構，以及 `negative-cases.json` 的語意錯誤變更。所有內容明確為合成測試資料，不能當成任何產品的執行證據。測試經公開 CLI 驗證重複 ID、缺漏／循環引用、AC 歸屬、缺失／空白／未通過證據、取消依賴、未完成交付及專案路徑限制，也檢查 bootstrap 草稿與 notes-cli 示例。

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_links.py
```
