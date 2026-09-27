# TASK-013：Binance 來源與四種快取情境

- id：TASK-013
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-031"]
- depends_on：["TASK-012"]
- test_evidence：["docs/workflow/tdd/TASK-013.md"]
- review_evidence：["docs/workflow/reviews/TASK-013.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：以注入的假 HTTP 客戶端呼叫 Binance 來源的 `fetch(symbol, interval, limit)` 時，四種情境各自成立——快取仍在有效期內回傳快取內容且對假客戶端的請求次數為 0（`data_source` 為 `cache`）；快取過期或不存在時重新取得並覆寫快取檔（`binance`）；取得失敗但有過期快取時回傳過期快取並標示 `cache-stale`；取得失敗且無快取時丟出 `SourceError`。回傳值符合 Series 契約（`time` 為 UTC `datetime64[ns]`、升冪、無重複，`open`／`high`／`low`／`close`／`volume` 皆 float64 且欄位順序固定）。全程只使用 Binance 公開端點，不接觸任何金鑰或私有 API。
- 本張不做：不實作 TWSE、Twelve Data 或 catalog（TASK-014、TASK-016、TASK-017）；**不建立 `ediaad/sources/binance.py` 向後相容層**（理由見 SPEC 第 5 節「相容性／遷移」與 ADR-001：從零重建，沒有需要相容的呼叫端；Binance 只保留 `ediaad/markets/crypto.py` 一條實作路徑，避免重現 F-001 的資料結構不一致）；不引入 `requests` 等新依賴，HTTP 以標準庫 `urllib` 實作且客戶端可注入；不改動 `Source` 協定與 registry 契約（TASK-012）；不實作系統狀態頁的來源標示呈現（TASK-025）；不執行 git 或任何對外動作。
- 每個 AC 在本張負責的範圍：AC-031 全部（四種快取情境、請求次數計數、`cache-stale` 回退、無快取時的 `SourceError`、只用公開端點）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-031、第 5 節模組表（`ediaad/markets/crypto.py` 的 `BASE_URL`、`cache_path`、`fetch_ohlcv`）、同節「外部依賴與失敗處理」（Binance 失敗時快取回退、無快取則 `SourceError`）、「相容性／遷移」（不重建 `ediaad/sources/` 的理由）與資料生命週期（`<cache_dir>/<symbol>_<interval>.csv`）；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F13（四種快取情境表）、第 7.2 與 7.3 節（加密貨幣來源、不需要金鑰）、第 4.6 節（快取位置與 `max_age`）；`docs/workflow/PROJECT.md` 的端點實測表（Binance `klines`／`exchangeInfo` 回 `200`、CORS `*`，2026-09-24）。
- 模組與公開介面：新增 `ediaad/markets/crypto.py`（`BinanceSource`：`id="binance"`、`display_name`、`supported_intervals`、`needs_api_key=False`、`search`、`fetch`；模組級 `BASE_URL`、`cache_path(symbol, interval, cache_dir)`、`fetch_ohlcv(symbol, interval, limit, cache_dir, client, max_age)` 與 `data_source` 回報）。此模組是 Binance 的**唯一**實作路徑。
- 預計觸及的檔案：`ediaad/markets/crypto.py`、`ediaad/markets/base.py`（僅新增註冊呼叫，如需要）、`tests/test_markets_binance.py`；實作前重新查證。
- 必要環境／依賴：`.venv`（TASK-001）；TASK-012 的 `Source` 介面與 registry、TASK-002 的 `data.from_rows` 契約已完成；測試以假 HTTP 客戶端與 `tmp_path` 快取目錄執行，全程離線；不需要重跑真實端點（`docs/workflow/PROJECT.md` 已記錄 2026-09-24 實測結果）。

## 測試計畫

- 測試公開邊界：`get_source("binance").fetch(...)` 與 `fetch_ohlcv(...)` 的回傳值、`data_source` 標記、假客戶端的請求計數與 `cache_path` 指向的快取檔內容；不檢視私有函式。
- 第一個失敗行為與預期斷言：模組尚未存在時匯入失敗（`ModuleNotFoundError: No module named 'ediaad.markets.crypto'`），對應測試收集失敗；實作後的第一個案例為「快取有效」：於 `tmp_path` 寫入一份新鮮快取 CSV，假客戶端計數器維持 0，`fetch` 回傳值與快取內容逐欄相同且 dtype 符合契約，`data_source == "cache"`。
- 後續例外／邊界情境：快取過期時請求次數為 1 且快取檔被新內容覆寫；取得失敗但有舊快取時回傳舊值、`data_source == "cache-stale"` 且不丟例外；取得失敗且無快取時丟出 `SourceError`；假回應為畸形 JSON 或缺 kline 欄位時的可讀錯誤（`SourceError` 或 `DataFormatError` 須在實作時擇一並記錄於 TDD）；快取檔損毀（非 CSV 內容）視為無快取；`symbol` 大小寫與不在 `supported_intervals` 的 `interval` 得到可讀錯誤。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_markets_binance.py -q`；相關回歸 `.venv/bin/python -m pytest tests/test_markets_base.py -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用（四種情境皆可以假 HTTP 客戶端與 `tmp_path` 完整覆蓋，不需真實網路或人工檢查）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-012 的交付物（全套 248 passed）；本次新增 `ediaad/markets/crypto.py` 與 `tests/test_markets_binance.py`，並在 `ediaad/markets/__init__.py` 加入註冊匯入（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-013.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-013.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-binance-source` sha256:e87b743ed448eeeefb8adf89b09d764cb89336571c9a5b6cd3267b3b8f2391e1（原始碼樹，31 檔）；新增 `ediaad/markets/crypto.py` `1b1cb639…`、`tests/test_markets_binance.py` `05715913…`；修改 `ediaad/markets/__init__.py` `77928659…`；全套 `295 passed`
- 取消、重開或變更原因：無
