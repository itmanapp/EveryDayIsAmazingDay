# TASK-004 測試紀錄

- task_id：TASK-004
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-similarity sha256:23c2dbff1a4d7d13a94a6fee605dda2f2b55e7db77ba802b34fcb382f4d70903
- alternative_reason：無（AC-008 與 AC-009 都有真實 Red→Green）
- Task／Spec 版本：TASK-004 / SPEC-001 v0.4
- 測試邊界：只呼叫 `ediaad.similarity.rank`，並讀取 `Match`、`DEFAULT_WEIGHTS` 與 `ediaad.features.FEATURE_NAMES`；不檢視私有正規化或距離函式。合成特徵向量為固定常數，離線可跑。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-003 的交付物（環境、`data.py`／`errors.py`、`features.py`），全套 43 passed；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用（整張以 pytest 在公開邊界驗證）。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## Cycle 1：完全相同者第 1、分數值域與同分排序（AC-008，真實 Red → Green）

- AC 與預期行為：候選池含與範例完全相同的視窗時，該候選排名第 1、分數 1.0；所有分數落在 (0, 1]；同分時以索引升冪。
- oracle 的來源：測試檔內以規格第 5.2 節的公式**獨立實作一次**穩健正規化與加權 L1 距離（`robust_normalize`／`weighted_l1_distance`），逐筆與 `rank` 的回傳值比對；不是呼叫待測函式產生期望值。
- 測試檔案／案例：`tests/test_similarity.py` 的 `test_default_weights_match_feature_count`、`test_rank_returns_match_objects_in_score_order`、`test_identical_candidates_rank_first_with_score_one_and_zero_distance`、`test_all_scores_are_within_zero_exclusive_and_one_inclusive`、`test_ties_are_ordered_by_ascending_index`、`test_distances_and_scores_match_independently_implemented_formula`、`test_ranking_is_sorted_by_score_descending`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_similarity.py -q` | 2 | `E ModuleNotFoundError: No module named 'ediaad.similarity'`；`1 error in 0.41s` | 尚未有 `ediaad/similarity.py`／2026-09-24 |
| Green | 同上 | 0 | `7 passed in 0.30s` | snap-2026-09-24-ocaievo-similarity／2026-09-24 |

- Red 確實因目標行為失敗的解釋：測試匯入尚不存在的模組；`.venv` 與 pytest 已於 TASK-001～003 驗證可用。
- 最小實作摘要：`ediaad/similarity.py` 的 `Match`、`DEFAULT_WEIGHTS`、`_robust_normalize`（候選池的**中位數**與 **IQR**，IQR 為 0 的維度退化為 0）與 `rank`（加權 L1 距離、`1/(1+d)` 分數、`numpy.lexsort` 分數降冪＋索引升冪）。

## Cycle 2：權重契約與尺度無關性（AC-009，真實 Red → Green）

- AC 與預期行為：權重長度不符、含負值、總和為 0 → `ConfigError`；權重整體乘 2 不改變排序與分數。
- 測試檔案／案例：`test_rank_rejects_weights_with_wrong_length`、`test_rank_rejects_negative_weights`、`test_rank_rejects_zero_sum_weights`、`test_weight_scale_does_not_change_order_or_scores`、`test_default_weights_rank_the_smaller_normalized_deviation_ahead`、`test_upweighting_a_dimension_changes_the_ranking`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_similarity.py -q` | 1 | `4 failed, 8 passed, 1 warning`：長度不符丟 `ValueError` 而非 `ConfigError`；負權重未被拒；總和為 0 時出現 `RuntimeWarning: invalid value encountered in divide`（產生 NaN 分數）；另有一個斷言失敗（見下） | 同上／2026-09-24 |
| Green | 同上 | 0 | `13 passed in 0.34s` | 同上／2026-09-24 |

- Red 確實因目標行為失敗的解釋：三個驗證缺口都是「驗證尚未實作」的直接後果；總和為 0 會產生 NaN，是真正的缺陷而非風格問題。
- **逐一處理第四個失敗（測試本身的問題，非實作缺陷）**：`test_weights_change_which_candidate_wins` 原本主張「把第 9 維加重會改變名次」，但實測發現原候選池的 6 列在**多個維度同時偏離**，任何單維加重都不改變順序——是**測試資料缺乏辨識力**。處理方式：
  1. 另建 `DEVIATION_POOL`（每列只在單一維度偏離範例），使權重的作用可被觀測；
  2. 第一版新斷言仍寫錯方向（我以為加重第 9 維會讓第 4 列超前第 0 列）；實測顯示加重第 9 維是**懲罰在該維偏離大的第 1 列**，翻轉的是第 1 列與第 3 列；
  3. 以實測確認方向後才寫下斷言（`order.index(1) < order.index(3)` 於預設權重、`order.index(3) < order.index(1)` 於第 9 維 ×10）。
  - 兩次修正都是**修正測試**，不是放寬實作；過程如實記錄，避免「先有結論再湊斷言」。
- 最小實作摘要：`rank` 加入範例／候選池形狀檢查、權重長度檢查、負值檢查與總和為 0 檢查（皆為 `ConfigError`），並保留空候選池回傳 `[]`。

## 變異檢查（證明測試有辨識力）

刻意植入缺陷 → 確認對應測試失敗 → 還原並比對 sha256。**第一次嘗試的工具有缺陷**：它沒有驗證「替換字串是否真的存在」，其中一個變異其實沒有套用卻仍印出綠燈，等於跑在原始檔上。已重做工具有（比對前後雜湊、字串不存在即中止）。

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 穩健統計量的中心由 `np.median` 改為 `np.mean` | **未被抓到（13 passed）——經查為等價變異，非測試弱點**：`z(x)-z(y) = (x-y)/IQR`，中心點在 L1 距離中相消。實測 6 列距離差為 0.00e+00～2.22e-16 |
| M2 | 同分時改為索引降冪（`lexsort` 第一個鍵取負） | 被抓到：`test_identical_candidates_rank_first_...`、`test_ties_are_ordered_by_ascending_index`、`test_default_weights_rank_the_smaller_normalized_deviation_ahead` |
| M3 | 移除負權重檢查 | 被抓到：`test_rank_rejects_negative_weights` |
| M4 | 移除「IQR 為 0 的維度退化為 0」保護 | 被抓到：`test_default_weights_rank_the_smaller_normalized_deviation_ahead`、`test_upweighting_a_dimension_changes_the_ranking` |
| M5 | 尺度由 IQR 改為標準差 | 被抓到：`test_distances_and_scores_match_independently_implemented_formula` |

還原後 `ediaad/similarity.py` 雜湊 `30ca12ea665f64a652740de5e4ae09bf7869e01dd4660415049e3545803c711c` 與變異前一致，全套 `56 passed`。

**M1 的結論（重要）**：報告第 5.2 節說「用中位數與 IQR 而非平均數與標準差，因為對離群值不敏感」——就本實作而言，**只有 IQR 那部分對距離有影響**；中心點用中位數或平均數會得到完全相同的排序。這不是缺陷（兩者都正確），但「為什麼選中位數」的理由在本函式中只對尺度成立，已記入 review 的 I-1。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit code | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_similarity.py -q` | 0（`13 passed`） | snap-2026-09-24-ocaievo-similarity |
| 全套回歸（含 TASK-002／003） | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`56 passed in 0.73s`） | 同上 |
| 變異後還原驗證 | 同上 | 0（`56 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 已知邊界（記錄，不在本張範圍）：空候選池回傳 `[]`（未在 AC 中要求，但為自然且明確的行為）；`rank` 未處理 `pool` 含 NaN 的情形（候選池由 TASK-003 的 `extract_matrix` 產生，其輸出保證為有限值）。
- 未涵蓋：權重的自動調校或學習（本版權重由使用者提供，`DEFAULT_WEIGHTS` 全為 1）。
