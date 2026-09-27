# TASK-015：TWSE 除權息還原與交易日曆

- id：TASK-015
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-034","AC-035"]
- depends_on：["TASK-008", "TASK-014"]
- test_evidence：["docs/workflow/tdd/TASK-015.md"]
- review_evidence：["docs/workflow/reviews/TASK-015.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：以 TWSE `TWT49U` 回應取得除權息事件後呼叫還原函式，還原後的台股序列在除權息日不再出現向下的價格跳空，因而呼叫 `patterns.detect` 時不在該日產生「向下跌破」命中；未還原的同一序列會產生假命中（作為對照）。事件物件含除權息前收盤價、除權息參考價與權值+息值三個欄位。以 TWSE `holidaySchedule` 回應建立交易日曆後，非交易日不會被當成連續 K 線；台股與加密貨幣使用不同的規律預設參數（市場別預設），且預設值可被設定覆寫。
- 本張不做：不實作日線取得與商品搜尋（TASK-014，本張只消費其序列與來源）；不實作 Binance、Twelve Data、catalog（TASK-013、TASK-016、TASK-017）；不新增 `PatternSpec` 欄位或修改偵測演算法（TASK-007、TASK-008）；不實作系統狀態頁的標記呈現（TASK-025，本張只提供狀態資訊）；不實作上櫃（TPEx）或其他市場的除權息（`docs/workflow/adr/ADR-003.md` 已列為重訪條件）；不執行 git 或任何對外動作。
- 每個 AC 在本張負責的範圍：AC-034 全部（`TWT49U` 事件取得、還原公式、事件三欄位、還原後不產生假跌破、未還原序列的假命中對照）；AC-035 全部（`holidaySchedule` 日曆、非交易日不視為連續 K 線、市場別規律預設參數與可覆寫性）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-034、AC-035、第 5 節模組表（`ediaad/markets/adjust.py` 的 `ExRightsEvent`、`fetch_ex_rights`、`adjust_series`；`ediaad/markets/calendar.py` 的 `TradingCalendar`、`is_trading_day`、`load_twse_calendar`）、第 8 節 Q-012（還原公式以 TWSE 欄位為依據）與風險 5（股票市場連續等距 K 線假設不成立）；`docs/workflow/adr/ADR-003.md`（方案 B 為主、方案 A 為輔、方案 C 保底，並修正報告第 7.4 節結論）；`docs/architecture/ENGINEERING-REPORT.md` 第 7.4 節（除權息、交易日曆、市場別預設）。
- 2026-09-24 實測存證（`docs/workflow/evidence/twse-probe/twse-endpoints.json`）：`exrights_2024-07` 以 `startDate=20240701`／`endDate=20240731` 取得 `stat=OK`、449 筆，標題為 `113年07月01日 至 113年07月31日 除權除息計算結果表`，欄位含 `資料日期`、`股票代號`、`股票名稱`、`除權息前收盤價`、`除權息參考價`、`權值+息值`、`權/息`、`減除股利參考價` 等，第一列為 `["113年07月01日","1101","台泥","34.20","33.20","1.000000","息",...]`，附註明載「權值+息值=除權息前收盤價-除權息參考價」與公式「除權息參考價 = (除權息前收盤價-息值+現金增資認購價*現金增資配股率)/(1+無償配股率+現金增資配股率)」；`holiday_schedule` 為 115 年市場開休市日期共 27 筆，欄位為 `日期`、`名稱`、`說明`（例如 `["2026-01-01","中華民國開國紀念日","依規定放假1日。"]`、`["2026-02-12","市場無交易，僅辦理結算交割作業",""]`）。同一存證亦確認 `strDate`／`endDate` 回誤導性錯誤、`date=` 被忽略只回當日，故本張只用 `startDate`／`endDate`。
- 模組與公開介面：新增 `ediaad/markets/adjust.py`（`ExRightsEvent`、`fetch_ex_rights(...)`、`adjust_series(series, events)`）；新增 `ediaad/markets/calendar.py`（`TradingCalendar`、`is_trading_day(date)`、`load_twse_calendar(payload)`、`apply_calendar(series, calendar)`（名稱於實作時定案並記錄）、市場別預設規格對照 `MARKET_PATTERN_DEFAULTS` 與 `default_spec_for(market_id)`，用於台股日線與加密貨幣的不同預設並允許設定覆寫）。
- 預計觸及的檔案：`ediaad/markets/adjust.py`、`ediaad/markets/calendar.py`、`ediaad/markets/twse.py`（僅新增除權息與日曆端點呼叫，如需要）、`tests/test_markets_twse_adjust.py`，必要時同步 `docs/workflow/adr/ADR-003.md` 的後續註記；實作前重新查證。
- 必要環境／依賴：`.venv`（TASK-001）；TASK-014 的 TWSE 來源與民國年解析、TASK-002 的 Series 契約已完成；AC-034 的命中對照以 `patterns.detect`（TASK-008，已列入本張 `depends_on`）為觀察邊界，因此本張可完整斷言「還原後不命中、未還原會假命中」；測試以假 HTTP 回應與合成序列執行，全程離線。

## 測試計畫

- 測試公開邊界：`fetch_ex_rights(...)` 回傳的事件欄位、`adjust_series(...)` 的回傳序列，以及 `TradingCalendar.is_trading_day(...)`／`load_twse_calendar(...)` 的判定結果；以假 HTTP 回應與合成序列驅動，不檢視私有解析細節。
- 第一個失敗行為與預期斷言：模組尚未存在時匯入失敗（`ModuleNotFoundError: No module named 'ediaad.markets.adjust'`）；實作後第一個案例為台泥 `113年07月01日`：事件解析出除權息前收盤價 `34.20`、除權息參考價 `33.20`、權值+息值 `1.000000`，且 `adjust_series` 後該日的相鄰收盤報酬絕對值小於 `1e-9`（未還原時同一位置為明顯負跳空）。
- 後續例外／邊界情境：同一商品一年內多次除權息事件的疊加還原；事件缺漏或端點失敗時保留未還原序列並在回傳的狀態標記（方案 A 輔助、方案 C 保底，見 ADR-003）；非交易日（週末與 `holiday_schedule` 中如 `2026-02-12`「市場無交易，僅辦理結算交割作業」）不被視為連續 K 線；日曆套用後每個用於 `detect` 的時間戳皆為交易日；台股日線與加密貨幣的市場別預設規格不同，且以設定覆寫後以覆寫值為準；`holidaySchedule` 缺少某年度時的可讀錯誤或明確降級。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_markets_twse_adjust.py -q`；相關回歸 `.venv/bin/python -m pytest tests/test_markets_twse.py tests/test_patterns_detect.py -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：除權息還原前後的命中差異另需人工目視核對（`docs/workflow/SPEC.md` 第 7 節「必要的人工／視覺檢查」第 4 項）；自動測試負責還原數值與假跌破的程式斷言，人工檢查於 TASK-022 的 K 線圖三相位標註一併執行。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-014 的交付物（全套 353 passed）；本次新增 `ediaad/markets/adjust.py`、`ediaad/markets/calendar.py` 與 `tests/test_markets_twse_adjust.py`，並修改 `ediaad/markets/base.py`（新增共用 `parse_iso_day`）、`ediaad/markets/twse.py`（`parse_roc_date` 增加年月日格式）、`ediaad/markets/__init__.py`（匯出新模組）、`tests/test_markets_twse.py`（補年月日案例）（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-015.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-015.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-twse-adjust-calendar` sha256:c3d0aca4e8b4c5d17e8fbd36b893e247741cee52c01f9e25f39c88b7a4102f68（原始碼樹，36 檔）；新增 `ediaad/markets/adjust.py` `0e694cea…`、`ediaad/markets/calendar.py` `2eb5443a…`、`tests/test_markets_twse_adjust.py` `90817abb…`；全套 `411 passed`
- 取消、重開或變更原因：無
