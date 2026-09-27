# TASK-003 Code Review

- task_id：TASK-003
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-features sha256:eca3deca94d213cb0f009e6c5537f57bd431b03ff79ba9910d981142f7662272
- Task／Spec 版本：TASK-003 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `eca3deca94d213cb0f009e6c5537f57bd431b03ff79ba9910d981142f7662272`；本張交付的兩個檔案——`ediaad/features.py` `e6bce065e84bb5a88b8d9844a294c4a1885a7fad271911b7527ffe5781d3c1f7`、`tests/test_features.py` `8c486efee361e234463775e423f0221d9c3e2414ec475760d70f26ef6f559ede`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對；本張新增 2 檔（`ediaad/features.py`、`tests/test_features.py`）、修改 SPEC 與文件（見下）
- 納入的已提交、未提交、新增檔案：`ediaad/features.py`、`tests/test_features.py`（本張交付物）；`docs/workflow/SPEC.md`（AC-006 修正，v0.3 → v0.4）、`docs/workflow/tasks/TASK-003.md`、37 張 Task 與 `TASKS.md`／`STATE.md`／`PROJECT.md`／`ADR-001.md`／`PROJECT_WORKFLOW.md` 的 `spec_version` 同步、本張 TDD 與 Review 紀錄
- 排除的既有修改及理由：`ediaad/data.py`、`ediaad/errors.py`、`tests/test_data.py`、`scripts/bootstrap_env.py`、`requirements*.txt` 屬 TASK-001／TASK-002 交付物（已於各自 Review 審查），本張未修改
- 程式規範來源：`docs/workflow/SPEC.md` 第 5 節（`features.py` 的責任與公開 API、原則 1「計算不碰 I/O」、錯誤分層）、第 6 節（可重現性）、第 2 節與 AC-006（尺度不變／平移不變的適用範圍）、報告第 5.1／5.2／5.3 節、`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-005 | `ediaad/features.py`（`FEATURE_NAMES`、`extract`）；`tests/test_features.py::test_feature_names_contract`、`::test_extract_returns_float64_vector_of_length_ten`、`::test_extract_matches_independently_derived_values` | 符合 | — |
| AC-006 | `ediaad/features.py`（`_safe_divide` 與 10 個公式）；`tests/test_features.py` 的 14 個不變性／退化案例 | 符合（AC 文字已於本張開工前修正為 v0.4，見下） | S-1（規格瑕疵，已修正） |
| AC-007 | `ediaad/features.py`（`extract_matrix`）；`tests/test_features.py` 的 9 個矩陣案例 | 符合 | — |

逐條核對：

- **AC-005**：`len(FEATURE_NAMES) == 10`、順序等於規格列出的 10 個名稱、無重複、皆為 `str`；`extract` 回傳 `numpy.ndarray` 形狀 `(10,)`、dtype `float64`；10 維逐維與**獨立算術**推導的 oracle 以 `atol=1e-9` 相符。未多做未要求行為（沒有加入週期、時間或跨商品特徵）。
- **AC-006**：四種乘常數後 10 維全部不變（4 個參數化案例）；三種平移後第 3、4、5、6、8、9、10 維不變（3 個案例）；**另有反向斷言**要求第 1、2、7 維必須改變（3 個案例），防止不變性被誤寫成恆真；全平坦視窗、零量能視窗、長度 1／2 的極短視窗皆 `numpy.isfinite(...).all()` 且退化維度為 0。符合。
- **AC-007**：`(181, 10)`、逐列與逐窗 `extract` 在 `atol=1e-12` 內相等、`step=3` 的列數與起始索引對應、`step=20` 不重疊、`window` 為 5／20／60 時 `shape[1]` 固定且 `nbytes` 等於「列數 × 10 × 8」（證明沒有隨視窗長度成長的內容）、四種不合法參數丟 `ConfigError`、序列短於視窗回傳 `(0, 10)`。符合。
- **S-1（規格瑕疵，於本張開工前修正，非隱藏變更）**：v0.1 寫下的 AC-006 要求「加常數平移後**特徵向量**不變」，但 `total_return`、`return_std`、`max_drawdown` 依定義使用價格**比值**，平移後必然改變；報告第 5.1 節也只宣稱「乘上正數 k 後全部不變」。已在寫測試前修正 AC-006（v0.4）並記入 SPEC 第 9 節，使需求與報告一致；此修正**移除做不到的要求**，不改任何 AC ID 或範圍。已在進度報告中告知使用者。

## 品質 Review

- **正確性（逐維對照報告第 5.1 節）**：10 個公式與報告定義一致——`total_return`＝`close[-1]/close[0]-1`；`return_std` 為逐根比值報酬的**母體**標準差（`numpy.std` 預設 `ddof=0`，與獨立 oracle 的 `statistics.pstdev` 相符）；實體比與上下影線比分母皆為 `high-low`；`bull_ratio` 為 `close > open` 的比例（嚴格大於）；`max_drawdown`＝`1 - min(close / cummax(close))`；`ma_slope_normalized` 為最小平方斜率除以收盤母體標準差；`volume_ratio` 分母為前半量能；`close_position` 分母為 `max(high) - min(low)`。未發現不符。
- **數值穩健性**：所有除法都經 `_safe_divide` 或顯式分母檢查（`slope_variance != 0`、`close_std != 0`、`first_half.size == 0 or mean == 0`），被遮蓋的位置為 0，符合報告「退化情境一律回傳有限值而非 NaN」與 SPEC AC-006。以變異檢查驗證：移除零分母遮蓋後，全平坦視窗測試確實失敗。未發現問題。
- **錯誤處理與錯誤契約**：不合法參數（`window < 1`、`step < 1`）丟 `ConfigError`，與 SPEC 第 5 節「參數不合法 → exit 2」一致；序列短於視窗回傳 `(0, 10)` 而不丟錯（該情境由 TASK-005 的掃描層以 `ConfigError` 擋下，符合 TASK-003 的「不定義」約定並在此明確記錄行為）。未發現問題。
- **模組責任與依賴方向**：`features.py` 只依賴 `numpy`、`pandas` 與 `ediaad.errors`，未匯入 `scan`／`similarity`／`monitor`；不讀寫檔案、不連網、不用亂數、不輸出訊息，符合 SPEC 第 5 節原則 1 與依賴方向。未發現問題。
- **公開介面與可用性**：`__all__` 明確列出三個名稱；`FEATURE_NAMES` 為 `tuple[str, ...]` 且順序即輸出順序（TASK-004 的權重向量可據此對齊）。未發現問題。
- **效能與記憶體契約**：`extract_matrix` 的輸出為單一連續 float64 區塊，寬度固定 10，不隨視窗長度成長（以 `nbytes` 斷言）。實測 1,000 根／視窗 20 → 0.39 秒；10,000 根／視窗 60 → 3.79 秒，距 AC-029 的 60 秒門檻有充足餘裕。未發現問題。
- **測試品質**：oracle 為獨立算術（非同一段演算法）；含 4 個參數化乘常數、3 個平移與 3 個反向斷言；退化情境以 `isfinite` 與具體值雙重斷言；矩陣以逐窗迴圈比對；兩組測試都以 `tmp_path`／合成資料隔離，無網路、無時間依賴、無亂數。既有的「既有覆蓋」弱點已以**變異檢查**（M1／M2／M3 各自被對應測試抓到）補強辨識力證據。未發現問題。
- **命名與可讀性**：`_safe_divide`、`_scalar`、`TRANSLATION_INVARIANT_INDICES` 等名稱直接表達意圖；模組 docstring 明列尺度／平移不變的**適用範圍**與退化慣例，避免後續誤用。未發現問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| S-1 | Spec 正確性 | advisory（於開工前修正，未進入實作） | SPEC v0.1 的 AC-006 要求平移後 10 維全部不變，與報告特徵定義矛盾 | 修正 AC-006 為「乘常數全部不變；平移 7 維不變」，並在 AC 文字與 SPEC 第 9 節說明 | **已修正**（SPEC-001 v0.4）；42 檔 `spec_version` 同步；本張測試即依 v0.4 撰寫 |
| A-1 | 邊界契約 | advisory | `extract` 對空視窗（0 根）丟 `IndexError`、對缺 OHLCV 欄位的框架丟 `KeyError` | 呼叫端契約已保證不發生（TASK-002 的序列保證欄位；TASK-005 保證長度）；若要更防禦可在 `extract` 開頭檢查並丟 `ConfigError` | 延後（本張不引入未要求的驗證層；已在 TDD 紀錄的「未執行或受阻」記錄實際行為） |
| A-2 | 效能 | advisory | `extract_matrix` 以逐窗 Python 迴圈實作，10,000 根／視窗 60 為 3.79 秒 | 可用向量化 rolling 運算加速；但 AC-029 門檻為 60 秒，現況餘裕充足 | 延後（由 TASK-011 驗證 AC-029 門檻；若逾時再最佳化） |
| A-3 | 文件 | advisory | 平移不變的適用範圍容易誤解（7 維不變、3 維會變） | 已在模組 docstring、SPEC AC-006 與測試的反向斷言三處同時說明 | 已處理 |

## 修正與重審

第 1 輪未發現 blocking。S-1 為規格層瑕疵，在**寫測試之前**發現並修正（SPEC v0.4），因此沒有「先實作錯的版本再回頭改」；A-1～A-3 為 advisory，已記錄理由。

重審範圍：修正 SPEC 後重新核對本張的三個 AC 文字與測試斷言一致；重跑 `tests/test_features.py`（26 passed）與全套（43 passed）。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-005／AC-006／AC-007 逐條符合；S-1 為規格本身的瑕疵且已於開工前修正）
- 品質 Review：passed（正確性、數值穩健性、錯誤契約、模組責任、效能、測試品質、命名皆已檢查，未發現 blocking）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（呼叫端契約已保證，且記錄了實際行為）、A-2（AC-029 門檻有充足餘裕）
- 能否標為 done：**可以**
- 限制與未驗證事項：`extract` 的防禦性輸入檢查未加入（A-1）；`extract_matrix` 未向量化（A-2）；本張無外部依賴，故無「未實機驗證」項目
