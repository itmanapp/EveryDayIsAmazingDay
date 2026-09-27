# TASK-003 測試紀錄

- task_id：TASK-003
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-features sha256:eca3deca94d213cb0f009e6c5537f57bd431b03ff79ba9910d981142f7662272
- alternative_reason：無（本張為純計算程式任務，AC-005 有真實 Red→Green；AC-006／AC-007 見下方「既有覆蓋」的如實說明，並以變異檢查補強測試辨識力）
- Task／Spec 版本：TASK-003 / SPEC-001 v0.4
- 測試邊界：只呼叫 `ediaad.features.extract`／`extract_matrix` 與讀取 `FEATURE_NAMES`；不檢視私有輔助函式。合成序列以 `math.sin` 與固定常數產生（無亂數、無網路），全程離線。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001（環境）與 TASK-002（`ediaad/data.py`、`ediaad/errors.py`、`tests/test_data.py`，17 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用（整張仍以 pytest 在公開邊界驗證）。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 開工前的規格修正（SPEC-001 v0.3 → v0.4）

逐維推導 AC-006 時發現 v0.1 寫下的敘述不可能成立：把整段價格**加常數平移**後，`total_return`＝`close[-1]/close[0]-1`、`return_std`（逐根**比值**報酬的標準差）與 `max_drawdown`（`close` 對累積最高的**比值**）依定義必然改變。報告第 5.1 節只宣稱特徵「**乘上正數 k 後全部不變**」；平移不變性是報告第 2.11 節對**規律判定**的要求（已由 AC-019 涵蓋）。

因此先修正 AC-006 為「乘常數 → 10 維全部不變；平移 → 第 3、4、5、6、8、9、10 維不變」，並在 SPEC 第 9 節留下理由（v0.4）。此修正讓需求與報告一致、且比原敘述**更寬鬆**（移除做不到的要求），不改變任何 AC 的 ID 或範圍。修正後 42 個文件的 `spec_version` 同步為 `SPEC-001 v0.4`。

## Cycle 1：10 維特徵與手算值相符（AC-005，真實 Red → Green）

- AC 與預期行為：`FEATURE_NAMES` 長度 10 且順序固定；`extract(window)` 回傳形狀 `(10,)`、dtype `float64` 的向量，逐維與手算值相符（容差 1e-9）。
- oracle 的來源：`EXPECTED_VECTOR` 以**獨立算術**推導——只用標準庫 `statistics.pstdev` 與四則運算，完全不經過 `ediaad.features`；每個值的推導寫在測試檔的註解旁（例如 `mean_body_ratio = mean([5/15, 5/15, 4/16, 5/8])`）。不是「用同一段演算法當 oracle」。
- 測試檔案／案例：`tests/test_features.py::test_feature_names_contract`、`::test_extract_returns_float64_vector_of_length_ten`、`::test_extract_matches_independently_derived_values`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_features.py -q` | 2 | `E ModuleNotFoundError: No module named 'ediaad.features'`；`1 error in 0.40s` | 尚未有 `ediaad/features.py`／2026-09-24 |
| Green | 同上 | 0 | `3 passed in 0.31s` | snap-2026-09-24-ocaievo-features／2026-09-24 |

- Red 確實因目標行為失敗的解釋：測試匯入尚不存在的模組，失敗來自目標模組未實作；`.venv` 與 pytest 已於 TASK-001／TASK-002 驗證可用。
- 最小實作摘要：`ediaad/features.py` 的 `FEATURE_NAMES`、`_safe_divide`（分母為 0 時回 0）、`extract`（10 維公式）。
- 附帶事實：以獨立算術複核時，我原先手算的 `return_std` 與正確值不符（手算 0.0408、獨立計算 0.04531）；採用獨立計算結果作為 oracle，證明「不以心算當唯一來源」是必要的。

## Cycle 2：尺度不變、平移不變的適用範圍與退化情境（AC-006）

- AC 與預期行為：四種乘常數（0.01／0.5／1／1000）後 10 維全部不變；三種平移（+7／+1234.5／−42）後第 3、4、5、6、8、9、10 維不變，第 1、2、7 維**必須改變**；全平坦視窗、零量能視窗、長度 1 與 2 的極短視窗皆回傳有限值。
- 測試檔案／案例：`test_extract_is_invariant_under_price_scaling`（4 個參數化）、`test_extract_is_translation_invariant_for_difference_based_features`（3 個）、`test_translation_does_change_the_three_price_ratio_features`（3 個）、`test_extract_handles_flat_window_with_finite_values`、`test_extract_handles_zero_volume_window_with_finite_values`、`test_extract_handles_very_short_windows`（2 個）——共 14 個案例。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| 既有覆蓋（非 Red） | `.venv/bin/python -m pytest tests/test_features.py -q` | 0 | `17 passed in 0.37s`（首次執行即通過） | snap-2026-09-24-ocaievo-features／2026-09-24 |

- 如實說明（依 `references/tdd.md`「若測試一開始就是綠……如實記為既有覆蓋，不捏造 Red」）：AC-006 的不變性與退化行為，是 Cycle 1 為滿足 AC-005 而實作的同一段公式的**直接後果**（例如 `_safe_divide` 的零分母遮蓋同時滿足退化要求；純比值／差值的公式本身即具乘常數不變性）。因此這些測試無法有真實 Red，記為**既有覆蓋**，不宣稱 Red。
- 補強（見下方「變異檢查」）：為避免「既有覆蓋」變成「空轉測試」，以故意植入缺陷的方式證明這些斷言真的會失敗。
- 設計細節：`test_translation_does_change_the_three_price_ratio_features` 是**反向斷言**——它要求不具平移不變性的三維必須改變。若有人把不變性測試寫成恆真（例如對全部 10 維都斷言不變），這個測試就會失敗，因此能防止 AC-006 被誤解成「全部 10 維都平移不變」。

## Cycle 3：批次矩陣的形狀、逐窗一致與寬度契約（AC-007）

- AC 與預期行為：長度 200、視窗 20、步長 1 → 形狀 `(181, 10)`；每一列與逐窗 `extract` 相同（atol 1e-12）；`step=3` 的列數與起始索引對應；`step=20`（等於視窗）不重疊；`window` 為 5／20／60 時 `shape[1]` 固定為 10 且 `nbytes == 列數 × 10 × 8`（沒有隨視窗長度成長的內容）；不合法參數丟 `ConfigError`；序列短於視窗回傳 `(0, 10)`。
- 測試檔案／案例：`test_extract_matrix_shape_for_length_200_window_20_step_1`、`test_extract_matrix_rows_equal_per_window_extract`、`test_extract_matrix_step_20_does_not_overlap`、`test_extract_matrix_width_is_fixed_and_payload_has_no_window_sized_data`、`test_extract_matrix_rejects_invalid_parameters`（4 個）、`test_extract_matrix_returns_empty_matrix_when_series_is_shorter_than_window`——共 9 個案例。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| 既有覆蓋（非 Red） | `.venv/bin/python -m pytest tests/test_features.py -q` | 0 | `26 passed in 0.68s`（首次執行即通過） | snap-2026-09-24-ocaievo-features／2026-09-24 |

- 如實說明：`extract_matrix` 在 Cycle 1 的同一次編輯中一併實作（它只是對 `extract` 的滑動呼叫），因此本 Cycle 的三類測試首次執行即通過，記為**既有覆蓋**。
- 效能實測（提供 TASK-011／AC-029 的事前資訊，不是本張門檻）：`extract_matrix` 於 1,000 根／視窗 20 → **0.39 秒**；10,000 根／視窗 60 → **3.79 秒**，形狀 `(9941, 10)`。AC-029 的門檻是整個 `match` 子命令 60 秒，目前留有充足餘裕。

## 變異檢查（證明測試有辨識力）

因為 Cycle 2／Cycle 3 屬既有覆蓋，額外做一次「故意植入缺陷 → 確認對應測試失敗 → 還原」的檢查。每次都以 `cp` 備份還原，最後比對 sha256。

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | `return_std` 由母體標準差改為 `ddof=1` | `FAILED test_extract_matches_independently_derived_values`、`FAILED test_extract_handles_very_short_windows[2]`（AC-005 的 oracle 測試抓到） |
| M2 | `_safe_divide` 移除零分母遮蓋（`where=(den != 0)`） | `FAILED test_extract_handles_flat_window_with_finite_values`（AC-006 的退化測試抓到） |
| M3 | `extract_matrix` 忽略 `step`（固定為 1） | `FAILED test_extract_matrix_rows_equal_per_window_extract`、`FAILED test_extract_matrix_step_20_does_not_overlap`（AC-007 的矩陣測試抓到） |

還原後 `ediaad/features.py` 雜湊 `e6bce065e84bb5a88b8d9844a294c4a1885a7fad271911b7527ffe5781d3c1f7` 與變異前一致，全套 `43 passed`。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit code | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_features.py -q` | 0（`26 passed in 0.68s`） | snap-2026-09-24-ocaievo-features |
| 全套回歸（含 TASK-002 的 17 個案例） | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`43 passed in 0.75s`） | 同上 |
| 變異後還原驗證 | 同上 | 0（`43 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 已知邊界（僅記錄，不在本張範圍）：`extract` 對**空視窗**（0 根）會丟 `IndexError`，對缺少 OHLCV 欄位的框架會丟 `KeyError`。這兩者都由呼叫端的契約保證不會發生（TASK-002 產出的序列保證欄位齊全；TASK-005 保證序列長度不小於視窗並以 `ConfigError` 擋下過短序列）。已列入 review 的 advisory。
- 未涵蓋：`extract_matrix` 的向量化最佳化（目前為逐窗呼叫，10,000 根 3.79 秒）；AC-029 的整體門檻由 TASK-011 驗證。
