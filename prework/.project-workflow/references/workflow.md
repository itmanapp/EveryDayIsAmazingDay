# 流程、狀態與續作

## 檔案契約

所有路徑相對於**目標專案**：

| 檔案 | 唯一負責內容 |
| --- | --- |
| `docs/workflow/PROJECT.md` | 執行環境、指令、工作根目錄、確認／授權紀錄、工具包版本 |
| `docs/workflow/BRIEF.md` | 問題、問答、假設、待決事項 |
| `docs/workflow/CONTEXT.md` | 領域詞彙；已有 glossary 時改記它的路徑 |
| `docs/workflow/SPEC.md` | 版本化需求與驗收條件 AC，產品行為的依據 |
| `docs/workflow/TASKS.md` | 每張 Task 的索引與相依圖；AC 到 Task 的對照 |
| `docs/workflow/tasks/TASK-001.md` | 單張 Task 的範圍、依賴、狀態與執行條件 |
| `docs/workflow/tdd/TASK-001.md` | 實際 Red／Green／回歸驗證證據 |
| `docs/workflow/reviews/TASK-001.md` | 該次差異範圍、Spec 與品質審查、修正結果 |
| `docs/workflow/adr/ADR-001.md` | 有實質取捨、日後需理解原因的重大決策 |
| `docs/workflow/STATE.md` | 當前位置、最後驗證版本與接續動作 |
| `docs/workflow/DELIVERY.md` | 最終驗收對照、使用方式、驗證結果、剩餘風險 |

單張 Task 檔是任務狀態的權威來源，TASKS 是索引，STATE 是續作摘要。三者不一致時，以程式與證據查證，更新文件；不得直接選擇看起來最接近完成的狀態。Task ID 不重用，取消工作也保留紀錄。

## 階段閘門

1. **discover**：讀既有專案與限制；記錄確定事實與未決事項。
2. **spec**：寫出能驗收的 Spec。阻塞產品行為的未知未解決時只能是 draft。
3. **tasks**：每項範圍內 AC 都有 Task 或明確驗證任務；相依無循環。
4. **ready**：Spec 版本、Task 清單、測試公開邊界已定案，且實作授權明確。將使用者原意、日期、適用範圍記入 PROJECT。可一次確認全部文件，不要求重複確認每個階段。
5. **implement**：重複執行下一節的任務迴圈。
6. **verify**：全體 Task 完成後做整合測試與 AC 對照。
7. **complete**：交付條件全部滿足；保存 DELIVERY 與 STATE。

使用者已明確表示「由你在這些限制內決定並做完」時，記錄授權，採合理選擇並公開假設。沉默或時間經過不構成確認。涉及核心行為、資料不可逆變動或範圍擴張且超出已有授權時，先保存具體提案再詢問；其他獨立工作可繼續。

外部發布、push、開 Issue、合併及部署各自依使用者授權處理；本流程不自帶這些授權。已授權的動作不再重複詢問。

## 自動任務迴圈

```text
讀 PROJECT 的授權、命令與限制，讀當前 Spec 版本
續作時先接手仍在 in_progress／in_review 的 Task；否則選 status=ready 且所有 depends_on 都是 done 的 Task
若沒有可選任務：依下方「沒有可領取任務時」判定下一步
首次領取 ready：記錄開工基準與既有修改，Task → in_progress
接續 in_progress／in_review：沿用原開工基準，從已保存的測試／審查位置恢復，不重設基準
對每個驗收行為：寫一個測試 → 執行並確認真正的 Red → 最小實作 → Green
跑本 Task 相關回歸／靜態檢查，Task → in_review
分別完成 Spec 與品質 Review
若有阻擋問題：補測試、修正、重跑受影響檢查，再 Review
阻擋問題歸零且所有證據有效：Task → done，更新 TASKS 和 STATE
依已有授權繼續下一張，不要求使用者逐張輸入「繼續」
```

### 沒有可領取任務時

先核對規劃與實際 Task，不以空清單推論完成：

1. 仍有 draft：補齊該任務缺少的規劃／決策；只要求規劃時，交付草稿並保存待決事項。
2. 仍有 blocked，或 ready 的相依未完成：指出阻塞原因；沒有可做的獨立工作時保存 STATE，不能直接進入驗收。
3. 規劃已定案，至少有一項 active AC 與一張有效 Task，所有**未取消且屬於目前範圍**的 Task 都是 done，active AC 的驗收責任完整，且無未解決阻塞，才進入 verify。

`cancelled` 不需要轉成 done，也不算尚未完成的有效任務。取消前把該 AC 標為 retired，或重新分配給其他有效 Task，並修正有效任務的相依；保留歷史紀錄。取消任務不會滿足任何 `depends_on`。若本版全部取消，記錄「本次範圍已取消」並交付狀態說明，不能宣稱產品 complete。

在規劃交付、進入 ready、Task 標為 done 及最終交付前，依 [validation.md](validation.md) 執行文件一致性檢查。結構檢查通過後，仍須人工核對需求與實際測試／Review 證據。

## Task 狀態

| 狀態 | 意義 | 可轉移至 |
| --- | --- | --- |
| draft | 範圍、驗收或決策仍缺漏 | ready、cancelled |
| ready | 可執行定義已完整；相依尚未完成時仍不可領取 | in_progress、blocked、draft、cancelled |
| in_progress | 正在實作或修正 | in_review、blocked、draft |
| in_review | 實作與測試可審查 | done、in_progress、blocked、draft |
| blocked | 缺少決策、環境、權限或外部依賴 | 回到紀錄的 blocked_from，或 draft、cancelled |
| done | AC、測試、Review 與文件都通過 | 需求變更時回到 draft，回歸時回到 in_progress |
| cancelled | 已明確移出範圍，保留理由 | 有新工作建立新 ID |

取消某個 Task 不會自動解鎖依賴它的 Task。先修正依賴關係和 AC 歸屬，再選下一張。blocked 保存原因、恢復所需條件及 blocked_from。

同一根因連續三次修正仍無進展時，停止盲目重試，保留重現步驟和假說，標記該 Task blocked，繼續其他可做工作或回報。這是預設停止條件，可依使用者已定義的預算調整。

## 跨對話接續

每張 Task 結束、阻塞、範圍變更或工作階段結束時更新 STATE。新 AI 讀取後：

1. 核對 Git branch、HEAD、未提交與未追蹤檔案；沒有 Git 就比對檔案快照。
2. 讀最新 Spec、Task、TDD 及 Review，確認完成證據對應目前程式版本。
3. 上次停在 Red 就先重現該失敗；停在 Review 就接續問題清單。已有修改不可再盲目重新產生。
4. 只重跑足以確定目前狀態的檢查。若檔案與已驗證版本完全一致，不必為續作重新跑所有昂貴測試。
5. 沿用既有範圍和授權。STATE 不取代實際程式與測試結果。

## 需求變更

變更前先列影響：哪些 AC、介面、資料、Task、測試失效，是否超出授權。更新 SPEC 版本，記錄理由。原 ID 在語意不變時沿用，新行為使用新 AC ID；移除條件標為 retired，不能悄悄刪除追溯。

受影響的 done Task 回到 draft（需求未定）或 in_progress（已授權回歸修正）；清除過期通過結論，保留歷史證據。更新 AC → Task 對照與相依。重新達到 ready 閘門後才實作變更。

## 交付條件

- 所有範圍內 AC 有實作與驗證證據，相關 Task 為 done。
- 在最終版本執行 PROJECT 所列必須的全套測試、build、lint、型別檢查；不適用者有理由，未執行者不能冒充通過。
- 若有多張 Task 的互動，驗證整合情境；僅有單元測試不足以宣稱端到端通過。
- 最終程式的 Spec／品質 Review 無未處理阻擋問題；非阻擋建議列入 DELIVERY。
- 有安裝、啟動、使用／操作說明；若有資料遷移則附遷移與復原策略。
- DELIVERY 指出已完成與未驗證項。必要測試受阻時標示「交付受阻／部分完成」，STATE 不得標 complete。
