---
name: project-workflow
description: 引導新專案或完整功能從需求訪談、Spec 與 Task 規劃，到逐張 TDD 實作、Code Review 及交付；也能依已保存狀態續作。適用於使用者要求採用此完整開發流程時。
---

# Project Workflow

把使用者的想法轉成可驗證、可續作的專案交付。以繁體中文溝通，沿用專案領域詞彙。使用者指定語言、範圍和既有授權優先。

## 入口與資料位置

此檔案所在位置是工具包根 `KIT`；安裝到目標專案時通常是 `.project-workflow/`。工作文件位於目標專案 `docs/workflow/`，不可混寫回 KIT 的範本。

先讀目標專案適用的規則、`PROJECT_WORKFLOW.md`，以及已有的 PROJECT、STATE、SPEC、TASKS；載入當前 Task 與它的測試、review 紀錄。依磁碟、Git 及實測結果校正狀態，再決定階段。

先讀 [流程與狀態](references/workflow.md)。其他文件按需讀取：

| 工作 | 必讀 | 使用的範本（位於 assets/templates） |
| --- | --- | --- |
| 盤點與需求釐清 | [discovery.md](references/discovery.md) | [PROJECT](assets/templates/PROJECT.md)、[BRIEF](assets/templates/BRIEF.md)、[CONTEXT](assets/templates/CONTEXT.md) |
| 規格 | [spec-and-tasks.md](references/spec-and-tasks.md) | [SPEC](assets/templates/SPEC.md)、需要時 [ADR](assets/templates/ADR.md) |
| 任務拆解 | [spec-and-tasks.md](references/spec-and-tasks.md) | [TASKS](assets/templates/TASKS.md)、每張 [TASK](assets/templates/TASK.md) |
| 實作與測試 | [tdd.md](references/tdd.md) | 每張 [TDD](assets/templates/TDD.md) |
| 程式審查 | [review.md](references/review.md) | 每張 [REVIEW](assets/templates/REVIEW.md) |
| 接續、變更及交付 | [workflow.md](references/workflow.md) | [STATE](assets/templates/STATE.md)、[DELIVERY](assets/templates/DELIVERY.md) |
| 檢查工作文件 | [validation.md](references/validation.md) | 執行 `scripts/validate_workflow.py`；產品驗證仍依 PROJECT |

## 執行原則

- 能從程式或環境找到的事實先自行查證；影響產品的未決問題再問使用者。用可觀察行為釐清，不用名詞堆疊替代需求。
- 盤點與訪談後，把根目錄的 PROJECT_WORKFLOW 更新為本專案適用的流程摘要，詳細規則仍引用 references。Spec 與 Task 草稿完成後，將摘要、範圍、AC、測試公開邊界及任務清單一起呈現。已有範圍內的實作授權且達到 ready 就記錄並繼續；否則取得一次明確確認再實作。
- 自動化指的是 AI 在本次可執行工作階段中逐張推進；不是常駐服務或排程。工具不足、關鍵決策未定或持續失敗時，保存 STATE 並如實回報。
- 一張 Task 從可重現的 Red 到 Green，再做兩個角度的 Review。修正阻擋問題、驗證後才標為 done，接著選下一張可執行 Task。
- 不因文件填完就宣稱產品完成；不把無工具、未執行、跳過或失敗當作通過。
- 使用者只要求規劃或單一階段時，完成該範圍即可，不自行擴大到產品實作或對外操作。

來源與本版差異：[sources.md](references/sources.md)。
