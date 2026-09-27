# TASK-037 測試紀錄（整合驗收）

- task_id：TASK-037
- verification：alternative
- result：passed
- alternative_reason：本張是 `docs` 型任務，主要產物是驗收與對照文件；「文件內容是否忠實」無法用單元測試證明。因此以**可重跑命令的 exit code 與輸出**、**證據路徑存在性**、**66 項 active AC 的覆蓋計數**，以及**本報告是否逐項標示未驗證／失敗**作為替代驗證；本張不新增測試檔、不修改產品程式碼。
- checked_version：snap-2026-09-24-ocaievo-cli-serve-license sha256:ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab
- Task／Spec 版本：TASK-037 / SPEC-001 v0.4
- 測試邊界：三個既有命令（`.venv/bin/python -m pytest -q`、`cloudflare/` 下的 `node --test`、`python3 .project-workflow/scripts/validate_workflow.py .`）＋自訂的唯讀契約檢查（`/tmp/check_tasks.py`）＋本張新增的**對照表完整性檢查**（`/tmp/check_delivery.py`）。全程唯讀，未部署、未執行 `git`、未連任何真實外部服務。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-036 的交付物，Python 全套 **1007 passed**、Node **82 passed**（本張不修改產品程式碼，驗收後數字相同）；開工前檔案樹 sha256 `ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab`（122 個檔案，即 TASK-036 的 `checked_version`）。

工作目錄：`ocaievo/`（pytest、node）與專案根（流程驗證器、契約檢查）。

## 交付檔案

| 檔案 | 說明 |
| --- | --- |
| `docs/workflow/DELIVERY.md` | 新增：交付報告（驗收結果、66 項 AC 對照表、未驗證清單、已知限制、未執行或失敗的檢查、跨 Task 測試變更的複核、授權與對外動作聲明） |
| `docs/workflow/TASKS.md` | 修改：TASK-037 標為 done、交付狀態改為「37 張全部 done」、AC 覆蓋表的「最終整合驗證負責 Task」已如實對應 |
| `docs/workflow/STATE.md` | 修改：階段改為 `complete`、統計 done 37、加入 TASK-037 的驗收摘要與待決事項的處置 |
| `docs/workflow/tdd/TASK-037.md`／`docs/workflow/reviews/TASK-037.md` | 新增：本張的證據與兩軸 Review |

## Cycle 1：三個命令的實際輸出（3 個測試函式等價的檢查）

| 階段 | 命令（工作目錄） | exit | 關鍵輸出 | 日期 |
| --- | --- | --- | --- | --- |
| 驗收 1 | `.venv/bin/python -m pytest -q`（`ocaievo/`）第 1 次 | 0 | `1007 passed, 2 warnings in 180.18s` | 2026-09-25 |
| 驗收 2 | 同上，第 2 次 | 0 | `1007 passed, 2 warnings in 179.18s` | 2026-09-25 |
| 驗收 3 | 同上，第 3 次 | 0 | `1007 passed, 2 warnings in 180.45s` | 2026-09-25 |
| 驗收 4 | `node --test`（`ocaievo/cloudflare/`） | 0 | `ℹ tests 82 / pass 82 / fail 0` | 2026-09-25 |
| 驗收 5 | `python3 .project-workflow/scripts/validate_workflow.py .`（專案根） | 0 | 「通過：流程文件結構與宣告一致」 | 2026-09-25 |
| 驗收 6 | `python3 /tmp/check_tasks.py`（專案根） | 0 | 「檢查 37 個 Task 檔；SPEC AC 66 項；索引 37 張；結果：通過」 | 2026-09-25 |

- **三次全套是刻意的**：TASK-036 期間有一個背景執行緒測試在整套測試下間歇性失敗（約 5 次出現 2 次），修正後連續三次全套皆通過；這是「間歇性問題已不再重現」的直接證據（三次都在 180 秒左右完成，時間也沒有異常膨脹）。
- 兩個 warning 來自 pandas 的棄用提示，與本專案程式碼無關；沒有把 warning 當成通過的理由。

## Cycle 2：對照表完整性（唯讀腳本 `/tmp/check_delivery.py`）

- 檢查內容：（1）`DELIVERY.md` 的 AC 對照表恰 **66 列**；（2）AC-001～AC-066 各**恰出現一次**（0 缺漏、0 重複）；（3）每一列的負責 Task 檔存在、狀態為 `done`、且 `test_evidence`／`review_evidence` 非空；（4）每一列提到的**證據路徑**（`docs/workflow/tdd/TASK-0NN.md`、`reviews/TASK-0NN.md`）存在；（5）每一列提到的**產品路徑**（`ediaad/`、`tests/`、`scripts/`、`cloudflare/`）都存在於 `ocaievo/`。
- 第一次執行（TASK-037 自己的紀錄尚未建立時）如實失敗：

```
AC 列數：66（應為 66）
AC ID：66 項不重複（應為 66）
發現問題：
 - AC-065 的證據路徑不存在：docs/workflow/tdd/TASK-037.md
 - AC-065 的證據路徑不存在：docs/workflow/reviews/TASK-037.md
 - AC-065 的 TASK-037 不是 done
 - AC-065 的 TASK-037 缺少證據欄位
check exit=1
```

- 建立本張的 TDD／Review 並把 TASK-037 標為 done 之後重跑：

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Red | `python3 /tmp/check_delivery.py` | 1 | 上列 4 個問題（TASK-037 的紀錄與狀態尚未就位） |
| Green | `python3 /tmp/check_delivery.py` | 0 | `AC 列數：66（應為 66）`／`AC ID：66 項不重複（應為 66）`／`結果：通過（66 列、每項 AC 恰一次、所有證據與實作路徑存在）` |

- **這是一個真實的 Red → Green**：檢查先失敗（缺證據），補齊後通過；不是「先有結論再寫檢查」。

## Cycle 3：狀態一致性（各張 Task 檔為權威）

- 以 `grep -L "^- status：done" docs/workflow/tasks/*.md` 確認沒有未完成的 Task：實作前為 `TASK-037.md`，實作後為**空集合**。
- 以 `grep -c "^- status：done"` 確認 **37 張全部 done**。
- 各張 Task 的 `test_evidence`／`review_evidence` 與 `TASKS.md`／`STATE.md` 的摘要逐項比對：**37/37 一致**（`TASKS.md` 的狀態欄與單張檔一致；`STATE.md` 的統計為 done 37、ready 0）。
- `validate_workflow.py` 與 `/tmp/check_tasks.py` 的 exit 0 是這條一致性的機器證據（前者檢查文件結構與宣告、後者檢查 37 張 Task 的欄位／AC 引用／相依圖／證據路徑）。

## Cycle 4：未驗證與失敗項的揭露（人工複核）

- 逐項核對 `DELIVERY.md` 的 §3 未驗證清單與 SPEC 第 2 節 out of scope、`PROJECT.md` 的「已知的未授權／未驗證邊界」：**一致**（Cloudflare 帳號／D1／網域與部署、macOS／Windows 通知、Twelve Data 真實金鑰與額度、自動下載安裝、跨瀏覽器視覺回歸、真實授權服務端到端、SPEC 第 7 節的四項人工檢查、長期執行穩定性、Windows 訊號語意）。
- 逐項核對 §5「未執行或失敗的檢查」：4 項未執行（三命令以外的外部驗收）與 5 項歷史失敗**全部如實標示**（已修正者寫明修正內容與複核方式，未執行者寫明原因與解除條件）。
- 確認沒有把未執行的檢查寫成通過：`DELIVERY.md` 內「未驗證」「未執行」的出現位置與 §3／§5 對應；`§1` 只陳述三個命令的實際輸出；**沒有任何整體性的「全部通過」宣告**。
- 確認未執行任何部署或 git 指令：本次驗收只跑 pytest／node／兩個驗證器與唯讀檢查腳本。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `python3 /tmp/check_delivery.py` | 0 | 66 列、每項 AC 恰一次、所有證據與實作路徑存在 |
| `.venv/bin/python -m pytest -q`（三次） | 0 | `1007 passed` ×3 |
| `node --test`（`ocaievo/cloudflare/`） | 0 | `ℹ tests 82 / pass 82 / fail 0` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 通過 |
| 檔案樹（`ocaievo/`，未修改） | — | sha256 `ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab`（122 個檔案） |

## 如實記載

1. **對照表是**產生**的，不是手寫的**：`/tmp/gen_ac_rows.py` 由 `TASKS.md` 的 AC 覆蓋表（負責 Task 與預期檢查）與各張 TDD 的交付檔案表產生 66 列；前 10 張（TASK-001～010）的 TDD 沒有交付檔案表，其「實作位置」由各張 Task 檔的模組介面與 SPEC 第 5 節模組表**逐項人工對照**補上（產生器內以 `EXTRA` 明列，可被檢查腳本驗證路徑存在）。
2. **第一次執行完整性檢查失敗**（缺 TASK-037 自己的證據與狀態），如實記為 Red；補齊後 Green。這正是該檢查存在的目的。
3. **TASK-036 的間歇性測試**：修正後三次全套連續通過；本報告仍把它列在 §5（歷史失敗 4）與 `STATE.md` 的待決事項，標示「已修正並複核」，而不是從紀錄中移除。
4. **沒有動產品程式碼**：本張唯一的檔案變更是四份文件（`DELIVERY.md`、`TASKS.md`、`STATE.md`、本張 TDD／Review）；`ocaievo/` 的檔案樹 sha256 與 TASK-036 驗收時相同。

## 未執行或受阻（本張自身）

1. **SPEC 第 7 節的人工／視覺檢查**：本環境沒有瀏覽器自動化、沒有 macOS／Windows 實機、且為非互動式，四項人工檢查皆未執行（已列於 `DELIVERY.md` §3／§5）。
2. **真實 Cloudflare 後端**：無帳號／網域且部署未授權，端到端驗收未執行（同上）。
3. **交付報告的最終讀者驗收**：`DELIVERY.md` 是否對使用者有用，只能由使用者閱讀後回饋；本張只能證明它的**每一列都指向存在的證據**、且未驗證項都被標示。
