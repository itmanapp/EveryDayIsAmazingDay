# TASK-009 測試紀錄

- task_id：TASK-009
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-patterns-learn sha256:d03c1cf328f8d9b6710be4f7b5593ec4fbb440155119f70c3877d94c70d7119a
- alternative_reason：無（Cycle 1 有真實 Red；Cycle 2 為既有覆蓋，見下並以變異檢查補強）
- Task／Spec 版本：TASK-009 / SPEC-001 v0.4
- 測試邊界：只呼叫 `ediaad.patterns.learn`，再把回傳的 `PatternSpec` 交給 `detect`／`to_json`／`atr` 觀察；不檢視門檻階梯或內部變數。合成範例由夾具產生，離線可跑。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-008 的交付物，全套 **150 passed**（本張完成後為 162 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用（整張以 pytest 在公開邊界驗證）。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 夾具設計（先推導，再寫斷言）

14 根範例：索引 0..11 為盤整區間（12 根；close 交錯 100.0／100.4、high=+1.0、low=−1.0
→ band 2.4、區間低點 99.0、均值 100.2），索引 12 跌破（low 97.0、close 98.5），
索引 13 回歸（close 100.5）。

由此可先推得預期推估值：盤整 12 根 → `range_bars_min=6`、`range_bars_max=18`；
深度 `2.0/2.4 = 0.8333` → 容差 `[0.5833, 1.0833]`；回歸 1 根 → `recovery_bars_max=3`；
`ATR(period)[range_end] = 2.0` → `band_atr_multiple_max = 2.4/2.0×1.2 = 1.44`。
這些都在 Cycle 1 的斷言中逐一驗證通過，代表「設計 → 實作」兩側一致。

## Cycle 1：推估結果可用、落在容差內、能命中範例自身（AC-021，真實 Red → Green）

- 測試：`test_learn_returns_a_pattern_spec`、`test_learned_spec_hits_its_own_sample`、`test_learned_spec_range_phase_covers_the_planted_range`、`test_learned_tolerances_follow_the_documented_formulas`、`test_learned_band_multiple_is_derived_from_the_measured_band_and_atr`、`test_learn_uses_an_atr_period_that_is_defined_at_the_range_end`、`test_learn_is_deterministic_for_the_same_sample`。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_patterns_learn.py -q` | 2 | `ImportError: cannot import name 'learn'` | 尚未有 `learn`／2026-09-24 |
| Green | 同上 | 0 | `7 passed in 0.31s` | snap-2026-09-24-ocaievo-patterns-learn／2026-09-24 |

- 最小實作：`learn(sample) -> PatternSpec`——`mtr`（真實區間的滾動中位數、窗 5）為尺；門檻階梯 `(1.0, 1.5, 2.0, 3.0, 4.0, 6.0)` 由嚴到鬆取第一個可行門檻並在其中取最長區間；跌破取區間後最低點；回歸取跌破（含）後第一根收盤回到均值；容差全部朝「更容易命中」放寬。
- **重構（避免第二套判定門檻）**：先把「以 `j` 結尾、`band <= limit` 的最長區間」抽成共用 helper `_longest_range_ending_at`，並改寫 `detect` 呼叫它。重構後先單獨重跑 `tests/test_patterns_detect.py` → **28 passed**，確認 TASK-008 的行為未變，才繼續實作 `learn`。

### 兩處規格未涵蓋而由本張決定的細節（已註解於程式）

1. **`atr_period`**：報告的容差清單未列出此欄位，但 `PatternSpec` 必須有值。若固定 14，短範例（如 12 根）在區間結束處的 ATR 會是 NaN，導致推估出的規格**無法命中自己的範例**（違反 AC-021）。因此取 `atr_period = max(1, min(14, range_end + 1))`，保證 ATR 在區間結束處有定義；長範例仍為 14。
2. **`breakdown_bars_max`**：同樣未在容差清單中。取範例實測的「盤整結束 → 跌破」間隔（至少 1），否則推估出的規格找不到自己的跌破相位。

兩者都有測試把關（`test_learn_uses_an_atr_period_that_is_defined_at_the_range_end`、`test_learned_spec_hits_its_own_sample`）。

## Cycle 2：無法推估時報錯（AC-021 的失敗面，既有覆蓋）

- 測試：`test_too_short_sample_is_rejected`（11 根）、`test_sample_without_a_phase_after_the_range_is_rejected`（全平坦）、`test_monotonic_rise_is_rejected_because_nothing_breaks_the_range_floor`、`test_sample_without_recovery_is_rejected`、`test_minimum_length_sample_with_a_complete_structure_is_learnable`（剛好 12 根）。
- 結果：**首次執行即通過（既有覆蓋）**。原因是這些守門與推估邏輯在同一次實作中完成——`learn` 若不檢查就必須回傳隨意參數，而那是 AC-021 明文禁止的。如實記載，不捏造 Red，並以下方變異檢查證明這些守門真的被測試鎖住。
- 邊界：剛好 12 根（10 根盤整 + 跌破 + 回歸）可推估，且推估出的規格能命中該 12 根範例。

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 移除最短長度檢查 | 被抓到：`test_too_short_sample_is_rejected` |
| M2 | 移除「跌破未低於區間下緣」檢查 | 被抓到：`test_monotonic_rise_is_rejected_because_nothing_breaks_the_range_floor` |
| M3 | 移除「找不到回歸」檢查 | **第一次未被抓到——查出是工具誤擊**（見下），改用含換行的精確字串後**被抓到**：`test_sample_without_recovery_is_rejected`（再現 `TypeError`） |
| M4 | `range_bars_max` 容差改為 0.9 倍（不足） | 被抓到 3 個測試，含 `test_learned_spec_range_phase_covers_the_planted_range`、`test_minimum_length_sample_with_a_complete_structure_is_learnable` |
| M5 | `atr_period` 固定 14（短範例無定義） | 被抓到 3 個測試，含 `test_learn_uses_an_atr_period_that_is_defined_at_the_range_end` |
| M6 | 深度容差上限反向緊縮（`depth × 0.5`） | 被抓到 3 個測試 |

**工具缺陷（第三次同類事件）**：M3 的替換字串 `"    if recovery_index is None:"`（4 空白縮排）**是 8 空白縮排版本的子字串**——`detect` 內的 `        if recovery_index is None:` 也包含它，因此 `replace(..., 1)` 改到 `detect` 的那一處（第 351 行）而非 `learn`（第 515 行），造成「未抓到」的錯誤結論。修正做法：替換字串**加入換行前綴**（`"\n    if recovery_index is None:"`）並以 `grep -n` 確認命中行號後才執行。前兩次同類事件分別是「未驗證變異是否套用」（TASK-004）與「誤擊 docstring」（TASK-005）。

還原後 `ediaad/patterns.py` 雜湊 `0e771abd764069214ac3f4293536105e91a88d512a577de37e12af4038c1c0b4` 與變異前一致，全套 `162 passed`。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_patterns_learn.py -q` | 0（`12 passed`） | snap-2026-09-24-ocaievo-patterns-learn |
| 規律相關回歸（規格＋偵測＋學習） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_patterns_spec.py tests/test_patterns_detect.py tests/test_patterns_learn.py -q` | 0（`75 passed`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`162 passed in 1.28s`） | 同上 |
| 變異後還原驗證 | 同上 | 0（`162 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 未涵蓋：網頁「學習」頁與 CSV 貼上／上傳（TASK-023，屆時以 `load_csv` 載入後呼叫本函式）；監控設定檔中的 `pattern_spec` 整合（TASK-010）。
- 已知限制（報告第 8.2 節第 7 項）：**單一範例學習可能過擬合**——容差圍繞那一段範例設計。本張以「容差朝更容易命中放寬」與「推估參數可由 `to_json` 檢視」降低風險，但不做交叉驗證；此限制將在交付報告揭露。
