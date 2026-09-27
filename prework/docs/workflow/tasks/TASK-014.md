# TASK-014：TWSE 日線來源與商品搜尋

- id：TASK-014
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-032","AC-033"]
- depends_on：["TASK-012"]
- test_evidence：["docs/workflow/tdd/TASK-014.md"]
- review_evidence：["docs/workflow/reviews/TASK-014.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：以注入的假 HTTP 客戶端提供 TWSE `STOCK_DAY` 回應時，TWSE 來源的 `fetch(symbol, interval, limit)` 回傳符合 Series 契約的日線——民國年日期（`113/07/01`）轉為西元 UTC `datetime64[ns]`（`2024-07-01`）、千分位字串（`20,936,005`）轉為 float（`20936005.0`）並映射為 `volume`（來源欄位為「成交股數」），欄位順序為 `time`、`open`、`high`、`low`、`close`、`volume`，且對不支援的週期（例如 `1h`）提出可讀錯誤。以 `STOCK_DAY_ALL` 與上市公司基本資料回應執行 `search(keyword, limit)` 時，可用股票代號或中文名關鍵字搜尋，回傳含代號與名稱的 `Instrument` 清單並限制筆數。
- 本張不做：不處理除權息還原與交易日曆（TASK-015）；不實作 Binance、Twelve Data、catalog（TASK-013、TASK-016、TASK-017）；不支援日線以外的週期；不把 `docs/workflow/evidence/twse-probe/twse-endpoints.json` 直接當成測試輸入（依 `docs/workflow/PROJECT.md`，該檔為一次性實測存證，測試改以其中記錄的真實欄位名與樣本值建立小型合成假回應）；不實作系統狀態頁（TASK-025）；不執行 git 或任何對外動作。
- 每個 AC 在本張負責的範圍：AC-032 全部（`STOCK_DAY` 解析、民國年轉西元、千分位轉 float、成交股數映射為 volume、Series 契約、不支援週期的可讀錯誤）；AC-033 全部（以代號與中文名關鍵字搜尋、`Instrument` 清單含代號與名稱、筆數上限）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-032、AC-033、第 5 節模組表（`ediaad/markets/twse.py` 的 `search`、`fetch`）與 Series 契約；`docs/architecture/ENGINEERING-REPORT.md` 第 7.3 節（台股只有日線、日期為民國年需轉換）、第 7.2 節目錄清單、第 4.4 節 Series 契約；`docs/workflow/PROJECT.md` 的端點實測表（TWSE `STOCK_DAY` 2330／2024-07 回 `200`、21 筆、民國年與千分位；`STOCK_DAY_ALL` 1,380 筆；`t187ap03_L` 1,095 筆）。
- 2026-09-24 實測存證（`docs/workflow/evidence/twse-probe/twse-endpoints.json`，只作對照、不作測試輸入）：`stock_day_2330_2024-07` 的欄位為 `["日期","成交股數","成交金額","開盤價","最高價","最低價","收盤價","漲跌價差","成交筆數","註記"]`，第一列為 `["113/07/01","20,936,005","20,320,957,284","968.00","977.00","965.00","968.00","+2.00","38,293",""]`，`total` 為 `21`；`stock_day_all` 為 JSON 陣列，欄位為 `Date`（民國無分隔，如 `1150923`）、`Code`、`Name`、`TradeVolume`、`TradeValue`、`OpeningPrice`、`HighestPrice`、`LowestPrice`、`ClosingPrice`、`Change`、`Transaction`；`listed_companies`（`t187ap03_L`）欄位含 `出表日期`、`公司代號`、`公司名稱`、`公司簡稱`。
- 模組與公開介面：新增 `ediaad/markets/twse.py`（`TwseSource`：`id="twse"`、`display_name`、`supported_intervals=("1d",)`、`needs_api_key=False`、`search`、`fetch`；模組級 `STOCK_DAY_URL`、`STOCK_DAY_ALL_URL`、`LISTED_COMPANIES_URL`、`parse_roc_date(value)`、`to_float(value)`）。
- 預計觸及的檔案：`ediaad/markets/twse.py`、`ediaad/markets/base.py`（僅新增註冊呼叫，如需要）、`tests/test_markets_twse.py`；實作前重新查證。
- 必要環境／依賴：`.venv`（TASK-001）；TASK-012 的 `Source` 介面與 registry、TASK-002 的 `data.from_rows` 與 Series 契約已完成；測試以假 HTTP 客戶端與 `tmp_path` 執行，全程離線。

## 測試計畫

- 測試公開邊界：`get_source("twse").fetch(...)` 與 `get_source("twse").search(...)` 的回傳值；以合成假 HTTP 回應（欄位名與樣本值照存證）驅動，不檢視私有解析函式以外的內部狀態。
- 第一個失敗行為與預期斷言：模組尚未存在時匯入失敗（`ModuleNotFoundError: No module named 'ediaad.markets.twse'`）；實作後第一個案例為 `STOCK_DAY` 解析：假回應含 `113/07/01` 與 `20,936,005` 兩列資料，斷言回傳序列第一列 `time == pandas.Timestamp("2024-07-01", tz="UTC")`、`time.dtype` 為 `datetime64[ns, UTC]`、`volume == 20936005.0`，且欄位順序等於 `SERIES_COLUMNS`。
- 後續例外／邊界情境：兩種民國年格式（`113/07/01` 與 `STOCK_DAY_ALL` 的七碼 `1150923`）皆正確轉換；`+2.00`／`-8.00` 漲跌欄位與 `X` 不比價、空字串註記不影響解析；`stat` 非 `OK` 或 `data` 為空時丟出可讀錯誤；`total` 與實際筆數不一致時的處理明確定義；搜尋關鍵字為空字串、含前後空白、英文大小寫與 `limit` 上限（回傳筆數不大於 `limit`）；同一代號重複出現（權證）時的去重規則；對 `interval="1h"` 丟出可讀錯誤並指出來源與週期。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_markets_twse.py -q`；相關回歸 `.venv/bin/python -m pytest tests/test_markets_base.py -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用（解析與搜尋皆可以假 HTTP 回應完整驗證；存證中的 449 筆除權息樣本另由 TASK-015 使用）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-013 的交付物（全套 295 passed）；本次新增 `ediaad/markets/twse.py` 與 `tests/test_markets_twse.py`，並在 `ediaad/markets/__init__.py` 加入註冊匯入（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-014.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-014.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-twse-source` sha256:6abcb8cfcb3711f2836195e077895448caf2bb8917c9d2731cc9e0030f644acc（原始碼樹，33 檔）；新增 `ediaad/markets/twse.py` `90253260…`、`tests/test_markets_twse.py` `479ddac8…`；修改 `ediaad/markets/__init__.py` `c2b90bce…`；全套 `353 passed`
- 取消、重開或變更原因：無
