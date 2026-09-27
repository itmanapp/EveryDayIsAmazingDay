# TASK-008 測試紀錄

- task_id：TASK-008
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-patterns-detect sha256:819486e7792c225bfd778b30b71e35f47dc7c59f12704a1f452d9dc721262c94
- alternative_reason：無（五個 Cycle 中有四個有真實 Red）
- Task／Spec 版本：TASK-008 / SPEC-001 v0.4
- 測試邊界：只呼叫 `ediaad.patterns.atr`／`detect`，並讀取 `PatternEvent`／`PatternSpec`；不檢視二分搜尋、累積和或去重實作。合成序列由夾具函式產生，離線可跑。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-007 的交付物，全套 **122 passed**（本張完成後為 150 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## Cycle 1：ATR 的計算與「不引用未來」（AC-016，真實 Red → Green）

- oracle：ATR 期望值以**純 Python 四則運算**獨立推導（`TR = [1.0, 2.0, 1.5, 1.5, 3.0, 2.0, 3.0, 2.0]`，週期 3），不經 `atr()`。
- 測試：`test_atr_returns_series_with_nan_warmup`、`test_atr_matches_independently_derived_values`、`test_atr_with_period_one_equals_true_range`、`test_atr_does_not_look_ahead`。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_patterns_detect.py -q` | 2 | `ImportError: cannot import name 'PatternEvent'` | 尚未有 `atr`／`PatternEvent`／2026-09-24 |
| Green | 同上 | 0 | `4 passed in 0.29s` | 同上／2026-09-24 |

- 「不引用未來」的測試**同時斷言反事實**：把植入點之後的價格乘 10，之前各索引的 ATR 差異 < 1e-12，**且**植入點之後的值必須確實改變（否則測試沒有辨識力）。
- 最小實作：`atr(series, period) -> pd.Series`（`previous_close[0] = close[0]`、`cumsum` 滾動平均、前 `period-1` 個為 NaN）與 `PatternEvent`（九欄位 frozen dataclass）。`detect` 此時以 `NotImplementedError` 佔位，讓 Cycle 2 有真實 Red。

## Cycle 2：三相位命中、欄位定義與信心值（AC-017，真實 Red → Green）

- 夾具：長度 80；0..28 安靜震盪、29 深谷（low 90，避免盤整區間往前延伸）、30..49 盤整（close 交錯 100.0／100.4、high=+1.0、low=−1.0 → band 2.4、區間低點 99.0、均值 100.2）、50 跌破（low 97.0）、51 回歸、之後安靜震盪。
- oracle：信心值以**獨立實作**的 `average_true_range()`（純 Python）加 SPEC 第 5.6 節公式計算；`band`／`depth`／`recovery_bars` 由夾具設計直接推導。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `4 failed, 5 passed`：四個 `NotImplementedError` | 同上／2026-09-24 |
| Green | 同上 | 0 | `9 passed in 0.35s` | 同上／2026-09-24 |

- 實作 ①②③⑤（盤整相位的最長可行區間、跌破、回歸、信心值）。
- 首輪綠燈時 `len(events) == 1` 失敗（實際 2 筆：盤整長度 19 與 20）。**這不是缺陷**——「同一結構只留最長」屬 AC-020 的 ⑥ 去重，此時尚未實作。調整 AC-017 的斷言為「選出盤整相位結束於植入位置的那筆事件」，把「恰好一筆」明確留給 Cycle 5，避免把兩條 AC 混在一起。
- 信心值實測 `0.79145299…` 與手算一致（band_score 0.6、depth_score 0.974359、recovery_score 0.8）。

## Cycle 3：四種反例（AC-018）——**抓到一個真實缺陷**

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `3 failed, 12 passed` | 同上／2026-09-24 |
| Green | 同上 | 0 | `15 passed in 0.36s`（修正缺陷與夾具後） | 同上／2026-09-24 |

三個失敗逐一處理：

1. **B-1（blocking，實作缺陷）**：`detect` 的增量最大值／最小值迴圈寫錯——初始視窗 `[shortest_start..j]` 只累加了第一根就往左擴張，**漏算視窗右半邊的 K 線**，使 `band` 被低估，不合格的區間看起來合格。症狀是「深度過大」與「回歸逾時」兩個反例仍各自出現額外命中（例如 `range=[51,55]` 的 `band` 被算成 1.5，實際為 2.4）。
   **修正**：先用 `np.max`／`np.min` 完整建立最短視窗的極值，再逐格往左擴張。修正後兩個反例如預期零命中，且 Cycle 2 的植入結構索引不變。
2. **夾具問題（非實作缺陷）**：「回歸前出現更低低點」的反例仍剩一筆命中，但那是**另一個合法結構**——把原跌破根吸收進盤整區間（`range=[31,50]`）後再被下一根跌破，深度 0.2273 ≥ 0.2。這使該反例無法只由反例防護決定。**修正夾具**：把中間那根的 low 由 96.0 壓到 88.0，讓次要結構的深度 `(97-88)/4.4 ≈ 2.05 > 1.5` 必然被排除；並在測試註解寫明理由。
3. **④ 反例防護尚未實作**（預期中的 Red）：加入「回歸之前（嚴格早於回歸根，即 `k+1..m-1`）若出現比 `low[k]` 更低的低點則該次跌破不成立」。

另補兩個對照組（`recovery_bars_max` 與 `breakdown_bars_max` 的「恰好落在期限」必須命中），避免把 `<=` 寫成 `<`。

## Cycle 4：尺度不變性（AC-019，既有覆蓋）

- 測試：三種乘常數（0.01／0.5／1000）與三種平移（+7／+1000／+100000）後，四個相位索引完全相同；`band` 隨乘常數縮放、平移不變；`breakdown_depth` 與 `confidence` 不變。
- 結果：**首次執行即通過（既有覆蓋）**。原因是偵測條件全部由比值構成（band／ATR、深度為 band 倍數、回歸比較為同視窗內的相對位置），尺度不變性是實作的直接後果，因此無法有真實 Red。如實記載，不捏造 Red。

## Cycle 5：去重與排序（AC-020，真實 Red → Green）

- 夾具：`build_two_structure_series()` 造出兩段結構（第一段盤整 20 根；第二段因前面深谷只能盤整 14 根）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `3 failed, 21 passed`：`len(events)` 為 3（含同一結構的多個長度） | 同上／2026-09-24 |
| Green | 同上 | 0 | `28 passed in 0.43s` | 同上／2026-09-24 |

- 實作 ⑥：以 `(breakdown_index, recovery_index)` 為去重鍵，保留盤整相位**最長**者；長度相同時保留盤整相位較晚結束者（區間緊鄰跌破），最後依長度降冪、起始索引升冪排序。
- 夾具自然產生「同一 `(k, m)` 由多個 `j` 命中」的情形（`j=48` 長度 19 與 `j=49` 長度 20），因此去重有真實的辨識對象。

## 邊界補強（兩處，皆由變異檢查反推）

1. **回歸「恰好等於」均值**：加入 `test_recovery_exactly_at_the_range_mean_is_accepted` 與略低於均值的對照組。過程中發現**浮點陷阱**：交錯 100.0／100.4 的區間均值是 `100.20000000000002`，無法用來測「恰好等於」；改用**平坦盤整**（close 全為 100.0，均值恰為 100.0）。
2. **跌破必須嚴格小於區間低點**：加入 `test_breakdown_requires_a_strictly_lower_low_even_when_zero_depth_is_allowed`。原因是預設規格 `depth_min = 0.2` 時「恰好等於」的深度為 0，會被深度檢查擋掉，使 `<` 與 `<=` 在預設規格下**無法區分**；把深度下限放寬到 0 之後才成為可觀測行為。

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | ATR 的 `previous_close` 誤用下一根收盤（lookahead） | 被抓到：`test_atr_with_period_one_equals_true_range`、`test_atr_does_not_look_ahead`、`test_confidence_matches_the_documented_formula_and_is_within_range` |
| M2 | 跌破判定改為 `<=` | **第一次未被抓到** → 查出是測試缺口（見上「邊界補強 2」）；補測試後**被抓到**：`test_breakdown_requires_a_strictly_lower_low_even_when_zero_depth_is_allowed` |
| M3 | 回歸判定改為 `>`（排除等於） | 被抓到：`test_recovery_exactly_at_the_range_mean_is_accepted`、`test_recovery_just_below_the_range_mean_is_not_a_recovery` |
| M4 | 移除「回歸前更低低點」防護 | 被抓到：`test_no_hit_when_a_lower_low_appears_before_the_recovery` |
| M5 | 去重改為保留最短 | 被抓到：`test_events_are_sorted_by_range_length_descending`、`test_one_structure_is_reported_once_with_the_longest_range` 等 |
| M6 | 最長區間掃描的 `break` 改為 `continue` | **未被抓到，經查為等價變異**：`band` 對起始索引單調不減，超限之後更長的視窗必然也超限，因此 `break` 只是最佳化，不影響結果 |

還原後 `ediaad/patterns.py` 雜湊 `5d5dc091c0ff2aa752fe9440c80c187cbbd610a5818977e0998a334982e4f066` 與變異前一致，全套 `150 passed`。

## 效能實測

`detect` 於 1,000 根 → **0.01 秒**、10,000 根 → **0.06 秒**（正弦合成資料、0 筆事件）；SPEC 第 6 節的門檻是 1,000 根 2 秒內，餘裕極大。這得益於「每個 `j` 由短往長掃描並在超限時立即停止」的 O(range_bars_max) 上界。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_patterns_detect.py -q` | 0（`28 passed`） | snap-2026-09-24-ocaievo-patterns-detect |
| 全套回歸（含 TASK-007 的 PatternSpec 契約） | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`150 passed in 1.26s`） | 同上 |
| 變異後還原驗證 | 同上 | 0（`150 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 已知語意取捨（皆有測試與註解）：「回歸之前」定義為**嚴格早於回歸根**（`k+1..m-1`）；回歸根本身的下影線不再檢查。這是本重建版的明確定義，報告未細分。
- 未涵蓋：`learn`（TASK-009）；與真實 `PatternEvent` 的 `outlook.forward_stats(..., end_attr="recovery_index")` 整合斷言（TASK-006 的 A-4 待辦，將在 TASK-009 之後或 TASK-037 補）。
