# 本專案的 AI 工作流程

讀取本專案適用的既有規則，再讀 `.project-workflow/SKILL.md`，按階段載入 references。工作文件在 `docs/workflow/`；範本在 `.project-workflow/assets/templates/`。以下路徑均相對於專案根目錄。

## 本次工作的方式

狀態：待盤點。這是初始化骨架；由 AI 在盤點與需求釐清後依 `.project-workflow/references/discovery.md` 更新，並與 Spec／Task 一起交付。

- 本次目標與範圍：待釐清，詳細需求見 `docs/workflow/BRIEF.md`。
- 適用階段、各階段產物與通過條件：待盤點後填入本專案的摘要；完整規則見 `.project-workflow/references/workflow.md`。
- 本次交付停點：依使用者指示記錄；初始化本身不構成產品實作授權。
- 適用的測試／審查／人工驗收方式及理由：待決策，詳細邊界見 `docs/workflow/SPEC.md`。

## 詳細資料與接續

- 環境、真實執行指令、自行決策範圍及使用者授權：`docs/workflow/PROJECT.md`。
- 規格與測試策略：`docs/workflow/SPEC.md`；任務及 AC 對照：`docs/workflow/TASKS.md`。
- 進度與下一步：`docs/workflow/STATE.md`。續作先核對磁碟、Git 與現有測試／Review 證據，再接手當前 Task。
- 文件一致性檢查：`.project-workflow/references/validation.md`；結構通過不代表產品測試已通過。

摘要只記錄本專案的工作方式與上述文件的導覽。命令、授權及進度保留在各自的權威文件，不在此重複維護。範本的待填欄位不是已確認需求或測試證據。
