# TASK-015 測試紀錄

- task_id：TASK-015
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-twse-adjust-calendar sha256:c3d0aca4e8b4c5d17e8fbd36b893e247741cee52c01f9e25f39c88b7a4102f68
- alternative_reason：無（除權息還原與日曆皆可用合成序列與假 HTTP 回應完整驗證；SPEC 第 7 節的人工目視檢查由 TASK-022 的 K 線圖一併執行）
- Task／Spec 版本：TASK-015 / SPEC-001 v0.4
- 測試邊界：`fetch_ex_rights`／`adjust_series`／`load_twse_calendar`／`TradingCalendar.is_trading_day`／`apply_calendar`／`default_spec_for` 的公開結果，以及 **AC-034 要求的 `patterns.detect` 命中差異**；`build_series` 一律經 `data.from_rows` 建立契約序列。假回應欄位名照實測存證建立，但不讀取該檔。全程離線。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-014 的交付物，全套 **353 passed**（本張完成後為 411 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/markets/adjust.py` | `0e694cea` | 新增：`EX_RIGHTS_URL`、`ExRightsEvent`、`AdjustResult`、`fetch_ex_rights`、`adjust_series` |
| `ediaad/markets/calendar.py` | `2eb5443a` | 新增：`TradingCalendar`、`is_trading_day`、`load_twse_calendar`、`apply_calendar`、`MARKET_PATTERN_DEFAULTS`、`default_spec_for` |
| `tests/test_markets_twse_adjust.py` | `90817abb` | 新增：58 個測試 |

## 本張修改的既有檔案（含理由）

| 檔案 | sha256（前 8 碼） | 修改內容與理由 |
| --- | --- | --- |
| `ediaad/markets/base.py` | `526d04ed` | 新增 `parse_iso_day`（西元日期解析）。除權息區間與開休市日期都需要它，兩個模組共用同一個實作；民國年格式仍留在 `twse.parse_roc_date`（台灣特有） |
| `ediaad/markets/twse.py` | `7b58e675` | `parse_roc_date` 增加「`113年07月01日`」格式（除權息表的日期格式），並在 `test_markets_twse.py` 補對應案例 |
| `ediaad/markets/__init__.py` | `8cc5a516` | 匯出新模組 `adjust`／`calendar` |
| `tests/test_markets_twse.py` | `51d90a2e` | 補 `parse_roc_date` 的年月日案例（TASK-014 交付物的擴充測試） |

## Cycle 1：除權息事件、還原與 `detect` 對照（AC-034 核心，真實 Red → Green）

- 測試：`fetch_ex_rights` 解析出三個必要欄位（34.20／33.20／1.000000）＋`kind`；請求 URL 用 `startDate`／`endDate` 且**不含** `strDate`；`adjust_series` 讓事件日與前一根的收盤差小於 `1e-9`；**未還原序列被 `detect` 判定為跌破假命中（`breakdown_index` 等於除權息日索引）**；**還原後 `detect` 完全不命中**；`adjust_series` 不改動輸入；事件早於每根 K 線時不動序列；事件晚於每根 K 線時整條縮放；沒有事件時狀態為 `unchanged`，共 9 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_markets_twse_adjust.py -q` | 1 | `8 failed`：`ModuleNotFoundError: No module named 'ediaad.markets.adjust'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `9 passed in 0.37s` | snap-2026-09-24-ocaievo-twse-adjust-calendar／2026-09-24 |

- 實作：`ExRightsEvent`（frozen，含 `factor` 屬性並在非正前收盤價時丟 `DataFormatError`）、`AdjustResult`、`fetch_ex_rights`（`TWT49U?startDate=&endDate=`；`stat` 檢核；中文欄名定位；**逐列驗證 TWSE 附註的「權值+息值 = 除權息前收盤價 - 除權息參考價」**，容忍 0.02 的進位；`symbol` 篩選；依（日期, 代號）排序）、`adjust_series`（事件日**之前**的價格乘上參考價／前收盤價；事件日與之後不動）。
- **夾具以實測校準**：`detect` 的跌破深度必須落在 `[0.2, 1.5]` 個 band 內，因此我沒有憑推算湊數字，而是先寫校準腳本實際跑 `detect`，確認「未還原命中在索引 30（除權息日）、還原後 0 命中」之後才把夾具寫進測試。夾具用預設 `range_fakeout_reversion` 規格（不是為測試特調的門檻）。
- **如實記載的測試錯誤**：`test_an_event_after_every_bar_leaves_the_series_unchanged` 的命名與期望都錯了——事件若在**所有 K 線之後**，每一根都在事件之前，因此**全部都要縮放**（`applied == 1`）才正確。真正「不動」的情境是事件在**第一根之前**。已把該測試改成「事件在第一根之前」，並補上互補的「事件在最後一根之後 → 整條縮放」。

## Cycle 2：多次事件、無法還原的事件與錯誤路徑（**既有覆蓋**，無真實 Red）

- 測試：兩次事件疊加（事件之前的價格乘兩個倍率、只在前一次事件之前的乘一個）；事件順序不影響位元結果；前收盤價非正數 → 記入 `unavailable_dates` 且序列不動（方案 A）；可還原與不可還原混合 → `partial`；缺「權/息」欄仍可解析；查無事件（含 TWSE 的「沒有符合條件的資料」）回空清單；`symbol` 篩選與（日期, 代號）排序；結束日期早於開始日期 → `ConfigError` 且**不發出請求**；七種壞回應 → 可讀 `SourceError`；公式不符 → `SourceError`；容忍度邊界（0.01 通過／0.05 不通過）；三種客戶端例外；五種非法日期參數，共 31 個（其中 18 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | — | — | **未取得**（見下） | — |
| Green | 同上 | 0 | `40 passed in 0.48s` | 同上／2026-09-24 |

- **如實記載的流程偏差**：`adjust.py` 在 Cycle 1 就一次寫成完整模組（AC-034 的核心對照需要整條管線才能觀察），因此 Cycle 2 的測試首次執行即通過，**沒有真實 Red**。補救方式與 TASK-013／TASK-011 相同：以**整檔 Red**（見下）與**變異檢查 27／27 全數擊殺**替代辨識力證據。
- **Cycle 2 修正的兩處實作／測試落差**：
  1. `stat` 非 OK 的錯誤訊息原本寫「狀態不是 OK」，測試以欄位名 `stat` 比對而失敗 → 訊息改為「…的 `stat` 不是 OK」，同時保留可讀性與欄位名。
  2. `parse_iso_day` **刻意接受** `2024/07/01`（與 `-` 同義的無歧義西元格式），因此「斜線日期應被拒絕」的測試期望是錯的。已改用真正非法的 `2024-13-45`，並補一個測試明確記錄「`2024-07-01`／`20240701`／`2024/07/01`／`date`／`datetime` 都接受」。

## Cycle 3：交易日曆與市場別預設（AC-035，真實 Red → Green）

- 測試：`load_twse_calendar` 的分類（`放假`／`無交易` 為休市、`開始交易日`／`最後交易日` 不是）；**春節區間展開**（說明寫成「2月15日至2月19日放假5日」，2/16～2/19 在回應中沒有各自的資料列，仍必須全部休市）；`is_trading_day` 排除週末與假日；模組層 `is_trading_day` 與方法一致；`apply_calendar` 只留交易日且每個時間戳都是交易日、回傳重新編號的新物件、不改動輸入；六種壞 payload；市場別預設（crypto 沿用既有、stock 只在三個欄位不同）；`default_spec_for` 回傳 `PatternSpec`、覆寫生效且未覆寫者維持市場別預設、未知市場別與非法覆寫各自 `ConfigError`，共 17 個（其中 6 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `16 failed`：`ModuleNotFoundError: No module named 'ediaad.markets.calendar'` | 同上／2026-09-24 |
| Green | 同上 | 0 | `57 passed in 0.47s` | 同上／2026-09-24 |

- 實作：`TradingCalendar`（休市日集合＋`year`；`is_trading_day` = 週一至週五且不在集合內）、`is_trading_day(calendar, day)` 模組層包裝（SPEC 第 5 節同時列出兩者）、`load_twse_calendar`（**不檢查 `stat`**，因為該端點的 `stat` 是小寫 `ok`，與其他端點不同）、`apply_calendar`、`MARKET_PATTERN_DEFAULTS`、`default_spec_for`。
- **春節區間展開是必要的正確性修正**：`holidaySchedule` 只列出「值得公告的日期」，連續假期只有一列、範圍寫在說明文字裡。若只用該列自己的日期，2/16～2/19 會被當成交易日。實作以 `N月N日至N月N日` 解析並展開，跨年或反向區間保守地只標記該列日期（已於 Review 列為 advisory）。
- **市場別預設的定義與理由**：`crypto` **完全沿用** `NAMED_PATTERNS["range_fakeout_reversion"]`（不改變既有行為，有斷言）；`stock` 只改三個欄位——`recovery_bars_max` 5 → 10、`breakdown_bars_max` 2 → 3（日線的回歸與跌破以「天」計）、`range_bars_max` 120 → 60（盤整上限從半年縮到一季）。其餘欄位與 crypto 相同且有斷言，避免「市場別預設」變成兩份互不相干的規格。
- **如實記載的測試錯誤**：我原先假設 `recovery_bars_max = 0` 是非法覆寫，但 TASK-007 的驗證下限是 **0**，且 `_confidence` 有 `recovery_bars_max == 0` 的專門分支（回歸必須在跌破當根完成）。**是我的假設錯、實作對**；已改用 `atr_period = 0` 與 `recovery_bars_max = -1` 作為非法案例，並補一個測試記錄「0 是合法值」。

## Cycle 4（補測）：把等效變異變成可偵測

- 首次變異檢查有 2 個存活者，其中一個是**我寫壞的變異**、另一個經追查是**等效變異**（詳見下節）。處理方式是**強化測試而非放寬標準**：
  1. 事件順序測試改為**位元級精確比較**：浮點乘法不滿足交換律到最後一位（`100.5×0.9×0.8 = 72.36`、`100.5×0.8×0.9 = 72.36000000000001`），因此「先依日期排序再套用」是 SPEC「同一輸入必須得到位元相同的結果」的**實際承載者**，不是裝飾。
  2. `apply_calendar` 補「回傳序列必須重新編號」與「不得在輸入序列上加欄位」兩個斷言。
- 測試數 57 → 58（另含先前修正）。

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 還原倍率取倒數 | 被抓到 |
| M2 | 改成事件日**之後**才縮放 | 被抓到 |
| M3 | 事件日當天也縮放 | 被抓到 |
| M4 | 只縮放收盤價 | 被抓到 |
| M5 | 直接改動輸入序列 | 被抓到 |
| M6 | 無法還原時不標記日期 | 被抓到 |
| M7 | 無法還原仍計入 `applied` | 被抓到 |
| M8 | 狀態一律 `adjusted` | 被抓到 |
| M9 | 事件未依日期排序 | **首次存活 → 補位元級斷言後被抓到**（見下） |
| M10 | 事件不排序回傳 | 被抓到 |
| M11 | 不檢查 `stat` | 被抓到 |
| M12 | 空資料當成錯誤 | 被抓到 |
| M13 | 不檢查權值+息值公式 | 被抓到 |
| M14 | 不檢查日期順序 | 被抓到 |
| M15 | 缺必要欄位不報錯 | 被抓到 |
| M16 | `symbol` 篩選不正規化 | 被抓到 |
| M17 | 週末算交易日 | 被抓到 |
| M18 | 不看休市清單 | 被抓到 |
| M19 | 不展開連續假期區間 | 被抓到 |
| M20 | 所有日期都當休市 | 被抓到 |
| M21 | `apply_calendar` 不過濾 | 被抓到 |
| M22a | `apply_calendar` 不重新編號 | **首次存活 → 補索引斷言後被抓到** |
| M22b | `apply_calendar` 在輸入上加欄位 | 被抓到 |
| M23 | `stock` 不覆寫（兩個市場別預設相同） | 被抓到 |
| M24 | 忽略 `overrides` | 被抓到 |
| M25 | 未知市場別回預設而不報錯 | 被抓到 |
| M26 | 民國年不處理「年月日」格式 | 被抓到 |

工具紀律：整行比對、`count(frm) == 1` 才執行、每次變異後立即還原並比對檔案 sha256。矩陣在**最終版檔案**上重跑過，27／27 全數被抓到；還原後 `ediaad/markets/adjust.py` `0e694cea`、`calendar.py` `2eb5443a`、`twse.py` `7b58e675` 與變異前一致，兩個目標檔共 `116 passed`。

### 「先判讀、再決定」的兩個存活者

- **M9（事件未依日期排序）**：第一輪存活。追查發現**結果層面確實等價**——每個事件的遮罩 `stamps < event.date` 彼此獨立，先後不影響乘哪些倍率。但我沒有就此結案：浮點乘法在最後一位不滿足交換律，因此「輸入順序不同 → 位元不同」是**真的**（上面的 72.36 vs 72.36000000000001）。SPEC 第 6 節要求「同一輸入與參數必須得到位元相同的結果」，所以 `sorted()` 是承載該要求的實作，只是我原本的測試用了 `pytest.approx` 與 `assert_frame_equal`（後者預設 `check_exact=False`）而看不見。把斷言改成 `list(a) == list(b)` 之後 M9 立刻被抓到。
- **M22（`apply_calendar` 改動輸入）**：第一輪的變異字串寫成 `series = series`——這是**空操作**，不是變異（我的工具錯誤）。已拆成 M22a（不重新編號）與 M22b（在輸入上加欄位），前者當時確實沒有測試守住（已補索引斷言），後者立即被抓到。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_markets_twse_adjust.py -q` | 0（`58 passed in 0.47s`） | snap-2026-09-24-ocaievo-twse-adjust-calendar |
| 相關回歸（TWSE 來源＋偵測器＋registry） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_markets_twse.py tests/test_patterns_detect.py tests/test_markets_base.py -q` | 0（`127 passed in 0.59s`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`411 passed in 19.32s`） | 同上 |
| 整檔 Red（移除實作） | `ocaievo/`：暫時移除 `adjust.py`／`calendar.py` 後跑本張單檔 | 1（`58 failed in 1.22s`：測試檔在函式內匯入這兩個模組，因此每個測試各自失敗而非整檔無法收集） | 同上 |
| 未使用匯入掃描 | `ocaievo/`：AST 粗檢 `ediaad/` | 0（無發現） | 同上 |
| 變異後還原驗證 | 同本張單檔與相關回歸 | 0，三個受變異檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- **SPEC 第 7 節的人工目視檢查（除權息還原前後的命中差異）依 SPEC 的設計由 TASK-022 的 K 線圖三相位標註一併執行**；本張以程式斷言覆蓋同一件事（未還原假命中、還原後零命中），但沒有產生圖形供人眼核對。
- 已知邊界（記錄）：
  - 日曆的完整度受限於 TWSE 的說明文字：只列出「值得公告」的日期，平日若不在清單中即視為交易日；連續假期靠說明文字的「N月N日至N月N日」展開，跨年或反向區間保守地只標記該列日期（見 Review A-2）。
  - `apply_calendar` 以**過濾**實作「非交易日不視為連續 K 線」，因此回傳的序列長度會變短；報告提到的另一種做法（原地標記）未採用。
  - 還原假設 `權值+息值 = 除權息前收盤價 - 除權息參考價`（TWSE 表附註），容忍 0.02；若真實資料出現不符的列，本張會直接失敗並指出該列，而不是靜默略過。真實端點未在本張重跑（`PROJECT.md` 已有 2026-09-24 存證）。
  - `adjust_series` 不從序列推斷商品代號，呼叫端負責只傳入該商品的事件。
  - 市場別預設目前只有 `crypto` 與 `stock` 兩組，且**沒有任何呼叫端**：`default_spec_for` 尚未接進 `monitor.load_config`（`source_id` → 市場別的對應屬 catalog／settings）。這是 TASK-013 A-1 跨 Task 缺口的同一條線（見 Review A-1）。
  - 只處理上市（`t18707_L` 的市場）與 TWT49U 的上市資料；上櫃（TPEx）不在範圍（ADR-003 的重訪條件）。
- 未涵蓋：Twelve Data／catalog（TASK-016／017）、來源分派與系統狀態頁（TASK-025）、SQLite（TASK-018）。
