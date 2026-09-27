# TASK-018：SQLite 落地與跨程序提醒去重

- id：TASK-018
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-039"]
- depends_on：["TASK-010"]
- test_evidence：["docs/workflow/tdd/TASK-018.md"]
- review_evidence：["docs/workflow/reviews/TASK-018.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：對一個空的 SQLite 資料庫寫入一次命中事件與其提醒狀態後結束程序，再以新的程序實例開啟同一個資料庫並查詢同一事件時，該事件被判定為已提醒（不再重複提醒），也就是去重跨程序有效；去重鍵為（商品, 週期, 規律 ID, 事件開始時間）。事件落地後可依商品與時間區間查詢，且查詢結果的欄位與寫入值一致。
- 本張不做：不修改 `monitor.run_once`／`AlertState` 的核心邏輯或去重鍵定義（TASK-010 已定案，本張只提供落地實作）；不把 `Store` 接進監控迴圈或 Web 服務（TASK-020 的 `app.py` 負責接線）；不匯入舊格式 `events.jsonl`（`docs/workflow/SPEC.md` 第 5 節「相容性／遷移」提到的首次匯入不屬 AC-039，另於整合階段處理並在 TDD 記錄決定）；不實作通知管道（TASK-027）；不加密資料庫；不執行 git 或任何對外動作。
- 每個 AC 在本張負責的範圍：AC-039 全部（空資料庫建立、事件與提醒狀態寫入、重啟程序後同一事件不重複提醒、事件依商品與時間查詢）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-039、第 5 節模組表（`ediaad/store.py` 的 `Store`、`open_store`、`record_event`、`seen_keys`、`mark_alerted`、`query_events`）、第 5 節資料契約的 `AlertState`（`seen` ＋ `should_alert`／`mark_alerted`）與資料生命週期（`$EDIAAD_HOME/ediaad.db`，事件永久累積）、第 7 節測試策略（`ediaad.store` 以真實 SQLite 暫存檔做整合測試，不能只對 mock 宣稱通過）；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F11（去重鍵的定義與理由：用時間而非索引）、第 4.5 節資料流 B、第 6.1 節（`store.py` 職責：事件、提醒狀態、租約快取）。
- 模組與公開介面：新增 `ediaad/store.py`（`Store`（支援 context manager 關閉）、`open_store(path)`、`record_event(...)`、`seen_keys(...)`、`mark_alerted(...)`、`query_events(symbol=None, start=None, end=None)`；資料表至少含事件與提醒狀態，並保留租約快取的位置）。
- 預計觸及的檔案：`ediaad/store.py`、`tests/test_store.py`；實作前重新查證。
- 必要環境／依賴：`.venv`（TASK-001，使用標準庫 `sqlite3`，不新增依賴）；TASK-010 的 `AlertState` 與去重鍵定義已完成；測試以 `tmp_path` 的真實 SQLite 檔與真實檔案系統執行，全程離線；跨程序情境以 `subprocess` 執行 `.venv/bin/python -c ...` 的短腳本，或以先後兩個獨立 `Store` 實例模擬重啟。

## 測試計畫

- 測試公開邊界：`open_store` 開啟 `tmp_path` 下的真實資料庫檔，觀察 `record_event`／`mark_alerted`／`seen_keys`／`query_events` 的行為與重啟後的結果；以檔案與公開函式為觀察邊界，不以 mock 取代 SQLite。
- 第一個失敗行為與預期斷言：模組尚未存在時匯入失敗（`ModuleNotFoundError: No module named 'ediaad.store'`）；實作後第一個案例為跨程序去重：第一個 `Store` 對鍵 `("2330", "1d", "range_fakeout_reversion", "2024-07-01T00:00:00Z")` 呼叫 `mark_alerted` 並關閉，第二個 `Store` 開啟同一檔案後 `seen_keys()` 含該鍵，且 `AlertState` 的 `should_alert` 對同一事件為 `False`。
- 後續例外／邊界情境：對空資料庫首次開啟時自動建表且不報錯；同一鍵重複 `mark_alerted` 為幂等（不產生重複列、不拋例外）；`query_events` 依商品與時間區間查詢的邊界（含起訖端點、UTC 時間、無符合結果時回空清單）；兩個連線先後或同時寫入時的鎖定行為（busy timeout 或 WAL）且不遺失已寫入事件；資料庫檔損毀（隨機位元組）時開啟得到可讀錯誤而非 traceback；`Store` 未關閉即離開 context manager 時連線正確釋放、檔案可再次開啟。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_store.py -q`；相關回歸 `.venv/bin/python -m pytest tests/test_monitor.py -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用（持久化與跨程序去重必須以真實 SQLite 與真實程序驗證，`docs/workflow/SPEC.md` 第 7 節已明定不採用 mock）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-017 的交付物（全套 519 passed）；本次新增 `ediaad/store.py` 與 `tests/test_store.py`，**未修改 `ediaad/monitor.py`**（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-018.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-018.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-store` sha256:ffabbf0e4351132738988d8571f3d1deb567b30ebb6284338a8d3a9c4ec3f39d（原始碼樹，42 檔）；新增 `ediaad/store.py` `9247a2a0…`、`tests/test_store.py` `2e9a4aca…`；全套 `552 passed`
- 取消、重開或變更原因：無
