# TASK-009 Code Review

- task_id：TASK-009
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-patterns-learn sha256:d03c1cf328f8d9b6710be4f7b5593ec4fbb440155119f70c3877d94c70d7119a
- Task／Spec 版本：TASK-009 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `d03c1cf328f8d9b6710be4f7b5593ec4fbb440155119f70c3877d94c70d7119a`；本張交付的兩個檔案——`ediaad/patterns.py` `0e771abd764069214ac3f4293536105e91a88d512a577de37e12af4038c1c0b4`、`tests/test_patterns_learn.py` `327ed652d9364ec0c0654793e52878c6b97708221d79df31b4718d1c63a3dff1`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對。本張改動範圍：`ediaad/patterns.py`（新增常數、`_rolling_median_true_range`、`_longest_range_ending_at`、`learn`；**重構** `detect` 改用共用 helper）＋ 新增 `tests/test_patterns_learn.py`
- 納入的已提交、未提交、新增檔案：`ediaad/patterns.py`（本張新增與重構部分）、`tests/test_patterns_learn.py`＋ 本張 TDD／Review 紀錄
- 排除的既有修改及理由：`PatternSpec`／`to_json`／`from_json`（TASK-007）與 `atr`／`PatternEvent`（TASK-008）的**行為**未變；`detect` 僅重構、語意不變（以 TASK-008 的 28 個測試確認）
- 程式規範來源：`docs/workflow/SPEC.md` 第 5 節（`patterns.py` 責任與依賴方向、原則 1）、AC-021、報告第 5.7 節（學習演算法七步與容差公式）、第 8.2 節第 7 項（單一範例過擬合）、`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-021 | `ediaad/patterns.py`（`learn`、`_rolling_median_true_range`、`_longest_range_ending_at`）；`tests/test_patterns_learn.py` 的 12 個案例 | 符合 | — |

逐條核對：

- **推估結果落在容差內**：`range_bars_min == round(12×0.5) == 6`、`range_bars_max == round(12×1.5) == 18`、`recovery_bars_max == 1 + 2 == 3`、`breakdown_depth_band_min == max(0.05, 0.8333×0.7) == 0.5833`、`breakdown_depth_band_max == min(3.0, 0.8333×1.3) == 1.0833`、`band_atr_multiple_max == clip(2.4/2.0×1.2) == 1.44`，全部與手算一致；`clip` 邊界（1.0～6.0）亦有斷言。
- **用該規格 `detect` 能命中自己的範例**：`detect(sample, learn(sample))` 非空，且事件的 `breakdown_index`／`recovery_index` 等於植入位置；盤整區間覆蓋植入的盤整相位。
- **無法推估時丟出 `ConfigError` 且不回傳隨意參數**：四種失敗情境（過短、區間後無 K 線、未跌破區間下緣、未回到均值）都丟 `ConfigError` 並在訊息指出原因；`pytest.raises` 確保沒有任何 `PatternSpec` 被回傳。
- **同一範例重跑結果完全相同**：`to_json(learn(sample))` 兩次完全相同（無隨機、無搜尋）。符合。

## 品質 Review

- **正確性（對照報告第 5.7 節七步）**：滾動中位數真實區間為尺 → 門檻階梯由嚴到鬆 → 在首個可行門檻取最長區間 → 跌破取區間後最低點 → 回歸取第一根收盤回到均值 → 容差放寬。逐步有測試。未發現不符。
- **「不得複製出第二套判定門檻」**：把「以 `j` 結尾、`band <= limit`、長度介於上下限的最長區間」抽成 `_longest_range_ending_at`，`detect` 與 `learn` **共用**同一個搜尋（差別只在 `limit` 的來源：`detect` 用 `band_atr_multiple_max × ATR[j]`，`learn` 用 `mtr × 階梯倍數`）。重構後先重跑 TASK-008 的測試確認行為不變，才繼續。符合 TASK-009 的約束。
- **兩處規格未涵蓋的欄位（已在程式註解與 TDD 紀錄說明）**：
  1. `atr_period = max(1, min(14, range_end + 1))`——若固定 14，短範例（12 根）在區間結束處的 ATR 會是 NaN，推估出的規格將**無法命中自己的範例**，直接違反 AC-021。此選擇讓長範例仍用 14、短範例自動縮短。
  2. `breakdown_bars_max = max(1, breakdown_index - range_end)`——取樣本實測的「盤整結束 → 跌破」間隔，否則規格找不到自己的跌破相位。
  這兩項是**必要的補充決定**，非任意放寬；若使用者認為應改為固定值，需一併檢視 AC-021 的可達性。
- **錯誤處理與錯誤契約**：所有失敗都是 `ConfigError`（exit 2），訊息含具體原因（根數、區間後無 K 線、未低於下緣、未回到均值）；未外洩 `TypeError`（變異 M3 的 `None - int` 正是被測試擋下的情形）。
- **確定性與可重現性**：無隨機、無時間依賴、無檔案；同一輸入的輸出完全一致（`to_json` 字串比較）。符合 SPEC 第 6 節。
- **模組責任與依賴**：只使用 numpy／pandas 與 `ediaad.errors`；不讀寫檔案、不連網、不輸出訊息。符合 SPEC 第 5 節原則 1。
- **測試品質**：夾具的預期推估值在寫斷言前先以設計推導（見 TDD 紀錄的夾具設計），實作後逐項吻合；含最短長度邊界（12 根）、四種失敗情境、容差公式與可重現性。變異 M1～M6 全部被抓到（M3 首次為工具誤擊，修正後成立）。未發現問題。
- **命名與可讀性**：`_rolling_median_true_range` 的 docstring 引用報告說明「為何用中位數而非平均」；`learn` 的 docstring 列出四步與「絕不回傳隨意參數」的保證；兩處自行決定的欄位都有行內註解說明理由。
- **過擬合風險**：單一範例學習的容差圍繞該範例設計（報告第 8.2 節已列為已知限制）。本張不新增交叉驗證，但容差一律朝「更容易命中」放寬，且推估參數可由 `to_json` 檢視與調整；此限制將在交付報告揭露。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 規格補充 | advisory（必要決定） | 報告的容差清單未涵蓋 `atr_period` 與 `breakdown_bars_max`，但 `PatternSpec` 必須有值；若取固定值（14／2），推估出的規格可能無法命中自己的範例 | 已取「保證可命中」的推導值並註解理由；若要改固定值需重審 AC-021 | 已實作並有測試（`test_learn_uses_an_atr_period_that_is_defined_at_the_range_end`、`test_learned_spec_hits_its_own_sample`） |
| A-2 | 過擬合 | advisory（已知限制） | 單一範例學習的容差圍繞該範例設計 | 報告第 8.2 節已列為已知限制；交付報告需再揭露 | 已記錄（將列入 DELIVERY） |
| A-3 | 參數名稱 | advisory | `MTR_WINDOW = 5` 與 `LEARN_MIN_RANGE_BARS = 5` 為本實作選定的常數，報告未指定 | 已集中為模組常數並註解；若日後要調參只需改一處 | 已處理 |
| A-4 | 效能 | advisory | `learn` 對每個門檻對每個 `j` 做一次線性掃描（樣本通常很短，影響可忽略） | 樣本長度為使用者貼上的一段走勢，非長序列 | 延後（無壓力） |
| P-1 | 流程工具 | advisory（流程） | 變異檢查的替換字串 `"    if recovery_index is None:"` 是 8 空白縮排版本的子字串，誤擊 `detect` 而非 `learn`，產生「未抓到」的錯誤結論（同類事件第三次） | 替換字串加入換行前綴並以 `grep -n` 確認命中行號 | 已修正並重測（M3 確實被抓到）；已記入 TDD 紀錄 |

## 修正與重審

- 第 1 輪：Spec Review 符合；品質 Review 未發現 blocking；A-1～A-4 為設計補充與已知限制，皆已文件化；P-1 為流程工具缺陷，已修正。
- 重審範圍：確認 `detect` 重構後行為不變（`tests/test_patterns_detect.py` 28 passed）；重跑規律相關回歸（規格＋偵測＋學習 75 passed）與全套（162 passed）；重讀 `learn` 複查門檻階梯的選擇、最長區間的 tie-break、跌破／回歸的邊界與容差公式。

## 結果

- Spec Review：passed（AC-021 四項要求逐條符合；容差公式與手算一致）
- 品質 Review：passed（未發現 blocking；共用搜尋、錯誤契約、確定性、測試品質皆已檢查）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-2（過擬合為報告已揭露的限制，交付報告再列）、A-4（無效能壓力）
- 能否標為 done：**可以**
- 限制與未驗證事項：單一範例學習可能過擬合；`MTR_WINDOW` 與 `LEARN_MIN_RANGE_BARS` 為本實作選定值；與網頁學習頁的整合待 TASK-023
