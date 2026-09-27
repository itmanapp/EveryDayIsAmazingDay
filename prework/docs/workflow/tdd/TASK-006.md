# TASK-006 測試紀錄

- task_id：TASK-006
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-outlook sha256:1f053e86d43c06c5f18e2e96251708c5bf4823d5d75b3bafa336bb2a366fac44
- alternative_reason：無（AC-012 與 AC-013 都有真實 Red→Green）
- Task／Spec 版本：TASK-006 / SPEC-001 v0.4
- 測試邊界：只呼叫 `ediaad.outlook.forward_stats` 並觀察 `OutlookStats` 五個欄位；片段以測試替身（同時具備 `end_index` 與 `recovery_index`）提供；不檢視內部彙總方式。合成序列與手算報酬，離線可跑。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-005 的交付物，全套 **74 passed**（本張完成後為 87 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## Cycle 1：後續走勢統計與邊界（AC-012，真實 Red → Green）

- AC 與預期行為：`samples`、`up_probability`、`mean_return`、`median_return`、母體標準差（`ddof=0`）與手算相符；`end + horizon >= 長度` 者排除；報酬恰為 0 不算上漲；無樣本時除 `samples` 外皆為 `None`。
- oracle 的來源：期望值以標準庫 `statistics`（`mean`／`median`／`pstdev`）獨立計算，不使用待測模組；推導寫在測試註解旁（例：`returns = [105/100-1, 120/120-1, 90/120-1, 125/90-1, 150/125-1]`）。
- 測試檔案／案例：`tests/test_outlook.py` 的 `test_two_fragments_with_known_returns`、`test_statistics_match_independently_derived_values`、`test_std_return_uses_population_standard_deviation`、`test_fragment_is_kept_when_end_plus_horizon_is_last_index`、`test_zero_return_counts_as_sample_but_not_as_up`、`test_empty_fragment_list_returns_zero_samples_and_none_fields`、`test_all_fragments_excluded_by_horizon_returns_none_fields`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_outlook.py -q` | 2 | `E ModuleNotFoundError: No module named 'ediaad.outlook'`；`1 error in 0.42s` | 尚未有 `ediaad/outlook.py`／2026-09-24 |
| Green | 同上 | 0 | `7 passed in 0.30s` | snap-2026-09-24-ocaievo-outlook／2026-09-24 |

- Red 確實因目標行為失敗的解釋：測試匯入尚不存在的模組；`.venv` 已在 TASK-001 驗證可用。
- 最小實作摘要：`ediaad/outlook.py` 的 `OutlookStats`、`HasEndIndex`（`Protocol`，描述「有結束索引欄位」的物件，避免匯入 `scan`／`patterns`）與 `forward_stats`（尾端排除、`up_probability` 用嚴格大於、`numpy.std` 預設 `ddof=0`、空樣本回 `None`）。
- 邊界的成對斷言：`end == len - 1 - horizon`（= 7）必須保留、`end == len - horizon`（= 8）必須排除，兩者同時斷言，避免只測單側而讓 `<` 與 `<=` 的錯誤寫法矇混過關。

## Cycle 2：雙路線共用介面（AC-013）與兩項錯誤契約（真實 Red → Green）

- AC 與預期行為：`end_attr` 未指定時用 `end_index`；指定 `recovery_index` 時對具該欄位的物件得到正確結果；兩條路線共用同一函式。
- 測試檔案／案例：`test_default_end_attribute_is_end_index`、`test_end_attr_selects_the_recovery_index`、`test_both_routes_share_the_same_function_and_agree`、`test_missing_end_attribute_reports_config_error_instead_of_attribute_error`、`test_zero_base_price_reports_config_error`、`test_non_finite_base_price_reports_config_error`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_outlook.py -q` | 1 | `3 failed, 10 passed, 2 warnings`：缺欄位時丟 `AttributeError`（正是 F-002 的失敗模式）；零基準價時**未報錯**且出現 `RuntimeWarning: invalid value encountered in subtract`（統計被 NaN 污染）；NaN 基準價同樣未報錯 | 同上／2026-09-24 |
| Green | 同上 | 0 | `13 passed in 0.32s` | 同上／2026-09-24 |

- Red 確實因目標行為失敗的解釋：三個失敗都是「守門尚未實作」的直接後果。其中零基準價的 `RuntimeWarning` 尤其重要——它證明若不擋，統計結果會被 NaN 污染而不會報錯（違反 SPEC 第 6 節可靠性與專案「退化情境不得產生 NaN」的一貫原則）。
- **既有覆蓋（如實記載）**：`end_attr` 的三個選擇性測試首次執行即通過。原因是 `forward_stats` 的簽名在第一個 Cycle 就必須有 `end_attr="end_index"`，因此「以參數指名欄位」的機制隨 Cycle 1 一併實作；Cycle 2 的測試把契約鎖住，但不宣稱有 Red。
- 最小實作摘要：新增 `_end_index`（缺欄位 → `ConfigError`，訊息同時指出 `end_index` 與 `recovery_index` 的用途）與基準價格守門（`close[end]` 非有限或為 0 → `ConfigError`）。

## 變異檢查（證明測試有辨識力）

刻意植入缺陷 → 確認對應測試失敗 → 還原並比對 sha256。替換字串一律使用**完整縮排的整行**（TASK-005 的教訓：短字串會誤擊 docstring）。

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 上漲判定改為 `>= 0`（0 也算上漲） | 被抓到：`test_statistics_match_independently_derived_values`、`test_zero_return_counts_as_sample_but_not_as_up` |
| M2 | 標準差改用 `ddof=1` | 被抓到：`test_statistics_match_independently_derived_values`、`test_std_return_uses_population_standard_deviation` |
| M3 | 尾端排除條件改為 `>`（會越界） | 被抓到 4 個測試，含**成對邊界**測試與兩個 `None` 欄位測試 |
| M4 | 預設 `end_attr` 改為 `recovery_index` | 被抓到 5 個測試，含 F-002 回歸測試 |
| M5 | 移除缺欄位檢查 | 被抓到：`test_missing_end_attribute_reports_config_error_instead_of_attribute_error`（再現 `AttributeError`） |

還原後 `ediaad/outlook.py` 雜湊 `afa7497019def510ef6c4dcd8aa8609925c529b022653a649579dd5dc6c424f7` 與變異前一致，全套 `87 passed`。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit code | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_outlook.py -q` | 0（`13 passed`） | snap-2026-09-24-ocaievo-outlook |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`87 passed in 1.17s`） | 同上 |
| 變異後還原驗證 | 同上 | 0（`87 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 真實整合待補：`PatternEvent`（TASK-008）尚未存在，因此「`PatternEvent` 經 `end_attr="recovery_index"` 走同一函式」目前以測試替身驗證。TASK-008 完成後應以真實 `PatternEvent` 補一次整合斷言（已記於 TASK-006 的測試計畫）。這是**已知的未完成整合**，不是通過。
- 未涵蓋：片段之間的相關性處理（報告第 5.8 節已揭露的統計偏誤，本版只揭露樣本數）；`horizon` 的合法性檢查（由呼叫端負責）。
