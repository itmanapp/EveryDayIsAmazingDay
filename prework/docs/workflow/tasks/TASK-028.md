# TASK-028：機器指紋與租約模型

- id：TASK-028
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-055"]
- depends_on：["TASK-001"]
- test_evidence：["docs/workflow/tdd/TASK-028.md"]
- review_evidence：["docs/workflow/reviews/TASK-028.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`ediaad.license.machine_fingerprint()` 讀取可讀的 `/etc/machine-id`（實測 33 bytes，含結尾換行），去除前後空白後取 sha256 十六進位前 16 碼；同一台機器重複計算（含跨程序重算）得到完全相同的字串，格式符合 `[0-9a-f]{16}`；`Lease` 為 frozen 且可與 SPEC 第 5 節的租約 JSON 格式互相轉換（簽章涵蓋除 `sig` 外的所有欄位）；`verify_lease` 在租約的 `machine` 與目前指紋不符時判定失敗。
- 本張不做：不做 Ed25519 簽章驗證與 RFC 8032 向量（TASK-029）、不做啟用與續期網路流程（TASK-030／031）、不把租約落地到 `$EDIAAD_HOME/lease.json`（TASK-030）、不做時鐘篡改防護與 `high_water`（TASK-030）、不做 features 功能分級（TASK-031）；不引入 `cryptography` 或任何新依賴（純標準庫）；不讀取 `/etc/machine-id` 以外的新識別來源。
- 每個 AC 在本張負責的範圍：AC-055 全部（可讀 `/etc/machine-id` 得到 sha256 前 16 碼的穩定字串、同一機器重算相同、租約指紋不符時驗證失敗）；簽章是否有效由 TASK-029 負責，本張以注入的假簽章驗證器單獨驗證指紋閘門。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-055、第 5 節 `ediaad/license.py`（`Lease`、`machine_fingerprint`、`verify_lease`）與「租約格式」JSON 及「資料生命週期、權限與狀態轉移」、第 6 節安全（租約以 Ed25519 簽章保護到期日與指紋）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.4 節租約格式與「時鐘篡改防護」、第 2.12 節租約／機器指紋概念；`docs/workflow/PROJECT.md` 環境實測（`/etc/machine-id` 可讀，33 bytes 含換行）；`docs/workflow/CONTEXT.md` 的「機器指紋」與「租約」。
- 模組與公開介面：新增 `ediaad/license.py`：`machine_fingerprint(machine_id_path="/etc/machine-id", read_text=None) -> str`（`read_text` 可注入以利測試；讀取失敗或內容無效時丟出 `ConfigError` 並指出來源，不得回傳空字串或固定常數）；`Lease`（frozen dataclass，欄位為 `key_id`、`machine`、`issued_at`、`expires_at`、`features`、`catalog_version`、`sig`）與 `Lease.to_json()`／`Lease.from_json()`（穩定鍵序與缺欄位／型別錯誤的 `ConfigError`，沿用 `PatternSpec` 的作法）；`verify_lease(lease, fingerprint=None, verify_sig=None) -> bool`（先檢查指紋相符，再交棒給 `verify_sig`；`verify_sig` 未注入時明確表示驗章尚未完成，不誤判為通過）。
- 預計觸及的檔案：`ediaad/license.py`、`tests/test_license_fingerprint.py`；實作前重新查證（特別是 TASK-029 是否已先建立 `Lease` 或驗章骨架，避免同一結構被兩張 Task 重複定義而分岔）。
- 必要環境／依賴：Python 3.12.3 與 `.venv`（TASK-001）；標準庫 `hashlib`、`json`、`dataclasses`、`datetime`；測試以 `tmp_path` 的假 `machine-id` 與注入的 reader 進行，不需網路、不依賴真實機器狀態。

## 測試計畫

- 測試公開邊界：直接呼叫 `machine_fingerprint`（注入的 `read_text` 指向 `tmp_path` 的假 `machine-id`）與 `verify_lease` 的回傳值，以及 `Lease` 的 JSON 往返。
- 第一個失敗行為與預期斷言：先寫「對內容為 `abc123\n` 的假 machine-id，`machine_fingerprint(...)` 等於 `hashlib.sha256(b"abc123").hexdigest()[:16]`，長度為 16，且可用 `[0-9a-f]{16}` 完整匹配」。實作前執行 `.venv/bin/python -m pytest tests/test_license_fingerprint.py -q` 預期收集期失敗 `ModuleNotFoundError: No module named 'ediaad.license'`；實作後斷言成立。
- 後續例外／邊界情境：同一內容在同一程序重複計算與另起程序重算都得到相同值；內容含尾端換行或前後空白時先去空白再雜湊（對應實測的 33 bytes 含換行情境）；`/etc/machine-id` 讀取失敗（注入的 reader 丟出 `OSError`）或內容為空時丟出 `ConfigError` 且訊息指出來源，不得回傳空字串或固定常數；兩份不同 machine-id 得到不同指紋；`Lease.from_json` 對缺欄位、多欄位與型別不符各自丟出 `ConfigError`，`to_json` 後 `from_json` round-trip 完全相等；`verify_lease` 在 `lease.machine` 與目前指紋不符時回 `False`，相符且注入的 `verify_sig` 回 `True` 時回 `True`，未注入 `verify_sig` 時不得回 `True`。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_license_fingerprint.py -q`；相關回歸 `.venv/bin/python -m pytest -q`。
- 非程式任務的替代驗證與理由：不適用（本張為純函式與資料模型，全部行為可自動驗證；不需人工或視覺檢查，亦不記錄真實機器指紋值）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-027 的交付物（全套 **798 passed**），檔案樹 sha256 `337e645a8137bd0ddf8c44ae382e8891875274629574f62361c76d1dc7b31749`（79 檔）；本次新增 `ediaad/license.py` 與 `tests/test_license_fingerprint.py`，未修改任何既有檔案（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-028.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-028.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-license-model` sha256:0c378a8ba64fa1a99b86a10b6489a1ce19e50accfaf157dcb530f21b8e8a9e38（原始碼樹，81 檔）；`ediaad/license.py` `461510ff…`、`tests/test_license_fingerprint.py` `0b2c9922…`；全套 **814 passed**；變異矩陣 20／20 偵測到（0 存活）
- 取消、重開或變更原因：無
