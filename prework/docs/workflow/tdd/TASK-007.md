# TASK-007 測試紀錄

- task_id：TASK-007
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-patterns-spec sha256:8f6edeb7ddfb91c799b8c42a470657afaa1efee3eff4cb5695041faf179b1058
- alternative_reason：無（AC-014 與 AC-015 都有真實 Red→Green）
- Task／Spec 版本：TASK-007 / SPEC-001 v0.4
- 測試邊界：只透過 `ediaad.patterns` 的公開名稱建構 `PatternSpec`、呼叫 `to_json`／`from_json`、讀取 `NAMED_PATTERNS` 與 `RECOVERY_TARGETS`；不呼叫私有驗證函式，也不斷言 `__post_init__` 的實作細節。全部離線可跑。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-006 的交付物，全套 **87 passed**（本張完成後為 122 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## Cycle 1：規格模型、相對單位欄位與建構時驗證（AC-014，真實 Red → Green）

- AC 與預期行為：`PatternSpec` 為 frozen、十個欄位依 SPEC 第 5 節順序、全為相對單位；不合法（交叉條件、負值、濫用下限、未知 `recovery_target`、型別錯誤）在 `__post_init__` 即丟 `ConfigError`；`NAMED_PATTERNS` 收錄 `range_fakeout_reversion` 與其預設值。
- 測試檔案／案例：`tests/test_patterns_spec.py` 的 `test_named_patterns_contains_the_first_named_pattern_with_spec_defaults`、`test_spec_exposes_exactly_the_documented_relative_unit_fields`、`test_no_field_is_an_absolute_price`、`test_spec_is_frozen`、`test_equal_range_bounds_are_a_valid_boundary`、`test_zero_recovery_bars_is_valid`，以及 `test_invalid_specs_cannot_be_constructed` 的 20 個參數化案例。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_patterns_spec.py -q` | 2 | `E ModuleNotFoundError: No module named 'ediaad.patterns'`；`1 error in 0.10s` | 尚未有 `ediaad/patterns.py`／2026-09-24 |
| Green | 同上 | 0 | `26 passed in 0.03s` | snap-2026-09-24-ocaievo-patterns-spec／2026-09-24 |

- Red 確實因目標行為失敗的解釋：測試匯入尚不存在的模組；`.venv` 已於 TASK-001 驗證可用。
- 最小實作摘要：`ediaad/patterns.py` 的 `RECOVERY_TARGETS`、`NAMED_PATTERNS`、`PatternSpec`（frozen，`__post_init__` 十項驗證，含 `min <= max` 與深度下限／上限的交叉檢查）與兩個型別輔助函式（`_require_int` 明確排除 `bool`；`_require_number`）。
- 邊界取捨（刻意且可驗證）：`breakdown_bars_max` 下限為 **1**（`j < k <= j + breakdown_bars_max`，為 0 時不存在合法的 `k`，規格永遠不可能命中），而 `recovery_bars_max` 下限為 **0**（`k <= m <= k + 0` 合法：同一根同時跌破並收回均值之上）。兩者都有測試。

## Cycle 2：序列化契約（AC-015，真實 Red → Green）

- AC 與預期行為：`from_json(to_json(spec)) == spec`；`to_json` 鍵序穩定（`sort_keys=True`）且連續兩次輸出完全相同；`from_json` 對缺欄位、多欄位、型別不符、非法 JSON、非物件 JSON 各自 `ConfigError`，且**不以預設值補齊**。
- 測試檔案／案例：`test_json_round_trip_is_lossless`、`test_to_json_is_stable_and_uses_sorted_keys`、`test_from_json_accepts_both_text_and_mapping`、`test_from_json_rejects_a_missing_field_without_filling_defaults`、`test_from_json_rejects_a_partial_payload`、`test_from_json_rejects_an_unknown_extra_field`、`test_from_json_rejects_wrong_types`、`test_from_json_rejects_invalid_json_text`、`test_from_json_rejects_non_object_json`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_patterns_spec.py -q` | 1 | `6 failed, 29 passed`：鍵序未排序（宣告順序 ≠ 字母序）；缺欄位／部分欄位／多欄位丟 `TypeError` 而非 `ConfigError`；非法 JSON 丟 `json.JSONDecodeError`；`[1, 2, 3]` 丟 `TypeError` | 同上／2026-09-24 |
| Green | 同上 | 0 | `35 passed in 0.04s` | 同上／2026-09-24 |

- Red 確實因目標行為失敗的解釋：Cycle 1 只實作「能 round-trip 的最小版本」（`json.dumps(asdict(spec))` 與 `PatternSpec(**data)`），刻意不滿足 AC-015 的嚴格契約，因此六個失敗全部是「嚴格契約尚未實作」的直接後果，不是拼字或工具問題。
- 最小實作摘要：`to_json` 加 `sort_keys=True`（並 `ensure_ascii=False` 讓中文可讀）；`from_json` 改為嚴格還原——`JSONDecodeError` → `ConfigError`、非 Mapping → `ConfigError`、以 `dataclasses.fields` 導出的欄位集合檢查缺欄位與未知欄位（訊息列出欄位名），最後才建構。

## 變異檢查（證明測試有辨識力）

刻意植入缺陷 → 確認對應測試失敗 → 還原並比對 sha256；替換字串一律使用完整縮排的整行。

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 移除 `range_bars_min <= range_bars_max` 交叉檢查 | 被抓到：`test_invalid_specs_cannot_be_constructed[min 大於 max]` |
| M2 | `to_json` 移除 `sort_keys=True` | 被抓到：`test_to_json_is_stable_and_uses_sorted_keys` |
| M3 | 移除未知欄位檢查 | 被抓到：`test_from_json_rejects_an_unknown_extra_field`（再現 `TypeError`） |
| M4 | 移除缺欄位檢查 | 被抓到：`test_from_json_rejects_a_missing_field_without_filling_defaults`、`..._a_partial_payload`（再現 `TypeError`） |
| M5 | `_require_int` 不再排除 `bool` | 被抓到：`test_invalid_specs_cannot_be_constructed[int 欄位給 bool]` |
| M6 | 移除 `recovery_target` 檢查 | 被抓到：兩個參數化案例（未知目標、非字串） |

還原後 `ediaad/patterns.py` 雜湊與變異前一致，全套 `122 passed`。

## Review 後修正（第 1 輪內）

品質 Review 發現 `band_atr_multiple_max` 同時用了 `_require_number(..., minimum=0)` 與顯式的 `<= 0` 檢查，前者是多餘的（0 會被後者擋下）。已移除 `minimum=0` 參數，行為不變；重跑全套 `122 passed`，並以修正後的檔案重新計算 `checked_version`（本紀錄與 review 記錄指向同一雜湊）。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit code | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_patterns_spec.py -q` | 0（`35 passed in 0.03s`） | snap-2026-09-24-ocaievo-patterns-spec |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`122 passed in 1.18s`） | 同上 |
| 變異後還原驗證 | 同上 | 0（`122 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 後續擴充的既有契約：`ediaad/patterns.py` 由 TASK-008（`atr`／`detect`／`PatternEvent`）與 TASK-009（`learn`）在同一檔案擴充；本張已建立 `RECOVERY_TARGETS`、`NAMED_PATTERNS`、`PatternSpec` 三個不得破壞的契約。`detect` 的 AC-016～AC-020 會需要 `PatternEvent`，屆時不得改動本張欄位。
- 未涵蓋：`recovery_target` 的其他候選值（目前只有 `range_mean`，SPEC 明列不得新增）；規格與監控設定檔的整合驗證（TASK-010 的 `load_config`）。
