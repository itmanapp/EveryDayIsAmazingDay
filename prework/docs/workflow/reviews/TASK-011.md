# TASK-011 Code Review

- task_id：TASK-011
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-cli-match-monitor sha256:3ef139627e2fd953dc1b3b8e1db07b538ca531f193fb3fcea9308e8d7eeedbce
- Task／Spec 版本：TASK-011 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含變異檢查補測與 Cycle 4 的規格對齊）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `3ef139627e2fd953dc1b3b8e1db07b538ca531f193fb3fcea9308e8d7eeedbce`；本張交付的三個檔案——`ediaad/cli.py` `672ace72125daa14032f8c919eb756050da3e972d2cdeacbd876e0bb80b5398b`、`ediaad/__main__.py` `5a437844988985e3566c5105a75038c805ab9ec51d3904d7922e44f567396444`、`tests/test_cli_match_monitor.py` `f3e68536e6b95efa0e2be2f4c3ed0efb829e336a83e0a6d1e311890fb11db021`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對；本張新增 `ediaad/cli.py`、`ediaad/__main__.py`、`tests/test_cli_match_monitor.py`，未修改其他模組
- 納入的已提交、未提交、新增檔案：上述三個檔案＋本張 TDD／Review 紀錄＋`docs/workflow/PROJECT.md` 的版本標記慣例（新增章節）
- 排除的既有修改及理由：`monitor`／`outlook`／`patterns`／`scan` 等屬 TASK-002～010 交付物，本張只**呼叫**未修改（`ediaad/monitor.py` 雜湊 `72df2ba2…` 與 TASK-010 紀錄一致，已核對）
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-027～AC-029、第 5 節（`ediaad/cli.py` 責任與公開 API、原則 1「模組責任與依賴方向」、原則 2「外部效果可注入」、原則 3「錯誤分層」、第 5 節「輸入／輸出、驗證與錯誤格式」）、第 7 節測試策略第 9 列（`python -m ediaad` 子程序：只有子程序層能驗證 exit code 與報表契約）；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F14、第 5.2 節 CLI 介面與 exit code 表、第 5.6 節報表結構、`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-027 | `ediaad/cli.py`（`build_parser`、`_run_match`、`_write_json_atomically`）；`tests/test_cli_match_monitor.py` 8 個案例 | 符合 | — |
| AC-028 | `ediaad/cli.py`（`_run_monitor`、`_local_cache_fetch`、`main` 的例外映射）；同檔 9 個案例 | 符合 | A-2（暫時來源，已知邊界） |
| AC-029 | `ediaad/cli.py`（沿用 TASK-005／010 的掃描路徑）；同檔 2 個案例（規模門檻、逐欄一致） | 符合 | A-1（第一版未依 AC 參數，已修正） |

逐條核對：

- **AC-027**：`match --data … --sample … --top … --horizon … --out report.json` → exit 0，`report.json` 頂層鍵**恰為** `sample`／`params`／`data_source`／`matches`／`outlook`（以集合相等斷言，多鍵少鍵都會失敗）；缺資料檔 exit 2、缺樣本檔 exit 2、`--top 0`／`--horizon 0`／`--horizon -1`／`--step 0`／`--overlap 1.5` 各自 exit 2 且**不留下報表**；輸出目錄不可寫 exit 1 且不留任何暫存檔。符合。
- **AC-028**：`monitor --config … --once` → exit 0 並印出 `[MONITOR] processed=… alerted=… skipped=… warnings=…` 單行摘要；設定含未知鍵 exit 2；本機快取缺失 exit 1（`找不到本地快取`）且無 traceback；常駐模式收到 `SIGINT` 後 exit 0、stderr 出現 `[STOP]`、無 traceback，且同一事件跨輪只告警一次。符合。
- **AC-029**：以 AC 明訂的刺激條件（10,000 根、視窗 60、top 20）實測 **3.86 秒** < 60 秒；同一樣本在 200 根與 10,000 根的 top 1 報表逐欄相同。符合。

## 品質 Review

- **A-1（已修正，規格對齊）——Cycle 4 第一版未依 AC-029 的參數**：第一版效能測試用視窗 12、top 1，而 AC-029 明訂「10,000 根序列、視窗 60、top 20」。這不只是參數不同：top 1 讓「`matches` 與 `outlook` 與小資料集完全相等」變得容易成立（只需一個精確命中），降低了 AC-029 這個案例的辨識力。**修正**：效能測試改用視窗 60／top 20，並加上「20 筆命中、分數遞減、每筆為完整 60 根視窗、任兩筆重疊 ≤ 0.5」等不變式；「逐欄一致」另立一個 top 1 測試。夾具新增 `range_bars`／`name` 參數（預設不變）。
- **`_write_json_atomically`（本張最重要的品質決策）**：報表先寫同目錄暫存檔再 `replace`，因此「不可寫」時既不會留下半寫報表，也不會留下殘檔（測試同時斷言兩者）。這讓 `match` 的輸出對下游（未來的網頁與排程）是「要嘛完整、要嘛不存在」。
- **錯誤分層的落實**：`main` 只攔截三種領域錯誤與 `KeyboardInterrupt`；`DataFormatError`／`ConfigError` → 2、`SourceError` → 1、中斷 → 0，其餘例外一律以 traceback 呈現（不吞掉程式缺陷）。**這個對應表在端到端路徑上其實測不到**——`monitor` 的 exit 1 來自 `run_once` 把來源失敗收成 warning 後的計數器判斷，不經過例外映射；因此另補 `test_main_maps_errors_to_the_documented_exit_codes`（以 monkeypatch 的 stub 直接觸發三種例外）來釘住契約。這是變異檢查的第一個收穫。
- **測試邊界的自我修正**：本檔 docstring 原本寫「不直接呼叫 `cli.main` 的內部輔助函式」，但補測後新增了 4 個契約層測試，已同步改寫 docstring，明確列出兩種觀察邊界與「為何端到端測不到例外映射」的理由——避免文件與實測不符。
- **變異檢查（6 個變異全數被抓到）**：首次執行時有 **4 個存活者**，全部是測試覆蓋不足而非實作缺陷：`SourceError` 的例外映射無測試、`_local_cache_fetch` 的例外型別無測試、`--horizon 0` 未列入參數化（只測了 `-1`）、常駐模式未斷言「不重複告警」。已逐項補測（`tests/test_cli_match_monitor.py` 由 14 個增至 21 個）。另發現 `run_forever(state=...)` 的 `state` 參數自 TASK-010 起從未被測（TASK-010 只覆蓋 `run_once(state=...)`），已補 `test_run_forever_honours_a_caller_supplied_alert_state`。
- **模組責任與依賴**：`cli.py` 只依賴 `errors`／`monitor`／`data`／`scan`／`outlook` 與 pandas，未匯入 `web`／`store`／`markets`；唯一的 I/O 是讀快取 CSV、寫報表與附加事件檔——都是 CLI 的職責。符合 SPEC 第 5 節原則 1 的依賴方向。
- **測試品質**：exit code 以子程序實際觀察（不是斷言函式回傳值），符合 SPEC 第 7 節「只有子程序層能驗證 exit code」；AC-029 的效能與不變式並存；`--once` 的摘要與事件檔內容一併斷言。未發現問題。
- **命名與可讀性**：`_run_match`／`_run_monitor`／`_write_json_atomically`／`_local_cache_fetch` 皆為私有且名稱直述行為；`_local_cache_fetch` 的 docstring 明確標示「暫時來源、TASK-013 之後替換」。未發現問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 規格對齊 | advisory | `tests/test_cli_match_monitor.py` Cycle 4：第一版用視窗 12／top 1，與 AC-029 的「視窗 60／top 20」不符，辨識力偏低 | 改用 AC 明訂參數並補上排序／視窗長度／重疊比例不變式 | **已修正並驗證**：`f3e68536…`；10,000 根、視窗 60、top 20 實測 3.86 秒 |
| A-2 | 來源鏈 | advisory（已知邊界） | `ediaad/cli.py` `_local_cache_fetch`：只讀本機快取 CSV，因此 exit 1 只涵蓋「快取缺失」一途 | TASK-013 起改為「快取 → 交易所 → 過期快取」的完整來源鏈 | 待辦（已記於 TDD 紀錄） |
| A-3 | 版本標記 | advisory | TASK-001～010 的 `checked_version` 樹雜湊以未記載的方式算出，六種候選方法皆無法重現既有值 | 於 `docs/workflow/PROJECT.md` 固定計算方式，並以逐檔 sha256 作為主要校驗依據 | **已修正**：`PROJECT.md` 新增「版本標記（checked_version）的計算慣例」，TASK-011 起適用；歷史標籤已註明為不可重算 |
| A-4 | 報表語意 | advisory | `report.json` 的 `matches` 只含通過重疊抑制的結果，未揭露「原始候選數／被抑制數」；在小資料集上 `--top 20` 可能只回 2～3 筆，使用者無法區分「沒有更多命中」與「被抑制」 | 網頁端需要時於 `params` 或新欄位補上候選與抑制計數；SPEC 目前未定義，需先改 Spec | 延後（需 Spec 變更，記於此供 TASK-025 評估） |
| A-5 | 流程紀律 | advisory（非程式） | Cycle 3 的 `_run_monitor` 實作先於測試，未取得 per-Cycle Red；另 Cycle 4 改寫腳本曾誤截 5 個測試後立即補回 | 維持「先紅後綠」；改檔一律用精確片段取代 | **已記載**：TDD 紀錄「流程偏差」與「未執行或受阻」兩節如實記錄，並以整檔 Red＋變異檢查補強辨識力證據 |

## 修正與重審

- 第 1 輪：Spec Review 三個 AC 逐條符合；品質 Review 找到 A-1（規格對齊）並修正，A-3（版本標記可重現性）一併修正。
- 變異檢查首輪 4 個存活者 → 補 5 個測試（`--horizon 0` 參數化、`_local_cache_fetch` 例外型別、`main` 錯誤映射表、`run_forever` 的 `state` 尊重、常駐模式不重複告警），重跑 6／6 全數被抓到。
- 重審：重跑單檔（21 passed）、相關回歸（掃描＋統計＋偵測＋監控＋CLI 105 passed）與全套（208 passed）；重讀 `cli.py` 複查參數驗證順序、例外映射、原子寫入與常駐迴圈的停止條件。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-027～AC-029 逐條符合，含 AC-029 的參數對齊）
- 品質 Review：passed（A-1／A-3 已修正並重驗；無 blocking）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-2（TASK-013 的來源鏈）、A-4（需先變更 Spec，供 TASK-025 評估）、A-5（流程記載，非程式）
- 能否標為 done：**可以**
- 限制與未驗證事項：`_local_cache_fetch` 為暫時來源；AC-029 的耗時為單機量測（3.86 秒 vs 60 秒門檻），非跨平台保證；常駐模式無停止條件以外的排程語意（服務生命週期屬後續 Task）
