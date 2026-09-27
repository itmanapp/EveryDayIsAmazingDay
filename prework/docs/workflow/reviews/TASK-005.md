# TASK-005 Code Review

- task_id：TASK-005
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-scan sha256:9e3074fb542f14c4c8d7f0d42513a9d8a8e0c26f4ba5bb0100c80b91207e3619
- Task／Spec 版本：TASK-005 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `9e3074fb542f14c4c8d7f0d42513a9d8a8e0c26f4ba5bb0100c80b91207e3619`；本張交付的兩個檔案——`ediaad/scan.py` `cfd068a3e5ab72b285909d9637759dafa53cfd2fadce45f869db9af09b46e4d8`、`tests/test_scan.py` `b8b0b991de4f82256212b0d0241c60f32b403b13087f6a5bff697cad13644bce`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對；本張新增 2 檔，未修改其他模組
- 納入的已提交、未提交、新增檔案：`ediaad/scan.py`、`tests/test_scan.py`（本張交付物）＋ 本張 TDD／Review 紀錄
- 排除的既有修改及理由：`data.py`／`features.py`／`similarity.py`／`errors.py` 與既有測試屬 TASK-001～004 交付物（已於各自 Review 審查），本張未修改
- 程式規範來源：`docs/workflow/SPEC.md` 第 5 節（`scan.py` 的責任、`ScanMatch` 欄位、原則 1 與 3）、AC-010／AC-011、報告第 5.3 節（七步流程、重疊公式、嚴格大於的邊界、貪婪取捨、`(M,10)` 效能設計）、`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-010 | `ediaad/scan.py`（`ScanMatch`、`_overlap_ratio`、`scan_similar`）；`tests/test_scan.py` 的 9 個 Cycle 1 案例 | 符合 | — |
| AC-011 | `ediaad/scan.py` 的七項前置檢查；`tests/test_scan.py` 的 9 個 Cycle 2 案例（含 3 個參數化） | 符合 | — |

逐條核對：

- **AC-010**：每筆 `end_index == start_index + 20 - 1` 且 `time_start`／`time_end` 等於序列 `time` 欄位在起訖索引的值；`top=1` 回傳 1 筆、`top=3` 不超過 3 筆、`top=1000` 不補空值；**重疊 60%**：起始 68 在完整排名中為第 5 名（反事實已證實），但不在結果中，而起始 60 在結果中；**恰好 50%**：起始 60、70、80 三筆都在結果中且兩兩重疊精確等於 0.5；另以「所有配對重疊 ≤ 0.5」與「`overlap=0` 時所有配對重疊 = 0」兩個性質斷言把界線鎖死。符合，未多做未要求行為（沒有加入全域最佳化、沒有回傳未通過抑制的候選）。
- **AC-011**：四類壞參數（範例長度、序列過短、`top`／`step`／`overlap`、缺 `time` 欄位）各自 `ConfigError`，訊息含可辨識的關鍵字（`範例長度`／`短於`／`top`／`step`／`overlap`／`time`），且實際收到的值會出現在訊息中。另補 `window < 1` 的檢查（與 TASK-003 的下游檢查重複，但讓失敗發生在抽取之前）。符合。
- 錯誤型別都在 SPEC 第 5 節的錯誤階層內（`ConfigError`，對應 CLI exit 2）；Red 階段的 `ValueError: range()` 與 `KeyError: 'time'` 已被擋掉。

## 品質 Review

- **正確性（對照報告第 5.3 節七步流程）**：候選起始索引以 `range(0, L - W + 1, step)` 產生，與 `extract_matrix(series, W, step)` 的列順序**必然對齊**（兩者用同一個 range），因此 `rank` 回傳的列索引可直接映射回起始索引——這是本模組最容易出錯的地方，已由「逐筆時間界線」與「`step=10` 時所有起始索引為 10 的倍數」兩個測試把關（M3 off-by-one 變異亦被抓到）。未發現問題。
- **邊界定義**：貪婪接受使用嚴格大於（`> overlap`）丟棄，因此重疊恰好 50% 保留；此定義在模組 docstring、SPEC AC-010 與報告第 5.3 節三處一致，並由 M1（改為 `>=`）證明測試能抓到誤用。未發現問題。
- **錯誤處理**：七項檢查全部前置（fail fast，不先做昂貴的特徵抽取），訊息含實際值；驗證順序（`window` → 序列長度 → `time` → 範例長度 → `top` → `step` → `overlap`）讓每個測試都能隔離單一錯誤。未發現問題。
- **模組責任與依賴**：只依賴 `features`、`similarity`、`errors` 與 numpy／pandas；未匯入 `monitor`／`cli`；不讀寫檔案、不連網、不輸出訊息（SPEC 第 5 節原則 1）。符合報告第 4.2 節的依賴方向。未發現問題。
- **效能**：候選特徵矩陣固定 `(M, 10)`，不隨視窗長度成長；貪婪接受為 O(M·K)（報告第 5.3 節的預期）。實測 10,000 根／視窗 60／`top=20` → **3.70 秒**，與 `extract_matrix` 的 3.79 秒同量級。未發現問題。
- **測試品質**：夾具**先以既有公開 API 驗證排名**才寫斷言（建立 68 的反事實），不是「先寫結論再湊資料」；含邊界（恰好 50%）、性質（所有配對重疊 ≤ 門檻）、`step`、`top`、時間界線與四類錯誤；資料確定、離線、無時間依賴。變異檢查 M1～M5 全部被抓到（M1 的第一次「未抓到」經查為工具誤擊 docstring，非測試弱點）。未發現問題。
- **命名與可讀性**：`_overlap_ratio` 的公式在 docstring 與 SPEC 一致；`ScanMatch` 五個欄位都有 docstring；模組 docstring 說明貪婪的取捨與 `(M,10)` 的效能設計。未發現問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 型別精確度 | advisory | `ScanMatch.time_start`／`time_end` 標為 `Any`，實際為 `pandas.Timestamp` | 可改標 `pd.Timestamp`；但目前沿用「由序列 `time` 欄位取得」的契約，且無型別檢查工具 | 延後（不影響行為；交付報告列為已知事項） |
| A-2 | 演算法取捨 | advisory（刻意） | 貪婪接受不保證全域最佳解（例如某高分片段被抑制後，可能少收其他片段） | 報告第 5.3 節已明列為刻意取捨（可預期性優於最佳化），不建議改動 | 已記錄（規格與模組 docstring 皆載明） |
| A-3 | 效能 | advisory | 即使 `top=1` 仍會抽取並排序全部候選（無提前結束） | 可先抽特徵再逐步排序；但 10,000 根僅 3.70 秒，AC-029 門檻 60 秒，無實際壓力 | 延後（由 TASK-011 驗證 AC-029 門檻） |
| A-4 | 重複驗證 | advisory | `window < 1` 同時由 `scan_similar` 與 `features.extract_matrix` 檢查 | 刻意保留：讓錯誤在抽取前發生（fail fast），且 `scan.py` 不應假設下游一定有檢查 | 已處理 |
| P-1 | 流程工具 | advisory（流程） | 變異檢查工具以 `replace(..., 1)` 替換，第一次誤擊模組 docstring 中的同名字串，導致「未抓到」的錯誤結論 | 替換字串須包含完整縮排的整行 | 已修正並重測（M1 確實被抓到）；已記入 TDD 紀錄 |

## 修正與重審

第 1 輪未發現 blocking。Cycle 2 的 Red 有 8 個失敗（六類驗證缺口），已全數補上並重驗。變異檢查工具兩度出現誤判（TASK-004 未驗證是否套用；本張誤擊 docstring），都已查出並修正，未讓錯誤結論留在證據中。

重審範圍：修正後重跑單檔（18 passed）、相關回歸（特徵＋相似度＋掃描）與全套（74 passed）；重讀 `scan.py` 全文複查驗證順序、起訖索引對齊與時間界線。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-010／AC-011 逐條符合；60% 與恰好 50% 的邊界都有直接證據與反事實）
- 品質 Review：passed（正確性、邊界、錯誤處理、模組責任、效能、測試品質皆已檢查；未發現 blocking）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（型別標註）、A-2（刻意的貪婪取捨）、A-3（效能有充足餘裕）
- 能否標為 done：**可以**
- 限制與未驗證事項：未做全域最佳化；`top=1` 時不做提前結束最佳化
