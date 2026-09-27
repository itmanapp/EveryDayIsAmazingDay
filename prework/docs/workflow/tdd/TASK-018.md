# TASK-018 測試紀錄

- task_id：TASK-018
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-store sha256:ffabbf0e4351132738988d8571f3d1deb567b30ebb6284338a8d3a9c4ec3f39d
- alternative_reason：無（SPEC 第 7 節明定 `ediaad.store` 必須以真實 SQLite 驗證，不能只對 mock 宣稱通過；本張全部使用 `tmp_path` 的真實資料庫檔與真實 `subprocess`）
- Task／Spec 版本：TASK-018 / SPEC-001 v0.4
- 測試邊界：`open_store` 開啟 `tmp_path` 下的真實資料庫，觀察 `record_event`／`query_events`／`mark_alerted`／`seen_keys`／`is_alerted`／`should_alert`／`put_lease`／`get_lease`／`close` 的行為與**重啟後**（新 `Store` 實例、另一個 `subprocess`）的結果；以檔案與公開方法為觀察邊界。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-017 的交付物，全套 **519 passed**（本張完成後為 552 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/store.py` | `9247a2a0` | 新增：`Store`、`open_store`（事件／提醒狀態／租約快取三張表） |
| `tests/test_store.py` | `2e9a4aca` | 新增：33 個測試（含 2 個真實 `subprocess` 跨程序案例） |

## Cycle 1：開檔、建表、事件與提醒狀態（AC-039，真實 Red → Green）

- 測試：開啟空資料庫即建表且 `seen_keys()` 為空；自動建立父目錄；事件寫入後查回**逐欄相同（含型別）**；同一去重鍵重複寫入為更新而非重複列；事件缺欄位／商品為空白各自 `DataFormatError`；`mark_alerted` 幂等且 `seen_keys`／`is_alerted` 正確；去重鍵長度或內容不合法時 `DataFormatError`；**先後兩個 `Store` 實例（模擬重啟）第二次必須看到第一次的提醒**；`AlertState(seen=set(store.seen_keys()))` 對同一事件 `should_alert` 為 `False`；**另一個 Python 程序**開啟同一檔案後 `should_alert` 為 `False`，共 13 個（其中 3 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_store.py -q` | 1 | `13 failed`：`ModuleNotFoundError: No module named 'ediaad.store'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `13 passed in 2.15s` | snap-2026-09-24-ocaievo-store／2026-09-24 |

- 實作：`_SCHEMA`（`events`／`alerts`／`leases` 三張表；`events` 以（商品, 週期, 規律 ID, 事件開始時間）為主鍵，另存**正規化 UTC** 的 `event_start_at` 供區間查詢）、`_validate_event`（九個欄位的型別驗證）、`_require_key`（四項去重鍵）、`open_store`（建立父目錄、建表）、`Store`（`record_event` 用 `ON CONFLICT DO UPDATE`、`mark_alerted` 用 `INSERT OR IGNORE`、`query_events`、`seen_keys`、`is_alerted`、`should_alert`、租約快取、`close` 與 context manager）。
- **`AlertState` 與 `run_once` 完全沒有被修改**（TASK-018 的邊界要求）。跨程序去重的接法就是 `AlertState(seen=set(store.seen_keys()))`——鍵定義與 TASK-010 完全相同，因此不需要動核心邏輯。有一個測試專門固定這件事。
- **去重鍵仍用「原始 ISO 字串」**（TASK-010 的定義），因此「同一個瞬間但不同字串格式」會被視為不同事件；`event_start_at` 只用於**區間查詢**的比較。已在 docstring 與 Review 說明。
- **如實記載的兩處我的錯誤**：
  1. `query_events` 第一版用 `SELECT *` ＋ 依位置對應 `EVENT_FIELDS`，但 `events` 表中間多了 `event_start_at`，造成欄位整體位移（`event_end_time` 變成時間、`confidence` 變成 `confidence` 的鄰居…）。**這正是本專案一再警惕的「靠位置對應」**（TWSE 解析、F-001）；已改為明確列出欄位並以 `cursor.description` 的**欄名**組 dict。
  2. 跨程序測試的短腳本原本寫 `sorted(sorted(k) for k in seen_keys())`，把**鍵內部**也排序了，斷言因此失敗。已改為 `sorted(list(k) for k in ...)`（保留鍵內部順序）。

## Cycle 2：強健性（損毀檔、WAL、並行、租約快取與查詢邊界，真實 Red → Green）

- 測試：查詢依商品篩選；**起訖端點都含在區間內**、區間外的回空清單；排序（時間升冪，同時間再依商品）；**時區正規化的三種方向**（正偏移且 UTC 較早→命中、負偏移且 UTC 較晚→命中、正偏移但 UTC 早於起點→不命中）；非 ISO／無時區的時間各自 `DataFormatError`；租約快取的往返與覆寫；**損毀的資料庫檔（三種）得到可讀的 `DataFormatError` 而非 sqlite3 原始例外**；0 位元組的檔案被視為**全新資料庫**並初始化；兩個連線先後寫入都不遺失；`journal_mode == "wal"`；`close()` 幂等且可重新開啟；離開 context manager 後狀態仍在；**另一個程序寫入的事件與提醒狀態**在主程序可見；**已關閉的 store 的每個入口都給出可讀的 `ConfigError`**，共 20 個（其中 7 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `4 failed`：三種損毀檔案例（`sqlite3.DatabaseError` 直接外洩）＋ `Store` 沒有 `journal_mode` | 同上／2026-09-24 |
| Green | 同上 | 0 | `30 passed in 4.07s` | 同上／2026-09-24 |

- 實作：`BUSY_TIMEOUT_SECONDS`／`BUSY_TIMEOUT_MS`、`PRAGMA journal_mode=WAL` ＋ `PRAGMA busy_timeout`、把 `sqlite3.DatabaseError` 轉譯成含路徑的 `DataFormatError`（並關閉連線）、`Store.journal_mode` 屬性。
- **「空檔案」是我的測試期望寫錯，不是實作錯**：SQLite 把 0 位元組的檔案視為全新的資料庫（例如中斷的下載留下的檔案），因此正確行為是**初始化它**而不是報錯。已把該案例從「損毀」移到「初始化」並補一個正向測試。
- **WAL 的代價（如實記載）**：WAL 會在資料庫旁產生 `ediaad.db-wal`／`ediaad.db-shm` 兩個 sidecar 檔。這是 SQLite 的正常行為，且 `.gitignore` 已忽略 `*.db`（但**沒有**忽略 `-wal`／`-shm`）；已列為 Review 的 advisory。

## Cycle 3（補測）：把 `assert` 換成明確的領域錯誤

- 檢查狀態空間時發現：我在 7 處用 `assert self._connection is not None` 當控制流程。**`assert` 在 `python -O` 下會被整段移除**，屆時會變成對 `None` 呼叫方法的 `AttributeError`（不可讀的 traceback）。已改為 `_connection_or_raise()` 丟出 `ConfigError("store（…）已關閉，無法再存取")`，並補一個測試逐一走過每個入口（`seen_keys`／`query_events`／`record_event`／`mark_alerted`／`get_lease`／`journal_mode`）。
- 這同時讓「`close()` 真的關閉連線」變成**可觀測**的行為（變異 M12 因此被抓到）。
- 測試數 30 → 31。

## Cycle 4（補測）：讓 M8 可被偵測

- 首次變異檢查中 **M8（區間查詢改用原始字串比較 `start`）存活**。原因：我原本的時區測試只有一個方向，而那個方向在原始字串比較下**剛好也成立**。已把測試改成**參數化的三個方向**，其中兩個方向會讓「原始字串比較」與「正規化 UTC 比較」得到**相反的結論**（負偏移且 UTC 較晚、正偏移但 UTC 早於起點）。M8 立刻被抓到。
- 這與 TASK-016 的 M6 同型：**不是等效變異，是測試覆蓋的方向不足**。
- 測試數 31 → 33。

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | `mark_alerted` 不用 `OR IGNORE` | 被抓到 |
| M2 | `seen_keys` 少回傳一個欄位 | 被抓到 |
| M3 | 事件不用 upsert | 被抓到 |
| M4 | 不驗證事件欄位 | 被抓到 |
| M5 | 去重鍵不檢查長度 | 被抓到 |
| M6 | 不檢查時區 | 被抓到 |
| M7 | 區間查詢不含結束端點 | 被抓到 |
| M8 | 區間查詢不比對正規化時間 | **首次存活 → 補三個方向的時區案例後被抓到** |
| M9 | 不篩選商品 | 被抓到 |
| M10 | 不啟用 WAL | 被抓到 |
| M11 | 不建 `alerts` 表 | 被抓到 |
| M12 | `close()` 什麼都不做 | 被抓到 |
| M13 | 不建立父目錄 | 被抓到 |
| M14 | 不轉譯損毀檔的錯誤 | 被抓到 |
| M15 | 查詢不排序 | 被抓到 |
| M16 | `put_lease` 不用 `REPLACE` | 被抓到 |
| M17 | `get_lease` 缺鍵回空字串 | 被抓到 |
| M18 | 關閉後的使用不明確報錯 | 被抓到 |

工具紀律：整行比對、`count(frm) == 1` 才執行、每次變異後立即還原並比對檔案 sha256。矩陣在**最終版檔案**上重跑過（另移除一個未使用的匯入之後），18／18 全數被抓到；還原後 `ediaad/store.py` `9247a2a0` 與變異前一致，單檔 `33 passed`。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_store.py -q` | 0（`33 passed in 4.51s`） | snap-2026-09-24-ocaievo-store |
| 相關回歸（監控，本張不改它） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_monitor.py -q` | 0（`24 passed in 0.39s`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`552 passed in 23.76s`） | 同上 |
| 未使用匯入掃描 | `ocaievo/`：AST 粗檢 `ediaad/` | 0（先抓到 `Iterable` 未使用並移除） | 同上 |
| 變異後還原驗證 | 同本張單檔 | 0（`33 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 已知邊界（記錄）：
  - **`Store` 尚未接進監控迴圈或 Web 服務**（TASK-018 明訂由 TASK-020 的 `app.py` 接線）：`cli._local_cache_fetch` 與 `_run_monitor` 仍使用記憶體 `AlertState`，因此**目前執行 `monitor` 仍是「重啟後會重複提醒」**。落地能力已具備且跨程序驗證通過，接線是 TASK-020 的工作——這是 TASK-013 以來那條跨 Task 缺口的一部分（見 Review A-1）。
  - **不匯入舊格式 `events.jsonl`**（SPEC 第 5 節「相容性／遷移」提到的首次匯入不屬 AC-039）。依 TASK-018 的邊界，這是整合階段的工作；本張的決定是**不實作**，已在此記錄，TASK-037 的整合驗收應確認是否需要。
  - 不加密資料庫；`leases` 表的欄位（`key_id`／`payload`／`fetched_at`）與 `put_lease`／`get_lease` 是本張定義的最小介面，TASK-029（租約模型）可能調整（見 Review A-2）。
  - 去重鍵用原始 ISO 字串（TASK-010 的定義）；同一瞬間但不同格式（`Z` vs `+00:00`）視為不同事件。應用內由 `monitor` 統一產生字串，因此不構成問題，但若日後有第二個寫入端，需先正規化字串。
  - WAL 會產生 `ediaad.db-wal`／`ediaad.db-shm` sidecar 檔；`.gitignore` 目前只忽略 `*.db`（見 Review A-3）。
  - 資料庫不會自動清理（報告第 8.2 節已列為已知限制）。
- 未涵蓋：把 `Store` 接進監控迴圈（TASK-020）、租約模型與驗章（TASK-029 之後）、通知管道（TASK-027）、`events.jsonl` 匯入（整合階段）。
