# TASK-015 Code Review

- task_id：TASK-015
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-twse-adjust-calendar sha256:c3d0aca4e8b4c5d17e8fbd36b893e247741cee52c01f9e25f39c88b7a4102f68
- Task／Spec 版本：TASK-015 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 M9／M22 的判讀與三處測試強化）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `c3d0aca4e8b4c5d17e8fbd36b893e247741cee52c01f9e25f39c88b7a4102f68`；本張新增 `ediaad/markets/adjust.py` `0e694cea…`、`ediaad/markets/calendar.py` `2eb5443a…`、`tests/test_markets_twse_adjust.py` `90817abb…`；修改 `ediaad/markets/base.py` `526d04ed…`、`ediaad/markets/twse.py` `7b58e675…`、`ediaad/markets/__init__.py` `8cc5a516…`、`tests/test_markets_twse.py` `51d90a2e…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的已提交、未提交、新增檔案：上述七個檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`patterns.py`（TASK-007／008 交付物）本張只**呼叫** `PatternSpec`／`NAMED_PATTERNS`／`detect`，未修改（雜湊未變）；`custom.py`／`crypto.py` 未修改
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-034／AC-035、第 5 節模組表（`ediaad/markets/adjust.py`、`ediaad/markets/calendar.py`）、第 6 節品質需求（可重現性：位元相同結果）、第 7 節測試策略與「必要的人工／視覺檢查」第 4 項、第 8 節 Q-012 與風險 5；`docs/workflow/adr/ADR-003.md`（方案 B 為主、A 為輔、C 保底）；`docs/architecture/ENGINEERING-REPORT.md` 第 7.4 節（除權息、交易日曆、市場別預設）與第 8.2 節第 4 點；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-034 | `ediaad/markets/adjust.py`；`tests/test_markets_twse_adjust.py` 40 個案例 | 符合 | A-3、A-5（advisory） |
| AC-035 | `ediaad/markets/calendar.py`；同檔 18 個案例 | 符合 | A-1、A-2、A-4（advisory） |

逐條核對：

- **AC-034「事件含除權息前收盤價、除權息參考價、權值+息值三個欄位」**：`ExRightsEvent` 的三個欄位都有斷言（34.20／33.20／1.000000），另帶 `kind`（來源的「權/息」欄，缺席時為空字串且有測試）。符合。
- **AC-034「還原後在除權息日不產生向下跌破命中」**：`test_detect_does_not_hit_the_adjusted_series` 斷言 `detect(adjusted, spec) == []`（完全零命中，不只是「該日沒有」）。符合。
- **AC-034「未還原序列會產生假命中（作為對照）」**：`test_detect_hits_the_unadjusted_series_on_the_ex_date` 斷言 `detect(raw, spec)` 非空，且**存在 `breakdown_index` 等於除權息日索引**的命中。兩者用同一份序列、同一個預設規格（`range_fakeout_reversion`）。符合。
- **AC-034「取得除權息事件」**：`TWT49U?startDate=&endDate=`，且測試斷言 URL **不含** `strDate`（ADR-003 記錄的誤導性參數）。符合。
- **AC-035「非交易日不會被當成連續 K 線」**：`apply_calendar` 過濾後有「每個時間戳都是交易日」的斷言；春節區間（2/16～2/19，回應中沒有各自的資料列）也被正確排除。符合。
- **AC-035「台股與加密貨幣使用不同的規律預設參數，且預設值可被設定覆寫」**：`MARKET_PATTERN_DEFAULTS` 有兩組且 `crypto` 與 `NAMED_PATTERNS` 逐欄相同（不改變既有行為）；`default_spec_for("stock", {...})` 的覆寫生效且未覆寫欄位維持市場別預設。符合。

## 品質 Review

- **AC-034 的驗證是「同一份序列的兩種處理」對照（本張最重要的品質決定）**：不是只驗還原後的數值，而是用 `detect` 這個**真正的下游消費者**觀察「未還原會誤判、還原後不會」。這讓測試直接對應 ADR-003 的驗證方式，也讓「還原公式寫錯」不可能同時通過兩邊（變異 M1／M2／M3 全部被抓到）。
- **夾具以實測校準而非推算**：`detect` 的跌破深度必須落在 `[0.2, 1.5]` 個 band 內，這與 ATR 耦合、手算容易出錯。我先寫校準腳本實際跑 `detect` 確認「未還原命中在索引 30、還原後零命中」，才把夾具寫進測試，並使用**預設規格**（不是為測試特調門檻）——測試驗的是產品預設行為。
- **「先判讀、再決定」處理存活變異（M9）**：M9 第一輪存活，追查後發現結果層面確實等價（遮罩彼此獨立），但我沒有就此結案——浮點乘法在最後一位不滿足交換律，而 SPEC 第 6 節要求「同一輸入與參數必須得到位元相同的結果」。原本的斷言用了 `pytest.approx` 與 `assert_frame_equal`（預設 `check_exact=False`），看不見 ULP 差異。改成 `list(a) == list(b)` 之後 M9 立刻被抓到，同時把「為什麼要排序」變成有測試支撐的事實。**這是本張最有價值的發現：一個看似裝飾的 `sorted()` 其實承載規格要求，而我原本的測試強度不足。**
- **資料完整性檢查（TWSE 附註的公式）**：逐列驗證 `權值+息值 = 除權息前收盤價 - 除權息參考價`（容忍 0.02 的進位）。若 TWSE 改表或我解析錯欄，會立刻失敗並指出該列，而不是靜默用錯誤的倍率還原整個序列（變異 M13 證明）。容忍度邊界兩側都有測試（0.01 通過／0.05 不通過）。
- **保底路徑（方案 A）具體可用**：無法還原的事件不改動序列，但把日期放進 `unavailable_dates`，讓呼叫端能標記該日不可用於規律判定；`status` 四態（`adjusted`／`partial`／`unavailable`／`unchanged`）各有測試。這比「靜默略過」或「整批失敗」都更符合 ADR-003 的方案 A／C 設計。
- **錯誤分層一致**：來源回應的解析失敗一律 `SourceError`（沿用 TASK-013／014 的決定）；呼叫端參數錯誤（結束日期早於開始日期、未知市場別、非法覆寫）一律 `ConfigError` 且**不發出請求**。
- **`parse_iso_day` 抽到 `markets/base`**：除權息區間與開休市日期都需要西元日期解析，兩個模組共用一個實作（避免 TASK-012 的 F-001 教訓再現）；民國年格式留在 `twse.parse_roc_date`（台灣特有）。`parse_roc_date` 只擴充了一個格式（年月日），既有格式與測試不受影響。
- **`load_twse_calendar` 不檢查 `stat`**：該端點的 `stat` 是小寫 `ok`（與 `STOCK_DAY` 的 `OK` 不同）。若照抄其他端點的檢查會**拒絕全部真實回應**——這是讀過實測存證才發現的細節（存證顯示 `stat: "ok"`）。
- **市場別預設的克制**：`stock` 只改三個欄位，其餘欄位與 `crypto` 逐欄相同且有斷言（包含 `pattern_id`、`atr_period`、`band_atr_multiple_max`）。這避免「兩份互不相干的規格」日後各自漂移。三個差異都以「日線的一根 ≈ 小時線的 24 倍」為理由，並在常數旁註解。
- **測試品質**：`apply_calendar` 同時斷言「過濾正確」「重新編號」「不改動輸入」「欄位不變」；日曆分類同時測「是休市」與「不是休市」（`開始交易日`／`最後交易日` 不能被誤判）。變異 M20（把所有日期都當休市）與 M18（完全不看休市清單）都被抓到，代表兩個方向都有守。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 缺口（沿用 TASK-013 A-1／TASK-014 A-3） | advisory（**需在後續 Task 處理**） | `default_spec_for`／`MARKET_PATTERN_DEFAULTS` 目前**沒有任何呼叫端**：`monitor.load_config` 仍用單一 `NAMED_PATTERNS`，不知道商品屬於哪個市場（`source_id` → 市場別的對應屬 catalog／settings）。`apply_calendar`／`fetch_ex_rights` 也沒有呼叫端 | 把「來源分派 ＋ 市場別預設 ＋ 日曆套用 ＋ 除權息還原」一起編入 TASK-025（或 TASK-037 整合項），並更新其「預計觸及的檔案」 | 待辦（已記於 `STATE.md` 待決事項） |
| A-2 | 日曆完整性 | advisory | `holidaySchedule` 只列出「值得公告」的日期：平日若不在清單中即視為交易日；連續假期靠說明文字的「N月N日至N月N日」展開，**跨年或反向區間**保守地只標記該列日期 | 若要更強的保證，需改為由「全部交易日」反推，或對跨年假期補規則並變更 Spec；目前已有測試固定現行語意 | 已實作並記錄（TDD 紀錄 Cycle 3） |
| A-3 | 真實資料風險 | advisory | 逐列驗證 TWSE 附註公式（容忍 0.02）；若真實 449 筆中有不符的列，整個 `fetch_ex_rights` 會失敗 | 建議在 TASK-037 以實測存證的那一個月做一次真實資料煙霧測試（需使用者同意連外）；若屆時發現不符的列，再決定改為「略過並回報」 | 待辦（TASK-037） |
| A-4 | 市場別預設的來源 | advisory | `stock` 的三個差異值（`range_bars_max` 60、`breakdown_bars_max` 3、`recovery_bars_max` 10）是依「日線一根 ≈ 小時線 24 倍」推導，**不是**校準過的數字 | TASK-023 的參數面板與 TASK-009 的 `learn` 可讓使用者實測調整；若日後有實測校準結果，需更新預設並記錄理由 | 延後（無實測依據可校準） |
| A-5 | 未測保證 | advisory | 除權息還原前後的**目視**核對（SPEC 第 7 節人工檢查第 4 項）由 TASK-022 的 K 線圖執行；本張只有程式斷言 | 維持 SPEC 的設計；TASK-022 完成後應在該張的人工檢查清單記錄結果 | 待辦（TASK-022） |
| A-6 | 流程紀律 | advisory（非程式） | Cycle 2 因 `adjust.py` 一次寫成而無真實 Red；另有一個測試命名／期望寫反（事件在最後一根之後）、一個變異字串寫成空操作（`series = series`）、一個對 `recovery_bars_max = 0` 的錯誤假設 | 已全部在 TDD 紀錄如實記載並修正；教訓：寫變異時必須確認「這個變異真的改變行為」 | **已記載**：TDD 紀錄 Cycle 2／Cycle 4 |

## 修正與重審

- 第 1 輪：Spec Review 兩個 AC 逐條符合；品質 Review 無 blocking。
- 依變異檢查強化測試 3 處（事件順序改位元級精確比較、`apply_calendar` 補索引與不改動輸入斷言、`stat` 訊息補欄位名），修正錯誤假設 1 處（`recovery_bars_max = 0` 是合法值）。
- 重審：重跑單檔（58 passed）、相關回歸（127 passed）與全套（411 passed）；重讀 `adjust.py`／`calendar.py` 複查還原方向、遮罩邊界、保底狀態、日曆分類與區間展開、市場別預設的差異範圍；變異矩陣在最終版檔案上 27／27 全數被抓到。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-034／AC-035 逐條符合，含 AC-034 的 `detect` 命中對照）
- 品質 Review：passed（無 blocking；A-1 需在後續 Task 落實，其餘為延後或已記錄的 advisory）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-025／037 的整合範圍）、A-2（需變更 Spec）、A-3（需連外同意）、A-4（無實測依據）、A-5（TASK-022）、A-6（流程記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：日曆完整度受限於 TWSE 說明文字；`apply_calendar` 以過濾實作；公式檢查會在真實資料不符時直接失敗；`default_spec_for`／`apply_calendar`／`fetch_ex_rights` 尚無呼叫端；人工目視核對由 TASK-022 執行
