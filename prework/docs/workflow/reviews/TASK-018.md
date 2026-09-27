# TASK-018 Code Review

- task_id：TASK-018
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-store sha256:ffabbf0e4351132738988d8571f3d1deb567b30ebb6284338a8d3a9c4ec3f39d
- Task／Spec 版本：TASK-018 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 `assert` 改為領域錯誤、WAL sidecar 的記載與 M8 的判讀）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `ffabbf0e4351132738988d8571f3d1deb567b30ebb6284338a8d3a9c4ec3f39d`；本張新增 `ediaad/store.py` `9247a2a0…`、`tests/test_store.py` `2e9a4aca…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的已提交、未提交、新增檔案：上述兩個檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：**`ediaad/monitor.py` 完全未修改**（TASK-018 的邊界要求「不修改 `run_once`／`AlertState` 的核心邏輯或去重鍵定義」；雜湊 `6259c366…` 與 TASK-012 時一致）
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-039、第 5 節模組表（`ediaad/store.py`）、資料契約的 `AlertState`（`seen` ＋ `should_alert`／`mark_alerted`）、資料生命週期（`$EDIAAD_HOME/ediaad.db`、事件永久累積）、「相容性／遷移」（`events.jsonl` 首次匯入）、第 7 節測試策略（`ediaad.store` 以真實 SQLite 暫存檔做整合測試，不能只對 mock 宣稱通過）、第 6 節品質需求（可靠性：事件去重跨程序有效）；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F11（去重鍵的定義與理由）、第 4.5 節資料流 B、第 6.1 節（`store.py` 職責）、第 8.2 節第 1 點；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-039 | `ediaad/store.py`（`open_store`／`Store`）；`tests/test_store.py` 33 個案例 | 符合 | A-1、A-2、A-3、A-4（advisory） |

逐條核對：

- **AC-039「空 SQLite 資料庫」**：`test_opening_an_empty_database_creates_the_schema` 對 `tmp_path` 下**不存在**的檔案開啟即建表並可寫入；0 位元組的既有檔案也被初始化（SQLite 語意）。符合。
- **AC-039「寫入事件與提醒狀態後重啟程序」**：兩種重啟都測了——先後兩個 `Store` 實例，以及**另一個 `subprocess`**（讀與寫各一個測試）。符合。
- **AC-039「重啟後同一事件不重複提醒（跨程序去重）」**：第二個實例與另一個程序對同一去重鍵的 `should_alert` 都是 `False`；`AlertState(seen=set(store.seen_keys()))` 的接法有專門測試。符合。
- **AC-039「事件可依商品與時間查詢」**：`query_events(symbol, start, end)` 的篩選、**含起訖端點**、排序、時區正規化與空結果都有斷言；回傳值與寫入值**逐欄相同（含型別）**。符合。

## 品質 Review

- **零侵入的跨程序去重（本張最重要的品質決定）**：`AlertState` 與 `run_once` **一行都沒有改**。去重鍵的定義（TASK-010／報告 F11）在 store 與 monitor 之間完全相同，因此接法是 `AlertState(seen=set(store.seen_keys()))`——落地能力不需要滲進監控邏輯，`monitor.py` 的雜湊可以逐字比對確認未變。這也讓 TASK-020 的接線是一行而不是一次重構。
- **「同一份資料只有一條路徑」的貫徹**：`events` 表**不重寫**一套事件欄位定義，而是 `from .monitor import EVENT_FIELDS`（唯讀匯入常數，無循環：monitor 不匯入 store）。九個欄位的權威來源因此只有一處。代價是 store→monitor 的同層匯入，已列為 A-4 供日後抽出共用模組時處理。
- **`query_events` 用欄名而不是位置取值**：第一版用 `SELECT *` ＋ 依位置對應 `EVENT_FIELDS`，因為表中間多了 `event_start_at` 而整體位移（我的測試立刻抓到）。已改為明確列出欄位並以 `cursor.description` 組 dict——日後新增欄位也不會位移。**這正是本專案反覆強調的教訓**（TWSE 解析、F-001：位置對應是靜默錯誤的來源）。
- **正規化時間只用於比較，原始字串才是身分**：去重鍵依 TASK-010 的定義用原始 ISO 字串（同一個瞬間的 `Z` 與 `+00:00` 是不同鍵）；另存 `event_start_at`（正規化 UTC）專供區間查詢。這個分工讓「回傳值與寫入值逐欄相同」與「跨時區查詢正確」同時成立。M8 的判讀（見下）證明這條分工有被測試守住，而且是**三個方向**的。
- **`assert` 不是控制流程（本張最重要的修正）**：七處 `assert self._connection is not None` 在 `python -O` 下會整段消失，屆時變成對 `None` 呼叫方法的 `AttributeError`。已改為 `_connection_or_raise()` 丟出 `ConfigError("store（…）已關閉，無法再存取")`，並補測試逐一走過所有入口。附帶好處是「`close()` 真的關閉連線」變成可觀測（變異 M12 因此被抓到）。
- **損毀檔的錯誤分層**：`sqlite3.DatabaseError` 被轉譯成含路徑的 `DataFormatError`（本機檔案問題 → exit 2），與 `data.load_csv`／`markets.catalog.load_catalog` 一致；轉譯時關閉連線避免洩漏 fd。0 位元組檔案**不是**損毀（SQLite 視為新資料庫）——這一點我原本的測試寫錯，實作才是對的。
- **並行寫入的策略明確且有測試**：`PRAGMA journal_mode=WAL` ＋ `busy_timeout` 讓「一個程序在讀」時仍可寫、短暫鎖等待而不立刻失敗；`journal_mode` 屬性讓策略可被斷言（不是只靠註解）。兩個連線先後寫入都不遺失有測試。
- **M8 的判讀（測試方向不足，不是等效變異）**：M8（區間查詢的 `start` 改用原始字串比較）存活，因為我原本只測了一個時區方向，而那個方向在原始字串比較下**剛好也成立**。已改成三個方向，其中兩個會讓兩種比較得到**相反的結論**。與 TASK-016 的 M6 同型：**先判讀、再補測試**，不宣布等效。
- **測試品質**：跨程序用真實 `subprocess`（不是模擬）；失敗路徑同時斷言狀態與「資料未受損」；幂等性（`mark_alerted`、`close`、重複 `record_event`）各有案例；型別一致性（`history_samples` 回傳 int、`confidence` 回 float）有斷言。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 缺口（沿用 TASK-013 A-1～017 A-1） | advisory（**需在後續 Task 處理**） | `Store` 尚未接進監控迴圈：`cli._run_monitor` 仍用記憶體 `AlertState`，因此**現在執行 `monitor` 仍是「重啟後重複提醒」**——AC-039 要求的落地能力已具備並跨程序驗證，但產品行為還沒改變 | TASK-020 的 `app.py` 接線時，把 `run_once` 的 `state` 換成由 `Store.seen_keys()` 補齊的 `AlertState`；`run_once` 的 `emit` 回呼改為同時寫入 `Store.record_event`。連同來源分派／市場別預設／日曆／除權息／金鑰狀態／catalog 狀態一起編入 TASK-025（或 TASK-037 整合項） | 待辦（已記於 `STATE.md` 待決事項） |
| A-2 | 介面補充 | advisory（需追認） | `leases` 表的欄位與 `put_lease`／`get_lease` 是本張定義的最小介面（SPEC 只說「保留租約快取的位置」）；`is_alerted`／`should_alert`／`journal_mode` 亦為 SPEC 未列出的方法 | TASK-029（租約模型）確認欄位是否足夠（可能需要 `expires_at` 或 `machine`）；若確認不足則調整並更新 SPEC 第 5 節 | 待辦（TASK-029） |
| A-3 | 產物與版控 | advisory | WAL 會產生 `ediaad.db-wal`／`ediaad.db-shm` sidecar 檔；`.gitignore` 只忽略 `*.db` | 在 `.gitignore` 補 `*.db-wal`／`*.db-shm`（一行；本張未改 `.gitignore` 以免與 TASK-037 的交付檢查重工） | 待辦（TASK-037 或下次 `.gitignore` 調整時） |
| A-4 | 模組耦合 | advisory | `store.py` 匯入 `monitor.EVENT_FIELDS`（同層匯入，無循環）——九個欄位的定義只有一處是優點，但同層耦合是缺點 | 當第三個消費端出現（例如通知或網頁）時，把 `EVENT_FIELDS` 抽到更低的共用模組（或 `data.py` 旁的新模組），兩邊都從那裡匯入 | 延後（目前只有兩個消費端，抽模組的成本大於收益） |
| A-5 | 舊格式匯入 | advisory（**已決定不實作**） | SPEC 第 5 節「相容性／遷移」提到「首次啟動時若存在舊 `events.jsonl` 則匯入一次並記錄」；TASK-018 的邊界說不屬 AC-039 | 於 TASK-037 的整合驗收確認是否需要（本張記錄決定：不實作） | 待辦（TASK-037 確認） |
| A-6 | 流程紀律 | advisory（非程式） | `query_events` 第一版靠位置對應；跨程序腳本的排序寫錯；`assert` 當控制流程；M8 需補測試方向 | 已全部在 TDD 紀錄如實記載並修正 | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-039 逐條符合；品質 Review 無 blocking。
- 依 Review 與補測修正 3 處：`query_events` 改為依欄名取值（修正欄位位移）；`assert` 改為 `_connection_or_raise()`（`python -O` 安全）；時區測試補成三個方向（M8）。
- 移除 1 個未使用的匯入（`Iterable`）並在最終版檔案上重跑變異矩陣（18／18 全數被抓到）。
- 重審：重跑單檔（33 passed）、相關回歸（24 passed，確認 `monitor.py` 未受影響）與全套（552 passed）；重讀 `store.py` 複查 schema、鍵定義、正規化比較、失敗轉譯與連線生命週期。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-039 的四項宣稱逐條符合）
- 品質 Review：passed（無 blocking；A-1 需在後續 Task 落實，其餘為待追認、待辦或已記錄）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-020／025／037）、A-2（TASK-029）、A-3（TASK-037）、A-4（等第三個消費端）、A-5（TASK-037 確認）、A-6（流程記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：尚未接進監控迴圈（產品行為未變）；不匯入舊 `events.jsonl`；`leases` 介面待 TASK-029 確認；不加密；WAL sidecar 檔未加入 `.gitignore`；資料庫不自動清理
