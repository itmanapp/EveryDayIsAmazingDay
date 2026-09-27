# TASK-013 Code Review

- task_id：TASK-013
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-binance-source sha256:e87b743ed448eeeefb8adf89b09d764cb89336571c9a5b6cd3267b3b8f2391e1
- Task／Spec 版本：TASK-013 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 search 分支的簡化與兩處弱斷言強化）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `e87b743ed448eeeefb8adf89b09d764cb89336571c9a5b6cd3267b3b8f2391e1`；本張新增 `ediaad/markets/crypto.py` `1b1cb639…`、`tests/test_markets_binance.py` `05715913…`；修改 `ediaad/markets/__init__.py` `77928659…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的已提交、未提交、新增檔案：上述三個檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`base`／`custom`（TASK-012 交付物）本張只**新增註冊匯入**未改邏輯（`base.py` 雜湊 `2d048d7e…`、`custom.py` `80a548f7…` 均未變）；`data`／`monitor`／`cli` 等未修改
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-031、第 5 節模組表（`ediaad/markets/crypto.py`）、同節「外部依賴與失敗處理」（Binance 失敗時快取回退、無快取則 `SourceError`）、「資料生命週期」（`<cache_dir>/<symbol>_<interval>.csv` 由 `max_age` 控制）、「相容性／遷移」（不重建 `ediaad/sources/`）、第 5 節原則 2（外部效果可注入）與原則 3（錯誤分層）、第 7 節測試策略第 10 列；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F13（四種快取情境表）、第 7.2／7.3 節（加密貨幣來源、不需要金鑰）、第 4.6 節（快取位置與 `max_age`）；`docs/workflow/adr/ADR-001.md`；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-031 | `ediaad/markets/crypto.py`（`fetch_ohlcv` 的四種情境分支、`BinanceSource.fetch`、`cache_path`）；`tests/test_markets_binance.py` 47 個案例 | 符合 | A-1、A-2、A-3（advisory） |

逐條核對（AC-031 的四個宣稱）：

- **「快取有效時請求次數為 0」**：`test_fresh_cache_is_returned_without_any_request` 斷言 `http.count == 0` 且回傳值與快取以 `assert_frame_equal` 逐欄相同；`data_source == "cache"`。符合。
- **「過期時重取並覆寫」**：`test_expired_cache_triggers_a_request_and_rewrites_the_file` 斷言請求 1 次、URL 含 `symbol=BTCUSDT`／`interval=1h`、新內容為回應值，且 `load_csv(cache_path)` 與回傳值逐欄相同（真的被覆寫）。符合。
- **「失敗且有舊快取時回傳 `cache-stale`」**：`test_failure_with_a_stale_cache_returns_the_stale_copy`（`data_source == "cache-stale"`、仍嘗試請求一次、內容為舊快取）＋ `test_any_exception_from_the_injected_client_is_a_source_error`（三種例外型別都回退）。符合。
- **「失敗且無快取丟出 `SourceError`」**：`test_failure_without_a_cache_raises_a_source_error` 斷言訊息同時含商品代號與原始原因；損毀快取也視為無快取（三個案例）。符合。
- **「只用公開端點」**：`BASE_URL = https://api.binance.com/api/v3`，只使用 `/klines`（取得）與 `/exchangeInfo`（搜尋）；模組內無任何金鑰、標頭或私有路徑；`needs_api_key is False` 有測試。符合。
- **回傳值符合 Series 契約**：`test_fresh_cache_series_matches_the_contract` 逐項斷言欄位順序、`datetime64[ns, UTC]`、升冪、無重複、五個價格欄位 `float64`。符合。
- 不重建 `ediaad/sources/binance.py`：模組內只有一條路徑，`markets/crypto.py` 為唯一實作（`grep` 確認專案內沒有 `sources/` 目錄）。符合。

## 品質 Review

- **四種情境的實作是「單一出口」的直線流程**：讀快取 → 新鮮就回傳 → 否則嘗試取得 → 失敗則回退或拋錯 → 成功則覆寫後回傳。四種情境沒有重複的判斷散落各處，`data_source` 的三個可能值只在三個 `return` 出現一次。變異 M1～M5 全部被抓到，說明這條直線的每一段都有測試守著。
- **錯誤轉譯的邊界放對位置（本張最重要的品質決定）**：`except Exception` 只包住**注入的客戶端呼叫**這一行（那是外部邊界，任何例外都是來源失敗），解析與欄位檢查則包在明確的 `(EdiaadError, IndexError, ValueError, TypeError)` 內。這避免了「用寬鬆的 `except Exception` 掩蓋自己的程式缺陷」，同時讓快取回退的判斷（只攔 `SourceError`）成立。變異 M13（把客戶端例外縮成只攔 `OSError`）被抓到，證明這個邊界有被測試釘住。
- **畸形回應選擇 `SourceError` 而非 `DataFormatError`（已記錄）**：`DataFormatError` 是 exit 2 的「輸入錯誤」，若畸形回應丟它，有舊快取時就不會回退——那會讓 F13 的第三種情境在最需要它的時候失效。選擇 `SourceError`（exit 1 的來源失敗）並以 `raise ... from error` 保留原因，是讓「快取回退」與「錯誤分層」同時成立的唯一一致選擇。變異 M12 被抓到。
- **`search` 的冗餘分支已移除（M16 的收穫）**：原本同時比對 `symbol`／`baseAsset`／`quoteAsset`，但 Binance spot 的代號固定是「基礎 ＋ 計價」，後兩者必然是代號的子字串——這個分支無法被任何輸入觀測（變異 M16 因此存活）。留著是不可測的冗餘碼，已移除並在 docstring 寫明理由。**這是本張「變異檢查改變了實作」的一例**（不只是改變測試）。
- **快取寫入的原子性與失敗語意**：以「同目錄暫存檔 ＋ `replace` ＋ 失敗時清除暫存檔」實作，並以「不留暫存檔」的測試守住（變異 M6 把 `replace` 換成 `copy` 會留下暫存檔而被抓到）。寫入失敗一律 `SourceError`：快取目錄不可寫是部署問題，應立刻可見（與 CLI「輸出檔不可寫 → exit 1」的分層一致）。替代方案（只警告並回傳新鮮資料）已列為 A-3。
- **商品代號正規化**：`"  btcusdt "` → 請求 URL 與快取檔名皆為 `BTCUSDT`，避免同一商品因大小寫或空白產生兩份快取（F-001 的「同一份資料不應有多條路徑」在資料命名層的落實）。變異 M8 被抓到。
- **依賴方向與「不新增依賴」**：`crypto.py` 只依賴標準庫（`json`／`time`／`urllib.request`）、`pandas`、`data`、`errors`、`markets.base`；沒有 `requests`，沒有從 `cli`／`web` 反向匯入。`urllib.request` 是唯一真實網路出口，且被包在可注入的 `client` 之後，因此全部測試離線。
- **既有死碼**：AST 掃描未發現未使用匯入，但人工複查抓到 `import urllib.error`（工具的假陰性：`urllib` 這個名字因 `urllib.request` 而被視為已使用）。已移除並在最終版檔案上重跑變異矩陣。
- **測試品質**：四種情境各有正向與反向案例；畸形回應 7 種、非法參數 7 種、損毀快取 3 種、客戶端例外 3 種，皆參數化；`search` 的空查詢還額外斷言「不發出請求」。修正了一處同義反覆的弱斷言（`x == x[:1]`）。未發現其他問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 缺口 | advisory（**需在後續 Task 處理，勿遺漏**） | 本張只交付來源模組；`cli._local_cache_fetch` 仍固定使用 csv 來源，`ediaad/monitor.py`／`ediaad/cli.py` 都還沒有依 `Instrument.source_id` 分派來源（`get_source(instrument.source_id).fetch`）。TASK-025 的交付文字要求系統狀態頁顯示「各商品的資料來源（`cache`／`binance`／`cache-stale`）」，但**沒有任何 Task 的「預計觸及的檔案」列出 `monitor.py`／`cli.py`** | 把「依 `source_id` 分派來源 ＋ 在 `RunResult` 記錄每個商品的 `data_source`」明確編入 TASK-025（或 TASK-037 的整合項），並更新該 Task 的預計觸及檔案；本張已把介面準備好（`series.attrs["data_source"]`） | 待辦（已同步記入 `STATE.md` 的待決事項） |
| A-2 | 介面可及性 | advisory | 每個商品的 `data_source` 只能從 `series.attrs` 取得；`run_once` 目前不記錄它 | TASK-025 需要「最後輪詢時間／各商品來源」時，於 `RunResult` 增加逐商品的來源欄位（需先變更 Spec 的 `RunResult` 定義） | 待辦（同上） |
| A-3 | 失敗語意 | advisory | 快取寫入失敗時丟 `SourceError`，即使已成功取得新鮮資料 | 替代方案是「警告並回傳新鮮資料」。目前選擇讓部署問題立刻可見；若日後發現監控迴圈因唯讀目錄持續告警，可改為只記一次警告 | 已實作並記錄（TDD 紀錄 Cycle 2） |
| A-4 | 未測保證 | advisory | 快取的原子性是「構造上的保證」（`replace` 在同一檔案系統為原子操作），沒有以注入中斷的方式測試；測試只保證「不留暫存檔」 | 若要更強保證，可在 TASK-019／TASK-017 一併建立「原子寫入」的共用測試工具（注入中斷點） | 延後（無現時需求） |
| A-5 | 真實端點 | advisory | 本張全部以假 HTTP 客戶端測試，未重跑真實端點；真實回應的欄位漂移不會被本張的測試發現 | 真實端點的實測結果已記於 `PROJECT.md`（2026-09-24）；TASK-037 若重跑真實端點需另行取得使用者同意 | 已記錄（TDD 紀錄「未執行或受阻」） |

## 修正與重審

- 第 1 輪：Spec Review 符合；品質 Review 無 blocking。
- 依變異檢查的結果調整實作 1 處（移除 `search` 的不可觀測分支）與測試 2 處（同義反覆的弱斷言、客戶端例外的型別覆蓋）。
- 重審：重跑單檔（47 passed）、相關回歸（58 passed）與全套（295 passed）；重讀 `crypto.py` 複查四種情境的分支、錯誤轉譯邊界、快取寫入與 `search` 的比對邏輯；變異矩陣在最終版檔案上 16／16 全數被抓到。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-031 的四項宣稱與 Series 契約逐條符合）
- 品質 Review：passed（無 blocking；A-1 需在後續 Task 落實，A-2～A-5 為延後或已記錄的 advisory）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1／A-2（屬 TASK-025 的範圍，已明確記錄以免遺漏）、A-3（已實作，保留替代方案）、A-4（需共用測試工具）、A-5（需使用者同意才能連外）
- 能否標為 done：**可以**
- 限制與未驗證事項：monitor／CLI 尚未依 `source_id` 分派來源；`run_once` 不記錄逐商品 `data_source`；快取原子性的「無半寫」為構造保證；真實端點未在本張重跑
