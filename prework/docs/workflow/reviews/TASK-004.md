# TASK-004 Code Review

- task_id：TASK-004
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-similarity sha256:23c2dbff1a4d7d13a94a6fee605dda2f2b55e7db77ba802b34fcb382f4d70903
- Task／Spec 版本：TASK-004 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `23c2dbff1a4d7d13a94a6fee605dda2f2b55e7db77ba802b34fcb382f4d70903`；本張交付的兩個檔案——`ediaad/similarity.py` `30ca12ea665f64a652740de5e4ae09bf7869e01dd4660415049e3545803c711c`、`tests/test_similarity.py` `6820964a755600ff5a81f22dff81a8731e77f341085e165b543fd07557f3543b`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對；本張新增 2 檔，未修改其他模組
- 納入的已提交、未提交、新增檔案：`ediaad/similarity.py`、`tests/test_similarity.py`（本張交付物）＋ 本張 TDD／Review 紀錄
- 排除的既有修改及理由：`data.py`／`features.py`／`errors.py`／測試與環境檔屬 TASK-001～003 交付物（已於各自 Review 審查），本張未修改
- 程式規範來源：`docs/workflow/SPEC.md` 第 5 節（`similarity.py` 的責任與公開 API、錯誤分層、原則 1）、AC-008／AC-009、報告第 5.2 節（公式與「為何用中位數與 IQR」）、報告第 8.1 節（距離度量的取捨）、`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-008 | `ediaad/similarity.py`（`Match`、`DEFAULT_WEIGHTS`、`rank`、`_robust_normalize`）；`tests/test_similarity.py` 的 7 個 Cycle 1 案例 | 符合 | — |
| AC-009 | `ediaad/similarity.py`（三項權重驗證）；`tests/test_similarity.py` 的 6 個 Cycle 2 案例 | 符合 | — |

逐條核對：

- **AC-008**：`POOL` 的第 2 與第 4 列與 `SAMPLE` 完全相同 → `matches[0].index == 2`、`score == 1.0`、`feature_distance == 0.0`；所有分數以 `(scores > 0).all()` 與 `(scores <= 1).all()` 驗證值域 (0, 1]；同分（兩列距離皆 0）以前兩名的索引 `[2, 4]` 升冪驗證；另以獨立的公式實作逐筆比對 6 列的距離與分數（`abs=1e-12`）。符合，且未多做未要求行為。
- **AC-009**：權重長度 9、含 `-0.5`、全 0 三種情況各自 `ConfigError` 且訊息含「權重」；權重乘 2 後排序與分數完全不變（逐筆 `abs=1e-12`）。另補兩個 AC 未要求但屬同一契約的檢查：`sample`／`pool` 的形狀不合法也丟 `ConfigError`（避免外洩 numpy 的 `ValueError`），以及「權重真的有作用」的正向驗證（見品質 Review）。符合。
- 兩條 AC 的錯誤型別都落在 SPEC 第 5 節的錯誤階層內（`ConfigError`，對應 CLI exit 2），未外洩 `ValueError`／`RuntimeWarning`／NaN。

## 品質 Review

- **正確性（對照報告第 5.2 節）**：正規化的統計量取自**候選池**（`np.median`／`np.percentile` 75 與 25），範例與候選都用同一組池統計量（符合「以候選池自身的統計量做穩健正規化」）；距離為加權 L1 並以 `Σw` 正規化；分數為 `1/(1+d)`。以獨立實作的公式逐筆比對通過。未發現不符。
- **退化處理**：IQR 為 0 的維度以布林遮罩退化為 0（不產生除以零）；權重總和為 0 在計分前擋下。變異檢查 M4（移除 IQR 保護）與 M3（移除負權重檢查）都會被測試抓到。未發現問題。
- **錯誤契約**：三種壞權重與兩種壞形狀皆為 `ConfigError`；訊息含「權重」或具體形狀，能直接指出問題。numpy 的 `ValueError` 與 `RuntimeWarning` 已不會外洩。未發現問題。
- **排序穩定性與可重現性**：以 `numpy.lexsort` 先分數降冪、再索引升冪；M2（把索引改為降冪）會被三個測試抓到。符合 SPEC 第 6 節「可重現性」。未發現問題。
- **模組責任與依賴**：只依賴 `numpy` 與 `ediaad.errors`／`ediaad.features`（取維度常數），未匯入 `scan`／`monitor`；不讀寫檔案、不連網、不輸出訊息。未發現問題。
- **效能與配置**：對 `(M, 10)` 的候選池做向量化運算，主要配置為 `z_pool`（M×10）；正規化統計量只算一次並重用於範例與候選。未發現問題。
- **測試品質**：oracle 為獨立實作的公式；含值域、同分、逐筆數值與權重尺度不變四類斷言；資料確定、離線、無時間依賴。**發現並修正一項測試缺陷**：`test_weights_change_which_candidate_wins` 原本使用的候選池各列在多維同時偏離，任何單維加重都不改變名次 → 測試資料**缺乏辨識力**（會永遠通過）。已改為每列只在單維偏離的 `DEVIATION_POOL`，並以實測確認斷言方向後才寫下。另外，我的變異檢查工具第一版沒有驗證「變異是否真的套用」，導致一個未套用的變異被誤讀為綠燈；已改為比對前後雜湊並在字串不存在時中止。
- **命名與可讀性**：`Match` 的三個欄位都有 docstring；`_robust_normalize` 的退化規則寫在 docstring；`rank` 的排序規則明列。未發現問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| I-1 | 規格理解 | advisory（洞察，非缺陷） | 報告第 5.2 節以「中位數與 IQR 對離群值不敏感」解釋為何不用平均數與標準差。經等價變異檢查（M1）證實：**中心點在 L1 距離中相消**（`z(x)-z(y) = (x-y)/IQR`，實測差異 0～2.22e-16），因此只有 **IQR（尺度）** 會影響排序；中心用中位數或平均數結果完全相同 | 實作不需改（兩者都正確）。若要保留「穩健」的實質效果，關鍵在尺度用 IQR 而非標準差（M5 已證實此點會被測試抓到） | 已記錄（TDD 紀錄的變異檢查與本表）；無程式變更 |
| A-1 | 測試資料辨識力 | advisory（已修正） | `test_weights_change_which_candidate_wins` 原用 `POOL` 驗證「權重會改變名次」，但該池各列多維同時偏離，任何單維加重都不改變順序 → 該斷言不可能失敗 | 改用單維偏離的 `DEVIATION_POOL` | **已修正**（`6820964a…`）；M2／M4 變異證明新斷言有辨識力 |
| A-2 | 輸入穩健性 | advisory | `rank` 未處理 `pool` 含 NaN／Inf 的情形 | 候選池由 TASK-003 的 `extract_matrix` 產生，其輸出保證有限值；若未來接受外部特徵矩陣再補檢查 | 延後（目前無此輸入路徑） |
| A-3 | 行為定義 | advisory | 空候選池回傳 `[]`（AC 未要求） | 為自然且明確的行為，已於 docstring 與 TDD 紀錄載明 | 已處理 |

## 修正與重審

第 1 輪未發現 blocking。Cycle 2 的 Red 中有三個是實作缺驗證（已補），第四個是**測試資料缺乏辨識力**（已改資料並修正方向錯誤的斷言）。變異檢查工具本身的缺陷（未驗證變異是否套用）也已修正後重跑。

重審範圍：修正後重跑單檔（13 passed）與全套（56 passed）；重讀 `similarity.py` 全文複查驗證順序（形狀 → 權重 → 計分）與退化路徑。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-008／AC-009 逐條符合；錯誤型別都在領域例外階層內）
- 品質 Review：passed（正確性、退化處理、錯誤契約、排序穩定性、模組責任、效能、測試品質皆已檢查；未發現 blocking）
- 未解決 blocking 數：0
- 延後 advisory 及理由：I-1（洞察，無程式變更）、A-2（目前無外部特徵輸入路徑）
- 能否標為 done：**可以**
- 限制與未驗證事項：未處理 NaN／Inf 候選池（A-2）；權重調校不在本版範圍
