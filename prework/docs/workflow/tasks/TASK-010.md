# TASK-010：監控設定、輪詢、提醒去重、錯誤隔離與提醒輸出

- id：TASK-010
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-022","AC-023","AC-024","AC-025","AC-026"]
- depends_on：["TASK-008"]
- test_evidence：["docs/workflow/tdd/TASK-010.md"]
- review_evidence：["docs/workflow/reviews/TASK-010.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`ediaad.monitor.load_config(path)` 讀入監控 JSON 並驗證後回傳 `Watchlist`（`poll_interval_seconds`、`events_path`、`cache_dir`、`pattern_id`、`pattern_spec`、`horizon`、`instruments`），五種壞設定（缺鍵、未知鍵、型別錯、`instruments` 為空、週期不合法）各自丟出 `ConfigError` 並指出出錯的鍵或索引位置，且 `pattern_spec` 提供時其 `pattern_id` 必須與頂層 `pattern_id` 一致；`run_once(watchlist, fetch, emit, warn, state, ...)` 逐商品取得序列、檢查長度、`patterns.detect` 偵測、`outlook.forward_stats(..., end_attr="recovery_index")` 統計歷史表現，只對未提醒過的事件發出提醒，回傳 `RunResult`（`processed`、`alerted`、`skipped`、`warnings`）；提醒去重鍵為（商品, 週期, 規律 ID, 事件開始時間），同一事件連續三輪的提醒次數為 1、0、1；單一商品失敗只記 warning 而其他商品仍發出提醒，非領域的程式錯誤向上拋出而非被吞掉；序列長度小於 `range_bars_min + 1` 的商品計入 `skipped` 並附「資料不足」warning，不與「評估後無命中」混為一談；`format_alert` 產生欄位順序固定的單行摘要，`append_event` 以附加寫入 JSONL、含九個欄位且不改寫既有行。
- 本張不做：不做 CLI 子命令、`--once` 與 exit code 語意（TASK-011）；不做 SQLite 落地與跨程序去重（TASK-018，本張的 `AlertState` 為記憶體內去重）；不做設定檔原子寫入（TASK-019）；不做通知管道（網頁 SSE、瀏覽器原生、服務端桌面）；不做網頁、排程與服務生命週期；不實作任何真實資料來源（`fetch` 一律由呼叫端注入）。
- 每個 AC 在本張負責的範圍：AC-022 全部（合法設定回傳 `Watchlist`、五種壞設定與 `pattern_spec` 身分一致性的 `ConfigError`）；AC-023 全部（連續三輪提醒次數 1／0／1、去重鍵內容）；AC-024 全部（單商品 `SourceError` 只記 warning、其他商品仍提醒、`RunResult` 四個計數正確、非領域程式錯誤上拋）；AC-025 全部（長度不足計入 `skipped` 並附「資料不足」warning、與「無命中」分開）；AC-026 全部（單行摘要欄位順序固定、JSONL 附加寫入與九個欄位、重複附加不破壞既有行）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-022～AC-026、第 5 節模組表中 `ediaad/monitor.py` 一列（`Instrument`、`Watchlist`、`AlertState`、`RunResult`、`load_config`、`run_once`、`run_forever`、`format_alert`、`append_event`、`event_times`）、第 5 節原則 2（外部效果一律可注入）與原則 3（錯誤分層：只攔截領域錯誤與來源畸形資料）、第 5 節「其他結構」的 `Instrument`／`Watchlist`／`RunResult`／`AlertState`、第 5 節「輸入／輸出、驗證與錯誤格式」的 `load_config` 驗證條目、第 7 節測試策略第 7 列；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F10／F11／F12、第 4.1 節原則 2 的注入參數表與原則 3 的例外清單、第 4.3 節 `monitor.py`、第 4.4 節 `Watchlist` 與 `RunResult`、第 4.5 節資料流 B、第 5.9 節（去重鍵用時間而非索引的理由、v0.2 只在記憶體的限制）；`docs/workflow/CONTEXT.md`「提醒去重鍵」（與「重疊抑制」不同）、「提醒（alert）」「信心值」。
- 模組與公開介面：新增 `ediaad/monitor.py`，公開 `Instrument`（`symbol`、`interval`；SPEC 另列 `source_id`、`display_name`，本張只實作契約所需欄位，實作前重新查證第 5 節）、`Watchlist`、`AlertState`（`seen` 集合 ＋ `should_alert(key)`／`mark_alerted(key)`）、`RunResult`、`load_config(path) -> Watchlist`、`run_once(watchlist, fetch, emit, warn, state, sleep=None, should_stop=None) -> RunResult`、`run_forever(...)`（以注入的 `sleep`／`should_stop` 重複呼叫 `run_once` 的最小迴圈，不新增 SPEC 未定義的語意）、`format_alert(...) -> str`、`append_event(path, event) -> None`、`event_times(...)`（由事件取得去重所需的時間鍵）。`run_once` 只攔截 `(EdiaadError, KeyError, IndexError)`；`format_alert` 的單行摘要欄位順序為 `[ALERT] <symbol> <interval> <pattern_id> <start>..<end> confidence=<c> history_up_prob=<p> samples=<n>`；`append_event` 的九個欄位為 `symbol`、`interval`、`pattern_id`、`event_start_time`、`event_end_time`、`confidence`、`detected_at`、`history_up_probability`、`history_samples`（依報告第 3.1 節 F12）。
- 預計觸及的檔案：`ediaad/monitor.py`、`tests/test_monitor.py`；實作前重新查證（重用 TASK-006 的 `ediaad/outlook.py`、TASK-007／TASK-008 的 `ediaad/patterns.py`、TASK-002 的 `ediaad/errors.py` 與 Series 契約；`ALLOWED_INTERVALS` 的來源依 SPEC 第 5 節與 AC-030 改由各來源查詢，本張不得建立全域唯一清單作為長期依據）。
- 必要環境／依賴：TASK-001 的 `.venv`（`numpy`、`pandas`、`pytest`）；測試以注入的假 `fetch`／`emit`／`warn`／可控時鐘與 `tmp_path` 事件檔進行，完全離線、不需網路、不需真實來源。

## 測試計畫

- 測試公開邊界：只呼叫 `ediaad.monitor.load_config`、`run_once`、`format_alert`、`append_event` 並觀察回傳的 `Watchlist`／`RunResult`、`emit` 被呼叫的次數與內容、`warn` 收到的訊息，以及事件檔的逐行內容；假 `fetch` 以閉包或小型類別注入，不 mock 私有函式。
- 第一個失敗行為與預期斷言：`ediaad/monitor.py` 尚未存在時，於專案根執行 `.venv/bin/python -m pytest tests/test_monitor.py -q` 預期 collection error（`ModuleNotFoundError: No module named 'ediaad.monitor'`）；實作後第一個綠燈斷言為「`load_config(合法設定檔)` 回傳 `Watchlist`，且 `watchlist.instruments[0].symbol` 與設定檔內容相同」。
- 後續例外／邊界情境：五種壞設定各自 `pytest.raises(ConfigError)` 並以 `match=` 斷言訊息含出錯鍵名或索引位置（缺鍵、未知鍵、型別錯如 `poll_interval_seconds` 給字串、`instruments` 為空陣列、週期不合法如 `"2h"`）；`pattern_spec` 的 `pattern_id` 與頂層 `pattern_id` 不一致時 `ConfigError`；三輪 `run_once` 以假 `fetch` 與可控時鐘餵入「第 1 輪事件 E1、第 2 輪同一 E1、第 3 輪新事件」，斷言 `[r.alerted for r in results] == [1, 0, 1]` 且 `emit` 收到的去重鍵為 `(symbol, interval, pattern_id, 事件開始時間)`；單一商品 `fetch` 丟 `SourceError` 時斷言另一商品仍 `emit`、`RunResult.alerted` 正確、warnings 只記該商品，且 `processed`／`skipped` 計數與輸入商品數一致；`fetch` 丟 `ValueError` 這類非領域錯誤時以 `pytest.raises(ValueError)` 斷言向上拋出（不得被轉成 warning）；以長度小於 `range_bars_min + 1` 的序列斷言該商品計入 `skipped` 且 `warn` 收到含「資料不足」的訊息，並斷言這與「評估後無命中」（`processed` 增加、`alerted` 與 `skipped` 不變）可區分；`format_alert` 以固定事件斷言輸出為單行且欄位順序與報告第 3.1 節 F12 一致；`append_event` 連續附加三次後斷言檔案每一行都是合法 JSON、九個欄位齊全、且先前行的內容逐字不變。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_monitor.py -q`；相關回歸為專案根執行 `.venv/bin/python -m pytest tests/test_outlook.py tests/test_patterns_detect.py tests/test_monitor.py -q` 與全套 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的執行指令表。
- 非程式任務的替代驗證與理由：不適用（本張為程式任務，所有外部效果皆可注入，時間與來源都能控制，能以 pytest 完全離線斷言，無需替代驗證）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-009 的交付物（全套 162 passed）；本次新增 `ediaad/monitor.py` 與 `tests/test_monitor.py`（開工時以 `find . -type f -not -path "./.venv/*" | sort` 與逐檔 sha256 建立快照；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（預計 `docs/workflow/tdd/TASK-010.md`）
- Review 紀錄位置：見上方 review_evidence（預計 `docs/workflow/reviews/TASK-010.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-monitor` sha256:9916447ac2b5ee5952ec372e470005f4dde834718a905474213e0c26bc3cf376（原始碼樹）；本張交付 `ediaad/monitor.py` `72df2ba2…`、`tests/test_monitor.py` `25699991…`；全套 `187 passed`
- 取消、重開或變更原因：無
