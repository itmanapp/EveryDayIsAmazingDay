# TASK-005 測試紀錄

- task_id：TASK-005
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-scan sha256:9e3074fb542f14c4c8d7f0d42513a9d8a8e0c26f4ba5bb0100c80b91207e3619
- alternative_reason：無（AC-010 與 AC-011 都有真實 Red→Green）
- Task／Spec 版本：TASK-005 / SPEC-001 v0.4
- 測試邊界：只呼叫 `ediaad.scan.scan_similar` 並觀察 `ScanMatch` 清單與 `ConfigError`；不檢視貪婪迴圈或內部狀態。合成序列為固定常數（長度 100、視窗 20），離線可跑。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-004 的交付物，全套 **56 passed**（本張完成後為 74 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 夾具設計（先用既有公開 API 驗證，不靠猜測）

重疊抑制的斷言需要**真的**存在「重疊 60% 的一對」與「重疊恰好 50% 的一對」。設計如下（長度 100、視窗 20）：

- 把一段 10 根的週期圖樣 `R` 重複 4 次鋪在 `[60, 100)`，因此起始索引 **60、70、80** 三個視窗完全相同（對範例的分數 1.0），兩兩間距 10 → 重疊 `(20-10)/20 = 50%`（恰好門檻）。
- 起始索引 **68** 與 60 的間距 8 → 重疊 `60%`。

寫下斷言之前，先以既有公開 API（`features.extract`／`extract_matrix` + `similarity.rank`）觀察完整排名：`60、70、80` 分數 1.0 並列前三；`65`（與 60 重疊 75%）第 4；**`68` 第 5（分數 0.7137）**。因此可以建立**反事實**：「68 若不被抑制，本來會被接受」——否則「被抑制」這句話不成立。

## Cycle 1：結果寬度、筆數上限、重疊抑制與 50% 邊界（AC-010，真實 Red → Green）

- AC 與預期行為：每筆寬度等於 window（`end_index == start_index + window - 1`）；筆數不超過 `top`；重疊 60% 者只留高分；重疊恰好 50% 者兩筆都保留；時間界線取自序列 `time` 欄位。
- 測試檔案／案例：`tests/test_scan.py` 的 `test_results_have_window_width_and_matching_time_bounds`、`test_top_limits_the_number_of_results`、`test_top_larger_than_candidates_does_not_pad_with_empty_values`、`test_no_two_results_overlap_more_than_the_threshold`、`test_exactly_fifty_percent_overlap_is_kept`、`test_sixty_percent_overlap_keeps_only_the_higher_scoring_match`、`test_results_are_sorted_by_score_descending`、`test_step_restricts_candidate_starts_to_multiples_of_step`、`test_zero_overlap_threshold_allows_only_disjoint_matches`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_scan.py -q` | 2 | `E ModuleNotFoundError: No module named 'ediaad.scan'`；`1 error in 0.41s` | 尚未有 `ediaad/scan.py`／2026-09-24 |
| Green | 同上 | 0 | `9 passed in 0.61s` | snap-2026-09-24-ocaievo-scan／2026-09-24 |

- Red 確實因目標行為失敗的解釋：測試匯入尚不存在的模組；`.venv` 與下游模組已在 TASK-001～004 驗證可用。
- 最小實作摘要：`ediaad/scan.py` 的 `ScanMatch`、`_overlap_ratio`（閉區間公式）與 `scan_similar`（候選起始索引 ↔ 特徵矩陣列對齊、依 `rank` 順序貪婪接受、`> overlap` 才丟棄、達 `top` 即停、以序列 `time` 欄位補時間界線）。

## Cycle 2：四類不合法參數（AC-011，真實 Red → Green）

- AC 與預期行為：範例長度不等於 window、序列短於 window、`top`／`step`／`overlap` 不合法、序列缺 `time` 欄位 → `ConfigError` 且訊息指出不合法處。
- 測試檔案／案例：`test_rejects_sample_whose_length_is_not_window`、`test_rejects_series_shorter_than_window`、`test_rejects_top_below_one`、`test_rejects_step_below_one`、`test_rejects_overlap_outside_zero_inclusive_one_exclusive`（3 個參數化）、`test_rejects_series_without_time_column`、`test_rejects_non_positive_window`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_scan.py -q` | 1 | `8 failed, 10 passed`：四個 `Failed: DID NOT RAISE ConfigError`（範例長度／序列過短／`top=0`／`overlap` 三種）、`ValueError: range() arg 3 must not be zero`（`step=0`）、`KeyError: 'time'`（缺欄位） | 同上／2026-09-24 |
| Green | 同上 | 0 | `18 passed in 0.65s` | 同上／2026-09-24 |

- Red 確實因目標行為失敗的解釋：六個失敗類別全部是「驗證尚未實作」的直接後果——不是拼字或工具問題；`step=0` 與缺 `time` 更是外洩了 numpy／pandas 的原始例外，正是 AC-011 要求擋掉的情形。
- **既有覆蓋**：`test_rejects_non_positive_window` 首次執行即通過，因為下游 `features.extract_matrix` 已對 `window < 1` 丟 `ConfigError`（TASK-003 的驗證）。如實記為既有覆蓋，且 `scan_similar` 仍自行檢查一次以保證失敗發生在抽取之前（fail fast）。
- 最小實作摘要：`scan_similar` 開頭依序檢查 `window` → 序列長度 → `time` 欄位 → 範例長度 → `top` → `step` → `overlap`，全部為 `ConfigError` 並附實際收到的值。

## 變異檢查（證明測試有辨識力）

刻意植入缺陷 → 確認對應測試失敗 → 還原並比對 sha256。

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 重疊比較由 `> overlap` 改為 `>= overlap`（變成丟棄恰好 50%） | **第一次未被抓到——查出是工具誤擊，不是測試弱點**：`> overlap` 這個字串在檔案中先出現於**模組 docstring**（第 8、17 行），`replace(..., 1)` 改到說明文字，行為未變。改為只替換程式碼那一行後重測：**被抓到**（`test_exactly_fifty_percent_overlap_is_kept`、`test_step_restricts_candidate_starts_to_multiples_of_step`） |
| M2 | 移除 `top` 上限（不 break） | 被抓到：`test_top_limits_the_number_of_results` |
| M3 | `end_index` 少一（off-by-one） | 被抓到：`test_results_have_window_width_and_matching_time_bounds`、`test_exactly_fifty_percent_overlap_is_kept` |
| M4 | 移除缺 `time` 欄位檢查 | 被抓到：`test_rejects_series_without_time_column`（再現 `KeyError`） |
| M5 | 移除範例長度檢查 | 被抓到：`test_rejects_sample_whose_length_is_not_window` |

還原後 `ediaad/scan.py` 雜湊 `cfd068a3e5ab72b285909d9637759dafa53cfd2fadce45f869db9af09b46e4d8` 與變異前一致，全套 `74 passed`。

**工具缺陷的教訓（連續第二張）**：TASK-004 的變異工具沒驗證「變異是否套用」；本次的工具有驗證檔案雜湊，卻仍不足以保證改到**目標程式碼**——替換字串必須夠精確（含縮排與整行），並在替換後人工確認命中位置。已在兩次事件後把此檢查固定為：替換字串須包含完整縮排的整行。

## 效能實測（供 TASK-011／AC-029 參考）

`scan_similar` 於 10,000 根、視窗 60、`top=20`、`step=1` → **3.70 秒**、20 筆結果，與 `extract_matrix` 單獨的 3.79 秒同量級（掃描與排序成本相對小）。AC-029 的門檻是整個 `match` 子命令 60 秒，餘裕充足。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit code | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_scan.py -q` | 0（`18 passed`） | snap-2026-09-24-ocaievo-scan |
| 相關回歸（特徵＋相似度＋掃描） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_features.py tests/test_similarity.py tests/test_scan.py -q` | 0 | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`74 passed in 1.14s`） | 同上 |
| 變異後還原驗證 | 同上 | 0（`74 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 未涵蓋：貪婪的「全域最佳化」比較（報告第 5.3 節明列為刻意取捨，不做最大總分最佳化）；`weights` 參數的轉傳（本張保留參數但未另測，權重契約由 TASK-004 的 AC-009 涵蓋）。
- 已知行為：`top` 大於可接受筆數時回傳實際筆數，不補空值（已測）。
