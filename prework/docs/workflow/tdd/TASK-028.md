# TASK-028 測試紀錄

- task_id：TASK-028
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-license-model sha256:0c378a8ba64fa1a99b86a10b6489a1ce19e50accfaf157dcb530f21b8e8a9e38
- alternative_reason：不適用（本張為純函式與資料模型，全部行為可自動驗證：指紋以注入的 reader 與 `tmp_path` 假檔驗證，租約以 JSON 往返與注入的 `verify_sig` 驗證；真實 `/etc/machine-id` 只驗**形狀**、不記錄指紋值，也不需要人工或視覺檢查）。
- Task／Spec 版本：TASK-028 / SPEC-001 v0.4
- 測試邊界：`machine_fingerprint`（注入 reader／預設 reader／真實檔案的形狀／錯誤處理／跨程序穩定）、`Lease`（JSON 往返、嚴格還原、frozen、`signing_payload` 的涵蓋範圍與**逐字正規形式**）、`verify_lease`（指紋閘門與注入的驗章器）。全部離線，不依賴真實機器狀態。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-027 的交付物，全套 **798 passed**（本張完成後為 **814 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `337e645a8137bd0ddf8c44ae382e8891875274629574f62361c76d1dc7b31749`（79 個檔案）。
- TDD 不適用的理由與替代驗證（若有）：無。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/license.py` | `461510ff` | 新增：`DEFAULT_MACHINE_ID_PATH`／`FINGERPRINT_LENGTH`、`machine_fingerprint`、`Lease`（frozen，含 `to_json`／`from_json`）、`signing_payload`、`verify_lease` |
| `tests/test_license_fingerprint.py` | `0b2c9922` | 新增：16 個測試（指紋 7、租約 5、指紋閘門 4） |

## Cycle 1：指紋與租約模型（AC-055，真實 Red → Green）

- 測試（16 個）：
  - **指紋**：內容 `abc123\n` → `sha256(b"abc123").hexdigest()[:16]`、長度 16 且完整匹配 `[0-9a-f]{16}`（任務指定的第一個失敗行為）；四種空白寫法（無換行／單換行／前後空白／多換行）都得到同一個值（對應實測的 33 bytes 含換行情境）；**跨程序重算相同**（另起 `.venv/bin/python -c` 子程序）；`read_text` 未注入時真的讀檔；真實 `/etc/machine-id` 只驗形狀且**不記錄指紋值**，並斷言 `DEFAULT_MACHINE_ID_PATH == "/etc/machine-id"`；reader 丟出 `OSError`／內容為空／只有空白都丟出 `ConfigError` 且訊息含來源路徑（**不得回傳空字串或固定常數**）；兩個不同 machine-id 得到不同指紋。
  - **租約**：`to_json` 的鍵集合等於 SPEC 第 5 節的七個欄位、鍵序為 `sort_keys=True`、`from_json` 往返完全相等（含以 tuple 建構 `features` 的情況）；frozen（指派欄位會失敗）；嚴格還原（缺欄位、未知欄位、非物件、非 JSON、`features` 為字串或含非字串、`key_id` 空、`machine` 不是 16 碼小寫十六進位、`issued_at` 非字串或不是合法 ISO 時間、`sig` 非字串、以及**非 Mapping 但鍵剛好齊全的 tuple**）各丟出 `ConfigError`；`signing_payload` 涵蓋除 `sig` 以外的每一個欄位（逐一改動都必須改變 bytes），改 `sig` 不改變，且**逐字等於正規形式的 bytes**。
  - **指紋閘門**：指紋不符 → `False` 且**不呼叫** `verify_sig`（不浪費一次驗章）；相符且 `verify_sig` 回 `True` → `True` 且驗章器收到租約本身；`verify_sig` 回 `False` → `False`；**未注入 `verify_sig` → 丟出 `ConfigError`**（「還沒驗章」不得被讀成「驗章通過」或「簽章無效」）；`fingerprint=None` 時會用目前機器的指紋（以 monkeypatch 驗證兩邊）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_license_fingerprint.py -q` | 2 | collection error：`ModuleNotFoundError: No module named 'ediaad.license'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `16 passed in 0.09s` | snap-2026-09-24-ocaievo-license-model／2026-09-24 |

- 實作：`ediaad/license.py`（純標準庫：`hashlib`／`json`／`dataclasses`／`datetime`／`pathlib`）。
- **`signing_payload` 是本張最重要的介面決定**：SPEC 說「簽章涵蓋除 `sig` 外的所有欄位」，但沒有指定序列化方式。若 TASK-029（驗章）與 TASK-030（簽發）各自實作一次，簽章範圍就會分岔、而且**兩邊的測試都會過**（各自 round-trip）。因此本張把它定義成公開函式並**逐字釘住 bytes**，兩張 Task 都必須用它。
- **「還沒驗章」與「驗章失敗」必須分開**：`verify_sig` 未注入時丟出 `ConfigError`（訊息指向 TASK-029）。回 `False` 會被讀成「簽章無效」——那是不同的意思，也是 F-003 的同一原則。
- **指紋錯誤不得靜默**：讀不到、空、只有空白都丟出 `ConfigError` 並附來源路徑。回空字串或固定常數會讓**所有機器看起來一樣**，等於沒有綁定。
- **`features` 正規化為 tuple**：JSON 只有陣列，讀回來一定是 `list`；不統一的話 `Lease(features=("start",))` 的往返會不相等。這是在寫測試時發現的（已補 tuple 往返的斷言）。
- **真實指紋不進證據**：形狀測試只斷言 `[0-9a-f]{16}`，不記錄值；這樣 TDD／Review 紀錄不會把機器資訊寫進專案。

## 變異測試（兩階段：先殺存活者，再跑凍結版）

- 工具：`/tmp/mutate_task028.py`（整行替換、`count(frm) == 1` 才套用、逾時 180 秒、跑完立即還原並比對 sha256、`flock` 確保單一行程）。
- 矩陣：**20 個變異**（全部在 `ediaad/license.py`），涵蓋指紋的空白處理／空內容／例外型別／截取長度／長度常數／預設來源路徑／預設 reader／編碼、租約的 `machine` 驗證、空字串驗證、ISO 時間驗證、`to_json` 的鍵序、`from_json` 的三種守門、`signing_payload` 的簽章排除與編碼、`verify_lease` 的指紋閘門／未注入驗章器／回傳值。
- **第一階段抓到 1 個真實存活者並補強測試擊殺**：`L13`（`from_json` 的「必須是 JSON 物件」型別檢查拿掉）存活——我原本用的 `["not","an","object"]` 會先被「缺少欄位」擋下（一樣是 `ConfigError`），所以看不出差別。已補「非 Mapping 但**鍵剛好齊全**的 tuple（欄位名排序後）」的案例：少了型別檢查就會落到 `cls(**dict(...))` 的 `ValueError`，訊息不可讀。
- **另外三處在跑之前就先補強**（避免製造假存活者）：預設來源路徑常數（`/etc/machine-id`）的斷言、非字串但**格式錯誤**的 ISO 時間（走 `datetime.fromisoformat` 的錯誤分支）、`signing_payload` 的逐字 bytes。
- **最終凍結版結果：20／20 全數偵測到（0 存活、0 無效）**，逐輪輸出形如 `15 passed, 1 failed`（16 個測試）。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `.venv/bin/python -m pytest tests/test_license_fingerprint.py -q` | 0 | `16 passed in 0.12s` |
| `.venv/bin/python -m pytest -q` | 0 | `814 passed, 2 warnings in 131.51s` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |

## 未執行或受阻

- 無。本張沒有需要人工或視覺檢查的項目；真實 `/etc/machine-id` 只以形狀驗證，未記錄值。
- 已知的**後續依賴**（不是本張的缺口）：`verify_lease` 的簽章那一半在 TASK-029 完成前一律丟出 `ConfigError`；租約落地（`$EDIAAD_HOME/lease.json`）與時鐘防護屬 TASK-030；`features` 的功能分級屬 TASK-031。
