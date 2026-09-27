# TASK-030：啟用、離線啟動驗證與時鐘篡改防護

- id：TASK-030
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-052","AC-053","AC-058"]
- depends_on：["TASK-028", "TASK-029"]
- test_evidence：["docs/workflow/tdd/TASK-030.md"]
- review_evidence：["docs/workflow/reviews/TASK-030.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：
  - AC-052：`activate(key, ...)` 以注入的 HTTP 客戶端送出密鑰與機器指紋到 `POST <url>/v1/activate`，取得伺服器簽章的 30 天租約並以原子寫入落地 `$EDIAAD_HOME/lease.json`；租約欄位符合 SPEC 第 5 節租約格式（`key_id`、`machine`、`issued_at`、`expires_at`、`features`、`catalog_version`、`sig`），且 `expires_at − issued_at = 30 天`；回傳物件與落地內容一致。
  - AC-053：啟動驗證 `verify_lease(...)` 在離線狀態下完成簽章驗證（呼叫 TASK-029 的 `ed25519_verify`）、機器指紋比對、到期檢查與時鐘檢查後回可啟動；**整個啟動流程不發出任何網路請求**，以注入的計數假 HTTP 客戶端驗證呼叫次數為 0。
  - AC-058：時鐘防護兩層都生效；第一層是簽章內的 `issued_at`（系統時間 `< issued_at − 容忍值` → 回 `force_online=True` 強制線上驗證），第二層是本地 `high_water`（系統時間 `< high_water − 容忍值` → 同樣 `force_online=True`）；兩者都不得以本地時間延長授權，且在 `force_online` 時若線上驗證不可用即不得放行。
- 本張不做：不做續期、到期停止、撤銷處理與功能分級（TASK-031）；不實作 Ed25519 曲線運算本身（TASK-029）；不建立 `Lease` 資料模型與機器指紋演算法（TASK-028）；不實作 Cloudflare Worker 的 `handleActivate`（TASK-033）；不做 CLI 子命令（TASK-036）；不啟動監控迴圈、Web 服務或排程（TASK-020）；不做更新檢查（TASK-032）。
- 每個 AC 在本張負責的範圍：AC-052 全部（啟用請求、30 天租約、落地、欄位契約）；AC-053 全部（離線驗章、指紋比對、到期檢查、啟動流程零網路請求）；AC-058 全部（兩層時鐘防護與強制線上驗證的判定）。到期後的停止與導流、續期屬 AC-056（TASK-031）；本張只判定「已過期、不啟動」，不處理重新申請導流。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-052／AC-053／AC-058、第 5 節租約 JSON 格式與「資料生命週期」產物位置（`$EDIAAD_HOME/lease.json`、`$EDIAAD_HOME/keys.json` 權限 `0600`）、授權狀態（未啟用 → 已啟用 → 已過期 → 已撤銷）、錯誤分層（`ConfigError`／`SourceError`）、第 7 節測試策略列（`ediaad.license` 以官方向量＋合成租約＋假時鐘＋假 HTTP）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.4 節「三個觸發點與各自的驗證方式」（首次啟用線上、每次啟動離線且不碰網路、每次開啟／每 24 小時線上）、「時鐘篡改防護」（`issued_at` 是真防線、`high_water` 可被刪檔繞過）、「租約格式」；`docs/workflow/adr/ADR-002.md`；`docs/workflow/PROJECT.md` 環境變數 `EDIAAD_HOME`／`EDIAAD_LICENSE_URL` 與環境實測表（`/etc/machine-id` 可讀）。
- 模組與公開介面：`ediaad/license.py`（與 TASK-028、TASK-029 同一模組）新增
  - `activate(key: str, *, fingerprint: str, http, url: str, now, timeout: float = 10.0) -> Lease`：組出 `{"key": ..., "machine": ...}` 送出並回傳 `Lease`；`http` 為可注入客戶端，介面只要求 `post(url, payload, timeout) -> (status, body)`。
  - `verify_lease(lease, *, fingerprint: str, public_key: bytes, now, high_water, tolerance_seconds: int = 900) -> LeaseVerdict`：`LeaseVerdict` 至少含 `ok: bool`、`reason: str`、`force_online: bool`。
  - 時鐘水位持久化：`load_high_water(path)`／`save_high_water(path, value)`（落點在 `$EDIAAD_HOME/`，檔名與 `Lease` 序列化方式於實作前與 TASK-028 對齊後定案）。
  - 絕不使用 `datetime.now()`；時間一律由 `now` 參數注入（符合 SPEC 第 5 節原則 2「外部效果一律可注入」）。
- 預計觸及的檔案：`ediaad/license.py`、`tests/test_license_activate.py`、`tests/test_license_startup.py`、`tests/_ed25519_fixture.py`（測試專用純 Python 簽章夾具，以 RFC 8032 的 secret key 產生合成租約簽章；只存在於測試、不進 `ediaad/`、不引入 `cryptography`）；實作前重新查證。
- 必要環境／依賴：`.venv`＋`pytest`；`tmp_path` 充當 `$EDIAAD_HOME`；假 HTTP 客戶端（可計數、可強制回 200／403／逾時／拋 `SourceError`）；固定時鐘值；全程離線，測試資料全部為合成租約。

## 測試計畫

- 測試公開邊界：只呼叫 `activate` 與 `verify_lease` 兩個公開函式；HTTP 以計數假客戶端注入、時間以固定 `now` 注入、租約檔以 `tmp_path` 觀察；授權服務不啟動真實伺服器，避免任何網路依賴。
- 第一個失敗行為與預期斷言：實作前 `from ediaad.license import activate, verify_lease` 丟 `ImportError`；首案 `test_activate_writes_signed_lease` 斷言假 HTTP 恰收到一筆 `POST <url>/v1/activate`、payload 同時含密鑰與機器指紋、回傳租約的 `expires_at − issued_at == 30 天`、`$EDIAAD_HOME/lease.json` 內容等於回傳租約，且以 `LICENSE_PUBLIC_KEY` 對「除 `sig` 外全部欄位」驗章為真。
- 後續例外／邊界情境：
  1. AC-053 零網路：以有效租約走啟動驗證路徑，斷言假 HTTP `call_count == 0`；同一案例把 HTTP 客戶端換成「任何呼叫都拋 `SourceError`」的實作，仍必須回 `ok=True` 完成啟動。
  2. 指紋不符：租約 `machine` 與目前指紋不同 → `ok=False`，`reason` 指出指紋不符。
  3. 已過期：`now` 大於 `expires_at` → `ok=False`，`reason` 指出過期（停止與導流的行為由 TASK-031 接手）。
  4. AC-058 第一層：`now = issued_at − 901 秒`（容忍值 900 秒）→ `force_online=True`；`now = issued_at − 900 秒` 恰在邊界時的行為必須明確定義並以測試固定。
  5. AC-058 第二層：`high_water` 已寫入較大值後，`now = high_water − 901 秒` → `force_online=True`；把 `high_water` 設為 `None`（首次啟動）時不得觸發此層。
  6. `force_online=True` 且線上驗證不可用（假 HTTP 拋 `SourceError`）→ 不得放行（`ok=False`），且不得以本地時間延長授權。
  7. 落地原子性：`lease.json` 寫入中斷（以唯讀目錄模擬）時不得留下半寫檔案，既有租約檔不損毀。
  8. 啟用失敗映射：假 HTTP 回 4xx（無效密鑰）→ 丟 `ConfigError`（exit 2 語意）；回 5xx 或連線失敗 → 丟 `SourceError`（exit 1 語意）；兩種情況都不得落地租約。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_license_activate.py tests/test_license_startup.py -q`；回歸 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用，本張全部行為皆可用假 HTTP／假時鐘先寫 Red 再實作。
- 必要的人工檢查：無（全部可自動化）。AC-053 的「啟動流程完全不發出網路請求」以假 HTTP 計數器為權威證據，不以人工觀察或封包側錄代替；若需人工複核，僅在 Review 時目視確認 `verify_lease` 路徑上沒有任何未經注入的網路呼叫。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-029 的交付物（全套 **836 passed**），檔案樹 sha256 `a6503eb5e87fa310bb305ed3a9f96d10deedeb7d320ad8a8a58020bf765178f6`（82 檔）；本次修改 `ediaad/license.py`（`activate`／`check_lease`／`LeaseVerdict`／租約與水位落地）與 `ediaad/paths.py`（`lease_path`／`high_water_path`），新增 `tests/test_license_activate.py`／`tests/test_license_startup.py`／`tests/_ed25519_fixture.py`（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-030.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-030.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-license-activate` sha256:582e6e88aff091027e99d12341796947843b885e0eae420c8fda413362adf2b2（原始碼樹，85 檔）；`ediaad/license.py` `adfdfd94…`、`ediaad/paths.py` `f6f6ad3b…`、`tests/test_license_activate.py` `bce0eb56…`、`tests/test_license_startup.py` `89d2408d…`、`tests/_ed25519_fixture.py` `7452398f…`；全套 **868 passed**；變異矩陣 25／25 偵測到（0 存活）
- 取消、重開或變更原因：無
