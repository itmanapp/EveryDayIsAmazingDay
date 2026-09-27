# TASK-014 Code Review

- task_id：TASK-014
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-twse-source sha256:6abcb8cfcb3711f2836195e077895448caf2bb8917c9d2731cc9e0030f644acc
- Task／Spec 版本：TASK-014 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 M13 夾具修正與 search 期望值修正）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `6abcb8cfcb3711f2836195e077895448caf2bb8917c9d2731cc9e0030f644acc`；本張新增 `ediaad/markets/twse.py` `90253260…`、`tests/test_markets_twse.py` `479ddac8…`；修改 `ediaad/markets/__init__.py` `c2b90bce…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的已提交、未提交、新增檔案：上述三個檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`base`／`custom`／`crypto`（TASK-012／013 交付物）本張只新增註冊匯入，未修改其邏輯（`base.py` `2d048d7e…`、`custom.py` `80a548f7…`、`crypto.py` `1b1cb639…` 均未變）
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-032／AC-033、第 5 節模組表（`ediaad/markets/twse.py` 的 `search`／`fetch`）、Series 契約、第 5 節原則 2（外部效果可注入）與原則 3（錯誤分層）、第 7 節測試策略第 10 列；`docs/architecture/ENGINEERING-REPORT.md` 第 7.3 節（台股只有日線、民國年需轉換）、第 7.2 節、第 4.4 節；`docs/workflow/PROJECT.md` 的端點實測表；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-032 | `ediaad/markets/twse.py`（`parse_roc_date`、`to_float`、`_parse_stock_day`、`fetch`）；`tests/test_markets_twse.py` 36 個案例 | 符合 | A-2、A-4（advisory） |
| AC-033 | `ediaad/markets/twse.py`（`_merge_directory`、`search`）；同檔 15 個案例 | 符合 | A-1（advisory） |

逐條核對：

- **AC-032「民國年轉為西元」**：`113/07/01` → `2024-07-01`、`1150923` → `2026-09-23`；`time.dtype == "datetime64[ns, UTC]"`（由 `data.from_rows` ＋ `_build_series` 統一保證，不另寫轉換）。符合。
- **AC-032「千分位字串轉為 float、成交股數映射為 volume」**：`20,936,005` → `20936005.0`，且 `volume` 取自中文欄名「成交股數」而非固定欄序（缺欄位時訊息指出欄名，變異 M7 證明）。符合。
- **AC-032「欄位順序為 time／open／high／low／close／volume」**：`list(series.columns) == list(SERIES_COLUMNS)` 有斷言；`from_rows` 的契約保證。符合。
- **AC-032「不支援的週期提出可讀錯誤」**：四種週期（`1h`／`1m`／`1w`／空字串）都得到 `ConfigError`，訊息含來源 id `twse`、週期與可用週期 `['1d']`。符合。
- **AC-033「可用代號或中文名關鍵字搜尋、回傳含代號與名稱的 `Instrument` 清單並限制筆數」**：以代號、公司簡稱、公司全名三種關鍵字都有案例；`Instrument` 帶 `symbol`／`display_name`／`source_id`；`limit` 與空查詢都有案例。符合。

## 品質 Review

- **不寫死欄序（本張最重要的品質決定）**：TWSE 的 `STOCK_DAY` 同時給 `fields`（中文欄名）與位置陣列。實作以 `fields.index(中文名)` 建立「欄位 → 位置」對照再取值，因此 TWSE 若調整欄序不會靜默取錯值，而缺欄位會以欄名回報（變異 M7 把缺欄位改成靜默取位置 0，立刻被抓到）。這是「同一份資料不應因欄序假設而產生不同結構」（F-001）在解析層的落實。
- **錯誤分層與 TASK-013 一致**：來源回應的解析失敗一律 `SourceError`（exit 1），不是 `DataFormatError`（exit 2）。理由：使用者沒有輸入錯任何東西，是來源給了不能用的內容；監控迴圈應把它當成「這個商品這一輪失敗」而不是「設定錯了」。`parse_roc_date`／`to_float` 仍是通用 helper（拋 `DataFormatError`，有直接單元測試），來源層負責轉譯並以 `raise ... from error` 保留原因（變異 M9 證明）。
- **`total` 一致性檢查**：TWSE 的 `total` 是「該月交易日數」，與 `data` 列數不符即代表回應被截斷。若靜默接受，使用者會拿到不完整的月份而毫無察覺（對 `detect` 這種需要連續 K 線的運算尤其危險）。字串型別的 `total` 也能比對（有案例）。
- **兩個目錄端點都必要，且都有測試證明**：`STOCK_DAY_ALL` 提供 ETF 等非公司證券（目錄沒有），`t18707_L` 提供公司簡稱（「台泥」這種簡稱才找得到）。變異 M15／M16／M20 分別移除目錄名稱比對、當日行情名稱比對與整個當日行情請求，全部被抓到——這兩個端點不是「多查一個比較保險」，而是各自無可替代。
- **顯示名稱的優先序明確**：公司簡稱 ＞ 當日行情名稱 ＞ 公司全名。這讓 G3 的下拉選單顯示使用者認得的名稱（「台泥」而不是「臺灣水泥股份有限公司」）。變異 M17 反轉優先序後被抓到。
- **依賴方向與可注入性**：`twse.py` 只依賴標準庫（`json`／`urllib.request`／`datetime`）、`pandas`、`data`、`errors`、`markets.base`；HTTP 客戶端與時鐘（`client`／`now`）皆可注入，因此 58 個測試全部離線且不依賴當下日期。
- **測試品質**：每個錯誤路徑都斷言「訊息裡有可辨識的內容」（欄名、第幾列、來源 id、宣稱與實際筆數），不是只斷言「有丟錯」；參數化覆蓋四種週期、七種非法參數、七種壞回應、三種客戶端例外、四種日期形式、四種目錄失敗。未發現新的問題。
- **本張抓到的兩個測試缺陷（皆為我的斷言錯，不是實作錯）**：
  1. `limit=None` 的夾具只有 5 列，而變異「截斷成 5 筆」因此存活 → 加寬到 7 列並斷言首末日期。
  2. `search("台")` 的期望值漏算「元大台灣50」也含「台」且 `0050` 排序在前 → 改用「台積」驗去重與簡稱優先，並把排序獨立成一個測試。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 可用性 | advisory | `search` 需要兩個端點都成功；任一端點故障時整個搜尋失敗（而非回傳不完整清單）。影響：G3 的下拉選單在 TWSE 部分故障時完全無法搜尋 | 目前選擇「不靜默給出殘缺結果」；若實務上目錄端點常故障，可改為「目錄失敗時只用當日行情並在回應中標示不完整」（需先定義回應格式，屬 TASK-025 的 API 設計） | 已實作並記錄（TDD 紀錄 Cycle 3） |
| A-2 | 範圍 | advisory | `fetch` 一次只回傳「一個月」的日線，不是連續 N 根；跨月歷史需多次呼叫 | 報告與 SPEC 未要求跨月；若要支援，需定義「往回抓幾個月」與月份對齊規則並變更 Spec | 延後（已記於 TDD 紀錄） |
| A-3 | 跨 Task 缺口（沿用 TASK-013 的 A-1） | advisory（需在後續 Task 處理） | `monitor.py`／`cli.py` 仍未依 `Instrument.source_id` 分派來源；本張的 `twse` 來源目前沒有任何呼叫端（`cli._local_cache_fetch` 固定用 csv） | 同 TASK-013 A-1：把來源分派與逐商品 `data_source` 明確編入 TASK-025（或 TASK-037 的整合項），並更新其「預計觸及的檔案」 | 待辦（已記於 `STATE.md` 待決事項） |
| A-4 | 未測保證 | advisory | 本張不含快取（AC-032 未要求），因此 TWSE 每次都發請求；真實端點未重跑（全部用合成假回應） | 快取與來源鏈屬 TASK-025 的整合；真實端點實測已有 2026-09-24 存證，若 TASK-037 要重跑需另行取得同意 | 已記錄（TDD 紀錄「未執行或受阻」） |
| A-5 | 一致性 | advisory | `search`／`fetch` 的 `limit` 假設為整數（與 `BinanceSource.search` 相同）；從 HTTP 查詢字串進來的值需由呼叫端轉型 | TASK-025 的端點在解析 query 參數時必須轉成 int 並以 `ConfigError`／400 回應非法值 | 待辦（TASK-025） |
| A-6 | 流程紀律 | advisory（非程式） | 初稿測試留下兩個佔位／同義反覆斷言（`pytest.approx(0)`、`x == x`），在第一次執行前即自行改為真斷言；另有一個測試漏寫 `date` 參數造成假失敗 | 維持「先寫測試、先讀過一次斷言再跑」的習慣 | **已記載**：TDD 紀錄 Cycle 1／Cycle 3 如實記錄 |

## 修正與重審

- 第 1 輪：Spec Review 兩個 AC 逐條符合；品質 Review 無 blocking。
- 依變異檢查修正 1 處（`limit=None` 的夾具寬度）與依實測修正 1 處（`search` 的期望值）；另把 `_default_client` 的區域匯入提升到模組層以與 `crypto.py` 一致，並在最終版檔案上重跑變異矩陣。
- 重審：重跑單檔（58 passed）、相關回歸（88 passed）與全套（353 passed）；重讀 `twse.py` 複查欄名對照、四層檢核、錯誤轉譯、`limit` 語意與兩端點合併邏輯。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-032／AC-033 逐條符合）
- 品質 Review：passed（無 blocking；A-3 需在後續 Task 落實，其餘為延後或已記錄的 advisory）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（需 TASK-025 的 API 設計）、A-2（需變更 Spec）、A-3（TASK-025／037）、A-4（需使用者同意連外）、A-5（TASK-025）、A-6（流程記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：無快取；一次只取一個月；搜尋需兩個端點都成功；真實端點未重跑；上櫃（TPEx）不在範圍
