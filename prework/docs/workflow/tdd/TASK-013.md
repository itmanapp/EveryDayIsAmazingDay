# TASK-013 測試紀錄

- task_id：TASK-013
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-binance-source sha256:e87b743ed448eeeefb8adf89b09d764cb89336571c9a5b6cd3267b3b8f2391e1
- alternative_reason：無（四種快取情境皆可用注入的假 HTTP 客戶端與 `tmp_path` 完整覆蓋，不需真實網路）
- Task／Spec 版本：TASK-013 / SPEC-001 v0.4
- 測試邊界：只呼叫模組級 `fetch_ohlcv`／`cache_path` 與 `get_source("binance").fetch`／`search`，觀察回傳序列、`data_source` 標記、假 HTTP 客戶端的請求 URL 與計數、以及 `cache_path` 指向的快取檔內容；不檢視私有函式。HTTP 一律注入假客戶端，全程離線。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-012 的交付物，全套 **248 passed**（本張完成後為 295 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/markets/crypto.py` | `1b1cb639` | 新增：Binance 公開端點來源（`BASE_URL`、`cache_path`、`fetch_ohlcv`、`OhlcvResult`、`BinanceSource`） |
| `ediaad/markets/__init__.py` | `77928659` | 修改：匯入 `crypto` 以完成註冊 |
| `tests/test_markets_binance.py` | `05715913` | 新增：47 個測試 |

## Cycle 1：四種快取情境（AC-031 核心，真實 Red → Green）

- 測試：快取有效時請求次數為 0 且回傳值與快取逐欄相同；快取有效時序列符合契約（欄位順序、`datetime64[ns, UTC]`、升冪、無重複、五個價格欄位 `float64`）；快取過期時請求 1 次、URL 含 `symbol=`／`interval=`、並覆寫快取檔；快取不存在時請求並建立快取檔；取得失敗但有過期快取時回傳 `cache-stale` 且仍嘗試過一次；取得失敗且無快取時 `SourceError`（訊息含商品與原始原因）；`BinanceSource.fetch` 在 `attrs["data_source"]` 回報來源；來源已註冊且六項成員齊備；`cache_path` 的檔名慣例，共 9 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_markets_binance.py -q` | 1 | `9 failed`：`ModuleNotFoundError: No module named 'ediaad.markets.crypto'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `9 passed in 0.37s` | snap-2026-09-24-ocaievo-binance-source／2026-09-24 |

- 實作：`OhlcvResult`（frozen：`series`＋`data_source`）、`cache_path`、`_default_client`（標準庫 `urllib` ＋ `json`，不新增依賴）、`_fetch_klines`（請求 → 形狀檢查 → 截取前六欄 → `data.from_rows(..., time_unit="ms")`）、`fetch_ohlcv`（讀快取 → 新鮮度判斷 → 取得 → 回退 → 原子覆寫）、`BinanceSource`（`fetch` 回傳序列並在 `attrs` 標示來源；`search` 走 `exchangeInfo`）；`register(BinanceSource())`。
- **實作中撞到的真實問題（由測試暴露）**：`from_rows` 以 `columns=KLINE_COLUMNS` 呼叫 `pd.DataFrame.from_records`，而 Binance 每列有 12 欄，因此第一次執行得到 `ValueError: 6 columns passed, passed data had 12 columns`（被化為 `SourceError`）。修正為先截取前六欄，並在截取前檢查每列都是陣列（少於六欄的列會被 `from_records` 擋下並轉為可讀錯誤）。

## Cycle 2：契約與錯誤邊界（**既有覆蓋**，無真實 Red）

- 測試：`cache_dir=None` 時每次都請求且失敗即 `SourceError`；以注入的時鐘決定新鮮度（`now=`，不動 mtime）；`max_age=0` 一律重新驗證；三種損毀快取（非 CSV、只有表頭、缺欄位）視為無快取；損毀快取＋取得失敗 → `SourceError`；七種畸形回應（錯誤物件、空陣列、非 JSON、欄位不足、時間無法解讀、價格非數值、列不是陣列）→ 可讀的 `SourceError`；七種非法參數（不支援週期、空週期、空商品、空白商品、`limit` 為 0／1001／布林）→ `ConfigError`；商品代號正規化（`"  btcusdt "` → URL 與快取檔名皆為 `BTCUSDT`）；快取寫入後不留暫存檔；快取目錄不可寫 → `SourceError` 且不留半寫檔；三種客戶端例外（`OSError`／`ValueError`／`RuntimeError`）都化為來源失敗，共 26 個（其中 19 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | — | — | **未取得**（見下） | — |
| Green | 同上 | 0 | `34 passed in 0.50s` | 同上／2026-09-24 |

- **如實記載的流程偏差**：本張的 `crypto.py` 在 Cycle 1 就一次寫成完整模組，因此 Cycle 2 與 Cycle 3 的測試首次執行即通過，**沒有真實 Red**。這是「先實作後補測試」的順序瑕疵。補救方式與 TASK-011 相同：不以 Cycle 的 Red 作為辨識力證據，改以**整檔 Red**（見下）與**變異檢查 16／16 全數擊殺**替代。
- 兩個值得記錄的設計決定（依測試計畫要求擇一並記錄）：
  1. **畸形回應一律 `SourceError`（不是 `DataFormatError`）**。理由：F13 的「取得失敗」在實作上就是「拿不到可用的新鮮資料」，而快取回退的判斷必須涵蓋解析失敗——若畸形回應丟 `DataFormatError`，有舊快取時就不會回退（`DataFormatError` 是 exit 2 的輸入錯誤，`SourceError` 才是 exit 1 的來源失敗）。`fetch_ohlcv` 因此只攔 `SourceError` 做回退，內層再把傳輸與解析失敗化為 `SourceError` 並保留原因（`raise ... from error`）。
  2. **快取寫入失敗一律 `SourceError`**。理由：快取目錄不可寫是部署問題，應立刻讓使用者知道（與 CLI「輸出檔不可寫 → exit 1」的分層一致），而不是每輪重試後才失敗。已列為 Review 的 advisory（替代方案是只警告並回傳新鮮資料）。

## Cycle 3：商品搜尋（`exchangeInfo`，**既有覆蓋**，無真實 Red）

- 測試：空查詢／空白查詢／`limit < 1` 回空清單且**不發出請求**；不分大小寫的子字串比對；`BTC` 命中兩個商品、`try` 只命中 `BTCTRY`、無命中回空清單；`limit` 生效並保持回應順序；請求打到 `exchangeInfo` 端點；三種畸形 `exchangeInfo`（非物件、`symbols` 非陣列、缺 `symbols`）→ `SourceError`；請求失敗 → `SourceError`；缺欄位或非物件的項目被跳過，共 12 個。
- 實作：`BinanceSource.search`（`query.strip().upper()`；空或 `limit < 1` 回 `[]`；逐項比對 **商品代號**）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Green | 同上 | 0 | `44 passed in 0.52s` | 同上／2026-09-24 |

- **簡化：移除 `baseAsset`／`quoteAsset` 的比對**。變異 M16（把比對改成只看商品代號）**存活**，追查後發現這個分支**無法被觀測**：Binance spot 的商品代號固定是「基礎資產 ＋ 計價資產」（`BTC` ＋ `USDT` → `BTCUSDT`），所以 `baseAsset`／`quoteAsset` 必然是代號的子字串，多比對兩個欄位的結果與只比對代號完全相同。留著等於不可測的冗餘碼，因此移除該分支並在 docstring 寫明理由；比對邏輯改以「子字串 vs 完全相等」的變異（M16 重寫後）守住。

## Cycle 4（補測）：強化兩處弱斷言

- `test_search_respects_the_limit` 原本寫成 `search(..., limit=1) == search(..., limit=1)[:1]`——**同義反覆**，對任何實作都成立。已改為斷言「保持回應順序的前 N 筆」。
- 原本所有客戶端例外都用 `OSError`，因此把 `except Exception` 縮成 `except OSError` 的變異會存活。已補參數化測試（`OSError`／`ValueError`／`RuntimeError`），同時驗證有舊快取時仍回退、無快取時丟 `SourceError`。

測試數 44 → 47。

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 新鮮度判斷反向（`<=` → `>`） | 被抓到：快取有效／過期兩個測試 |
| M2 | 完全不讀快取（`cached = None`） | 被抓到：`test_fresh_cache_is_returned_without_any_request` 等 |
| M3 | 移除過期快取回退 | 被抓到：`test_failure_with_a_stale_cache_returns_the_stale_copy` |
| M4 | `cache-stale` 標記寫成 `cache` | 被抓到：同上 |
| M5 | 不寫入快取 | 被抓到：`test_missing_cache_triggers_a_request_and_creates_the_file`、`test_expired_cache_triggers_a_request_and_rewrites_the_file` |
| M6 | 原子替換改為複製（留下暫存檔） | 被抓到：`test_the_cache_is_written_atomically_leaving_no_temporary_file` |
| M7 | 損毀快取改為直接外洩 | 被抓到：三個損毀快取案例 |
| M8 | 商品代號不做大小寫正規化 | 被抓到：`test_the_symbol_is_normalised_before_the_request_and_the_cache_path` |
| M9 | 不驗證 `limit` | 被抓到：三個 `limit` 參數案例 |
| M10 | 不驗證 `interval` | 被抓到：不支援週期／空週期案例 |
| M11 | K 線不截取前六欄 | 被抓到：所有取得測試（`from_records` 欄數不符） |
| M12 | 畸形回應改丟 `DataFormatError` | 被抓到：七個畸形回應案例 |
| M13 | 客戶端例外只攔 `OSError` | 被抓到：`ValueError`／`RuntimeError` 案例 |
| M14 | `search` 不做大小寫正規化 | 抓到：`test_search_matches_the_symbol_regardless_of_case` |
| M15 | `search` 忽略 `limit` | 被抓到：`test_search_respects_the_limit_and_keeps_the_payload_order` |
| M16 | `search` 改成完全相等比對 | 被抓到：`test_search_matches_any_symbol_containing_the_query` |

工具紀律：整行比對、`count(frm) == 1` 才執行、每次變異後立即還原並比對檔案 sha256。**變異矩陣在最終版檔案上重跑過一次**（移除未使用的 `urllib.error` 之後），16／16 全數被抓到，還原後 `ediaad/markets/crypto.py` `1b1cb639` 與變異前一致，單檔 `47 passed`。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_markets_binance.py -q` | 0（`47 passed in 0.51s`） | snap-2026-09-24-ocaievo-binance-source |
| 相關回歸（來源 registry＋序列契約） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_markets_base.py tests/test_data.py -q` | 0（`58 passed in 0.49s`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`295 passed in 18.63s`） | 同上 |
| 整檔 Red（移除實作） | `ocaievo/`：移除 `ediaad/markets/crypto.py`（並暫時取消註冊）後跑本張單檔 | 1（`47 failed in 0.83s`：測試檔在函式內匯入，因此每個測試各自失敗而非整檔無法收集） | 同上 |
| 未使用匯入掃描 | `ocaievo/`：AST 粗檢 `ediaad/` | 0（並以人工複查抓到 `urllib.error` 這個工具假陰性，已移除） | 同上 |
| 變異後還原驗證 | 同本張單檔 | 0（`47 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 已知邊界（記錄）：
  - **本張只交付來源模組，尚未把 registry 接進 monitor／CLI**。`cli._local_cache_fetch` 仍固定使用 csv 來源；依 `Instrument.source_id` 分派來源（`get_source(instrument.source_id).fetch`）與在系統狀態頁呈現 `data_source` 屬 TASK-025 的交付範圍（其交付文字已明列「各商品的資料來源（`cache`／`binance`／`cache-stale` 等）」），但沒有任何 Task 的「預計觸及的檔案」列出 `ediaad/monitor.py`／`ediaad/cli.py`。已於 Review 的 A-2 與 `STATE.md` 的待決事項明確記錄，避免遺漏。
  - `run_once` 目前不記錄每個商品的 `data_source`；本張提供的介面是 `series.attrs["data_source"]`（TASK-025 可直接消費）。
  - 快取的**原子性**以「同目錄暫存檔 ＋ `replace` ＋ 失敗時清除暫存檔」實作，並以「不留暫存檔」的測試守住；「寫入過程中絕不暴露半寫內容」屬於構造上的保證（`replace` 在同一檔案系統上是原子操作），**沒有**以注入中斷的方式測試。
  - `max_age` 以檔案 mtime 計算；系統時鐘被回調時的行為未定義（報告未要求）。
  - 真實端點未在本張重跑（`PROJECT.md` 已於 2026-09-24 實測 `klines`／`exchangeInfo` 回 `200`）；本張的測試全部以假 HTTP 客戶端進行，因此**不涵蓋**真實回應的欄位漂移。TASK-037 的整合驗收若要重跑真實端點，需另行取得同意。
  - `search` 只比對商品代號（見 Cycle 3 的簡化說明）；不支援中文名搜尋（TWSE 來源才有名稱欄位）。
- 未涵蓋：TWSE／Twelve Data／catalog（TASK-014／016／017）、除權息還原與交易日曆（TASK-015）、monitor／CLI 的來源分派與系統狀態頁（TASK-025）、SQLite（TASK-018）。
