# TASK-014 測試紀錄

- task_id：TASK-014
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-twse-source sha256:6abcb8cfcb3711f2836195e077895448caf2bb8917c9d2731cc9e0030f644acc
- alternative_reason：無（解析與搜尋皆可用注入的假 HTTP 回應完整驗證，不需真實網路）
- Task／Spec 版本：TASK-014 / SPEC-001 v0.4
- 測試邊界：只呼叫模組級 `parse_roc_date`／`to_float` 與 `get_source("twse").fetch`／`search`；假回應的欄位名與樣本值照 `docs/workflow/evidence/twse-probe/twse-endpoints.json` 的實測存證建立，但**不讀取該檔**（依 `PROJECT.md`，它是存證而非測試輸入）。全程離線。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-013 的交付物，全套 **295 passed**（本張完成後為 353 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/markets/twse.py` | `90253260` | 新增：TWSE 日線來源與商品搜尋（`STOCK_DAY_URL`／`STOCK_DAY_ALL_URL`／`LISTED_COMPANIES_URL`、`parse_roc_date`、`to_float`、`TwseSource`） |
| `ediaad/markets/__init__.py` | `c2b90bce` | 修改：匯入 `twse` 以完成註冊 |
| `tests/test_markets_twse.py` | `479ddac8` | 新增：58 個測試 |

## Cycle 1：`STOCK_DAY` 解析（AC-032，真實 Red → Green）

- 測試：民國年與千分位轉換（首列 `time == Timestamp("2024-07-01", tz="UTC")`、`volume == 20936005.0`）、五個價格欄位各取自對應中文欄名、請求 URL 含 `stockNo=`／`date=`（指定月中的任何一天都查該月 1 日）、未指定日期時用注入時鐘的當月、依時間升冪排序、來源已註冊且只宣告 `1d`、`parse_roc_date` 接受兩種格式、`to_float` 去千分位與正負號，共 8 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_markets_twse.py -q` | 1 | `7 failed`：`ModuleNotFoundError: No module named 'ediaad.markets.twse'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `8 passed in 0.33s` | snap-2026-09-24-ocaievo-twse-source／2026-09-24 |

- 最小實作（**刻意只做順利路徑**，讓 Cycle 2 有真實 Red）：`parse_roc_date`（`113/07/01` 與 `1150923`）、`to_float`（去千分位）、`_month_stamp`、`_coerce_date`、`_parse_stock_day`（只以 `fields.index()` 取位置、不做任何檢核）、`fetch`（只做請求與解析，未驗證 `interval`／`limit`）、`search` 先以 `NotImplementedError` 佔位。
- **如實記載的測試錯誤**：第一版 `test_fetch_requests_stock_day_for_the_symbol_and_month` 沒指定 `date`，因此查的是**當月**（2026-09）而非 2024-07，斷言 `date=20240701` 失敗。這是我的測試漏寫參數（實作正確）；已補上 `date="2024-07-15"`，並另立一個測試驗證「未指定時用注入時鐘的當月」。另在初稿留下兩個佔位／同義反覆的斷言（`pytest.approx(0)`、`x == x`），也在跑第一次之前就改為真斷言。

## Cycle 2：錯誤與邊界（AC-032，真實 Red → Green）

- 測試：七種壞回應（`stat` 非 OK、`data` 為空、缺 `data`、缺 `fields`、回應是陣列／字串／`None`）→ 可讀的 `SourceError`；`total` 與實際列數不一致 → 指出宣稱與實際筆數的 `SourceError`，字串型別的 `total` 仍可比對；缺中文欄位時**以欄名回報**；列長度不足時指出第幾列；非數值價格化為 `SourceError`（不是 `DataFormatError`）；三種客戶端例外都化為來源失敗；四種不支援週期 → `ConfigError` 並指出來源、週期與可用週期；七種非法參數（空／空白代號、`limit` 為 0／負／布林、`date` 用斜線或數字）→ `ConfigError`；`limit=None` 回傳整月；`limit=2` 取最近兩根且維持升冪，共 19 個（其中 15 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `19 failed`：`KeyError`／`ValueError`／`IndexError` 外洩、`limit` 未生效、`1h` 未被擋 | 同上／2026-09-24 |
| Green | 同上 | 0 | `36 passed in 0.37s` | 同上／2026-09-24 |

- 實作：`_require_interval`（只允許 `1d`）、`_require_limit`、`_field_positions`（以中文欄名取值，缺欄位指出欄名）、`_parse_stock_day` 的四層檢核（回應是物件 → `stat == "OK"` → 非空 `data` → `total` 一致性）＋逐列檢核（欄數、型別），並把 `DataFormatError` 外層化為 `SourceError`（`raise ... from error` 保留原因）；`fetch` 以 `limit` 取最近 N 根（`.iloc[-N:]` 後 `reset_index`）。
- **設計決定（與 TASK-013 一致）**：來源回應的解析失敗一律 `SourceError`（exit 1 的來源失敗），而不是 `DataFormatError`（exit 2 的輸入錯誤）。這樣監控迴圈會把它當成「這個商品這一輪失敗」而不是「使用者的設定錯了」。`parse_roc_date`／`to_float` 本身仍是通用的 `DataFormatError` 拋出者（它們也有直接的單元測試），由來源層負責轉譯。
- **`total` 不一致的定義**：TWSE 回應若宣稱的筆數與實際列數不同，視為回應被截斷 → `SourceError`（訊息同時給出兩個數字）。`total` 缺席或無法轉成整數時不比對。

## Cycle 3：商品搜尋（AC-033，真實 Red → Green）

- 測試：以代號搜尋、以公司簡稱搜尋、以公司**全名**搜尋（只有在目錄端點才有的字串）、找到只存在於 `STOCK_DAY_ALL` 的 ETF、找到只存在於目錄的公司、同一代號在兩個端點都出現時只回一筆且顯示名稱用公司簡稱、英文代號不分大小寫、查詢去前後空白、空查詢不發出請求、`limit` 生效、兩個端點都被請求，以及四種目錄失敗 → 可讀的 `SourceError`，共 15 個（其中 4 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `15 failed`：`NotImplementedError` | 同上／2026-09-24 |
| Green | 同上 | 0 | `49 passed`（含後續修正，見下） | 同上／2026-09-24 |

- 實作：`_get_json`（客戶端例外 → `SourceError`）、`_require_records`（必須是 JSON 陣列）、`_merge_directory`（合併兩端點、以代號為鍵、**顯示名稱優先序 公司簡稱 ＞ 當日行情名稱 ＞ 公司全名**）、`search`（空查詢或 `limit < 1` 回空清單；比對代號與所有蒐集到的名稱；依代號排序後取前 `limit` 筆）。
- **為何兩個端點都要查**：`STOCK_DAY_ALL` 含 ETF 等非公司證券（目錄沒有），`t18707_L` 有公司簡稱（搜尋「台泥」這種簡稱才找得到）。變異 M15／M16／M20 分別移除其中一邊的比對或整個請求，全部被抓到——兩個端點的必要性有測試守著。兩個端點都必須成功（結果不完整卻不告知比直接失敗更糟），已列為 Review 的 advisory。
- **如實記載的測試錯誤**：`test_search_prefers_the_short_name_and_dedups_by_code` 原本用查詢「台」並期望 `["1101","2330"]`，但「元大台灣50」也含「台」且代號 `0050` 排序在最前，因此實作正確、**我的期望錯了**。已把該測試改為用「台積」（同時命中兩個端點的 2330，才真的在驗去重與簡稱優先），並把「依代號排序」獨立成另一個測試（期望 `["0050","1101","2330"]`）。

## Cycle 4（補測）：任務計畫列出但尚未明確覆蓋的邊界

- `漲跌價差` 為 `X`、`註記` 為 `**` 或空白不影響解析（本張不讀這三欄）。
- `date` 四種形式（`2024-07-15`／`20240715`／`date` 物件／`datetime` 物件）都查同一月份。
- 同一代號在**同一個端點內**重複出現時仍只回一筆。
- 測試數 49 → 58。

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 民國年不 `+1911` | 被抓到：所有解析測試 |
| M2 | 七碼日期不解析 | 被抓到：`parse_roc_date` 的緊湊格式案例 |
| M3 | `to_float` 不去千分位 | 被抓到：`to_float` 與 `volume` 斷言 |
| M4 | 不檢查 `stat` | 被抓到：`stat` 非 OK 案例 |
| M5 | 不檢查空 `data` | 被抓到：`data` 為空案例 |
| M6 | 不檢查 `total` 一致性 | 被抓到：`test_a_total_mismatch_is_a_truncated_response_error` |
| M7 | 缺中文欄位不報錯（改用位置 0） | 被抓到：`test_a_missing_chinese_field_is_reported_by_name` |
| M8 | 不檢查每列長度 | 被抓到：列長度不足案例 |
| M9 | 解析錯誤不外層化為 `SourceError` | 被抓到：非數值價格案例 |
| M10 | 不驗證 `interval` | 被抓到：四個不支援週期案例 |
| M11 | 不驗證 `limit` | 被抓到：三個 `limit` 參數案例 |
| M12 | `limit` 取最舊的 N 筆 | 被抓到：`test_limit_keeps_the_most_recent_rows_in_ascending_order` |
| M13 | `limit=None` 仍截斷成 5 筆 | **第一次存活**（見下），修正夾具後被抓到 |
| M14 | `search` 不比對代號 | 被抓到：以代號搜尋的案例 |
| M15 | `search` 不比對目錄名稱 | 被抓到：全名／簡稱搜尋案例 |
| M16 | `search` 不比對當日行情名稱 | 被抓到：ETF 搜尋案例 |
| M17 | 顯示名稱優先序反轉（全名優先） | 被抓到：`test_search_dedups_by_code_and_prefers_the_short_name` |
| M18 | `search` 不排序（用回應順序） | 被抓到：`test_search_returns_matches_sorted_by_code` |
| M19 | `search` 不檢查 `limit` 下界 | 被抓到：`limit=0` 案例 |
| M20 | `search` 只查目錄（不查當日行情） | 被抓到：ETF 搜尋案例 |

工具紀律：整行比對、`count(frm) == 1` 才執行、每次變異後立即還原並比對檔案 sha256。矩陣在**最終版檔案**上重跑過（把 `_default_client` 的區域匯入提升到模組層之後），20／20 全數被抓到，還原後 `ediaad/markets/twse.py` `90253260` 與變異前一致，單檔 `58 passed`。

**M13 的判讀（不是等效變異，是我的夾具太弱）**：`limit=None` 的測試原本只放 5 列，而變異把它截斷成 5 筆，結果完全相同。已把夾具加寬到 7 列並斷言首末日期，讓任何預設截斷都會被抓到。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_markets_twse.py -q` | 0（`58 passed in 0.41s`） | snap-2026-09-24-ocaievo-twse-source |
| 相關回歸（來源 registry＋Binance＋自訂 CSV） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_markets_base.py tests/test_markets_binance.py -q` | 0（`88 passed in 0.65s`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`353 passed in 18.65s`） | 同上 |
| 未使用匯入掃描 | `ocaievo/`：AST 粗檢 `ediaad/` | 0（無發現） | 同上 |
| 變異後還原驗證 | 同本張單檔 | 0（`58 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 已知邊界（記錄）：
  - **本張不含快取**。AC-032 未要求快取，因此 `TwseSource.fetch` 每次都請求；`<cache_dir>/<symbol>_<interval>.csv` 的快取與「快取 → 交易所 → 過期快取」的來源鏈仍未接上（同 TASK-013 的 A-1 跨 Task 缺口：`monitor.py`／`cli.py` 尚未依 `source_id` 分派來源）。
  - **`fetch` 一次只取一個月**：`STOCK_DAY` 是「某月」的端點，因此 `fetch` 回傳的是 `date` 所屬月份的日線（預設當月），不是連續 N 根。要取得跨月歷史需多次呼叫或由呼叫端組合；報告未要求，已記錄。
  - `search` 每次都請求兩個端點（無快取）；商品目錄的快取留給 TASK-017 的 catalog。
  - `search`／`fetch` 的 `limit` 假設是整數（與 TASK-013 的 `BinanceSource.search` 一致）；從 HTTP 查詢字串進來的值必須由呼叫端先轉型（TASK-025）。
  - 真實端點未在本張重跑（`PROJECT.md` 已於 2026-09-24 實測 `STOCK_DAY` 2330／2024-07 回 200、21 筆）；本張全部以合成假回應測試，因此**不涵蓋**日後 TWSE 的欄位變動。TASK-037 若要重跑真實端點需另行取得同意。
  - 只處理上市（`t18707_L`）與 `STOCK_DAY_ALL`；上櫃（TPEx）不在範圍（ADR-003 已列為重訪條件）。
- 未涵蓋：除權息還原與交易日曆（TASK-015，會重用本張的 `parse_roc_date`）、Twelve Data／catalog（TASK-016／017）、來源分派與系統狀態頁（TASK-025）、SQLite（TASK-018）。
