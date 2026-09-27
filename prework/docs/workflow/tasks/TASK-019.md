# TASK-019：設定解析與原子寫入

- id：TASK-019
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-040"]
- depends_on：["TASK-010"]
- test_evidence：["docs/workflow/tdd/TASK-019.md"]
- review_evidence：["docs/workflow/reviews/TASK-019.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：對一份合法設定呼叫 `save_settings_atomic(path, settings)` 時，以「同目錄暫存檔＋`os.replace`」完成寫入，寫入後檔案內容等於新設定、目錄不留下暫存檔，且任何時刻讀到的檔案都是完整內容（不會是半寫狀態）；對一份損毀設定（非 JSON、空檔案或型別不符）呼叫 `load_settings(path)` 時丟出 `ConfigError` 並回報可讀訊息，且**不覆蓋原檔**——原檔位元組完全不變、內容保留。`DEFAULT_SETTINGS` 提供可用的預設鍵集，缺值時的行為明確定義。
- 本張不做：不實作網頁的設定端點與儲存按鈕（TASK-020、TASK-025，本張只提供可被它們呼叫的函式）；不改變 `monitor.load_config` 對 `watchlist.json` 的既有鍵集與錯誤語意（TASK-010，本張不重複實作其驗證）；不寫入或讀取 `keys.json`（金鑰存放與隔離為 TASK-016）；不實作設定版本遷移；不執行 git 或任何對外動作。
- 每個 AC 在本張負責的範圍：AC-040 全部（合法設定以暫存檔＋rename 原子寫入、損毀設定不覆蓋原檔並回報錯誤且保留原內容）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-040、第 5 節模組表（`ediaad/config.py` 的 `load_settings`、`save_settings_atomic`、`DEFAULT_SETTINGS`）、第 5 節「輸入／輸出、驗證與錯誤格式」（缺鍵、未知鍵、型別錯誤 → `ConfigError`，訊息指出鍵名或索引位置）與資料生命週期（`$EDIAAD_HOME/settings.json`）、第 6 節品質需求（可靠性：設定與 catalog 以原子寫入避免半寫狀態）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.1 節（`config.py` 職責：設定解析＋驗證＋原子寫入）、第 6.3 節（網頁層只做參數解析與錯誤轉譯，不重實作邏輯）；`docs/workflow/PROJECT.md` 的環境變數（`EDIAAD_HOME`）。
- 模組與公開介面：新增 `ediaad/config.py`（`load_settings(path)`、`save_settings_atomic(path, settings)`、`DEFAULT_SETTINGS`，以及內部使用的暫存檔命名與 `os.replace` 流程；驗證錯誤一律 `ConfigError` 並指出出錯鍵名）。
- 預計觸及的檔案：`ediaad/config.py`、`tests/test_config.py`；實作前重新查證。
- 必要環境／依賴：`.venv`（TASK-001，只用標準庫 `json`、`os`、`tempfile`，不新增依賴）；TASK-010 的 `ConfigError` 與設定鍵集已完成；測試以 `tmp_path` 的真實檔案系統執行，全程離線。

## 測試計畫

- 測試公開邊界：對 `tmp_path` 下的真實設定檔呼叫 `load_settings`／`save_settings_atomic`，以檔案位元組、目錄內容與例外型別為觀察邊界；不檢視私有暫存檔命名常數。
- 第一個失敗行為與預期斷言：模組尚未存在時匯入失敗（`ModuleNotFoundError: No module named 'ediaad.config'`）；實作後第一個案例為原子寫入：對合法設定呼叫 `save_settings_atomic` 後，`json.loads(path.read_text())` 等於寫入值、`sorted(p.name for p in tmp_path.iterdir())` 不含暫存檔殘留。
- 後續例外／邊界情境：損毀原檔（內容為 `{not json`、空檔案、頂層為 JSON 陣列）時 `load_settings` 丟出 `ConfigError`，且以讀取前後 `path.read_bytes()` 相等斷言原檔未被覆寫；寫入過程在 `os.replace` 之前失敗（以 monkeypatch 讓序列化或寫入拋錯）時原檔仍為舊內容且無殘留；同一目錄並發兩次寫入時使用互不衝突的暫存檔名，最終檔案為其中一份完整內容；未知鍵與型別錯誤各自 `ConfigError` 且訊息含鍵名；目標目錄不存在時的行為明確定義（建立或可讀錯誤）並以斷言固定；`DEFAULT_SETTINGS` 與 `load_settings` 對缺值檔案的補齊規則一致。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_config.py -q`；相關回歸 `.venv/bin/python -m pytest tests/test_monitor.py -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用（原子寫入與損毀保護必須以真實檔案系統與位元組比對驗證，`docs/workflow/SPEC.md` 第 7 節已明定不採用 mock）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-018 的交付物（全套 552 passed）；本次新增 `ediaad/config.py` 與 `tests/test_config.py`，**未修改 `ediaad/monitor.py`**（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-019.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-019.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-config` sha256:b2aa45bd91ccaacf93b71337c5abafa7c0838fac62bbe858aec14e00b4f328b7（原始碼樹，44 檔）；新增 `ediaad/config.py` `c2a0196a…`、`tests/test_config.py` `5c79157e…`；全套 `585 passed`
- 取消、重開或變更原因：無
