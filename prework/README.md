# prework/ — 前置作業文件

本資料夾集中存放本專案**開始寫程式之前**的所有文件：需求訪談、Spec、Task 規劃、逐張 TDD 與 Review 紀錄、證據與交付報告，以及工作流程工具包。程式碼不在這裡，請見倉庫根目錄的 [`../ocaievo/`](../ocaievo/)。

## 內容

| 路徑 | 內容 |
| --- | --- |
| `AGENTS.md` | 進入點指示：開始工作前先讀 `PROJECT_WORKFLOW.md` |
| `PROJECT_WORKFLOW.md` | 本專案的工作流程規則（入口與既有規則） |
| `.project-workflow/` | 工作流程工具包（[skills-agent-spec](https://github.com/itmanapp/skills-agent-spec) 的 `project-workflow` v1.0）：規格、範本、參考文件與驗證腳本 |
| `docs/architecture/ENGINEERING-REPORT.md` | 需求與架構權威來源（前置輸入報告） |
| `docs/workflow/PROJECT.md` | 專案設定、執行指令、環境實測、版本標記慣例、授權紀錄 |
| `docs/workflow/BRIEF.md` | 需求釐清、問答與決策紀錄 |
| `docs/workflow/CONTEXT.md` | 領域詞彙與背景 |
| `docs/workflow/SPEC.md` | SPEC-001 v0.4：權威驗收條件（AC）表格 |
| `docs/workflow/TASKS.md` | 37 張 Task 的索引與相依順序 |
| `docs/workflow/STATE.md` | 完整工作狀態與逐階段紀錄 |
| `docs/workflow/DELIVERY.md` | **交付報告**：驗收證據、66 項 AC 對照表、未驗證項目與已知限制 |
| `docs/workflow/tasks/` | 37 張 Task 文件（`TASK-001`～`TASK-037`） |
| `docs/workflow/tdd/` | 每張 Task 的 TDD 紀錄（Red → Green） |
| `docs/workflow/reviews/` | 每張 Task 的雙軸 Review 紀錄（規格軸／品質軸） |
| `docs/workflow/evidence/` | 一次性實測存證（例如 TWSE 端點探測結果、實作前基準） |
| `docs/workflow/adr/` | 架構決策紀錄 |

## 路徑慣例（重要）

文件保留當初撰寫時的相對路徑寫法：

- `docs/workflow/…`、`.project-workflow/…` → 相對於**本資料夾**（`prework/`）。
- `ocaievo/…` → 相對於**倉庫根目錄**；Task／SPEC 內的實作位置（例如 `ediaad/scan.py`）指的是 `ocaievo/ediaad/scan.py`。

## 驗證

```bash
cd prework
python3 .project-workflow/scripts/validate_workflow.py .
# 通過：流程文件結構與宣告一致；不代表測試實跑、Review 品質或實作授權已獲證明。
```

專案文件中的 checked_version 記為 `<snap 標籤> sha256:<ocaievo 原始碼樹雜湊>`；本次交付的樹狀雜湊為
`ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab`（122 檔）。
