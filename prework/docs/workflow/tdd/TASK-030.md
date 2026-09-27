# TASK-030 測試紀錄

- task_id：TASK-030
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-license-activate sha256:582e6e88aff091027e99d12341796947843b885e0eae420c8fda413362adf2b2
- alternative_reason：不適用（全部行為可用假 HTTP 與假時鐘先寫 Red 再實作；授權服務不啟動真實伺服器，租約簽章由測試專用的純 Python 夾具產生，全程離線）。
- Task／Spec 版本：TASK-030 / SPEC-001 v0.4
- 測試邊界：只呼叫 `activate`／`check_lease`（以及落地用的 `save_lease`／`load_lease`／`save_high_water`／`load_high_water`）；HTTP 以計數假客戶端注入、時間以固定 `now` 注入、產物以 `tmp_path` 觀察。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-029 的交付物，全套 **836 passed**（本張完成後為 **868 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `a6503eb5e87fa310bb305ed3a9f96d10deedeb7d320ad8a8a58020bf765178f6`（82 個檔案）。
- TDD 不適用的理由與替代驗證（若有）：無。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/license.py` | `adfdfd94` | 修改：`LEASE_DURATION`／`CLOCK_TOLERANCE_SECONDS`／`HTTP_TIMEOUT_SECONDS`、`LeaseVerdict`、`sig_bytes`、`save_lease`／`load_lease`、`load_high_water`／`save_high_water`、`activate`、`check_lease`（含 `_refresh_online`／`_advance_high_water`／`_body_message`／`_lease_from_body`／`_clock`／`_epoch`） |
| `ediaad/paths.py` | `f6f6ad3b` | 修改：`lease_path`（`<home>/lease.json`）與 `high_water_path`（`<home>/high_water.json`） |
| `tests/test_license_activate.py` | `bce0eb56` | 新增：15 個測試（啟用請求、落地、錯誤分層、原子性、權限、預設路徑） |
| `tests/test_license_startup.py` | `89d2408d` | 新增：17 個測試（離線啟動、指紋／簽章／到期、兩層時鐘防護、水位） |
| `tests/_ed25519_fixture.py` | `7452398f` | 新增：測試專用的純 Python Ed25519 **簽章**夾具（RFC 8032 的公開 secret key；含自我檢查） |

## Cycle 1：首次啟用與落地（AC-052，真實 Red → Green）

- 測試（15 個）：假 HTTP **恰好一次** `POST <url>/v1/activate`，payload 同時含密鑰與機器指紋；回傳租約與落地內容一致；以伺服器公鑰對「除 `sig` 外全部欄位」驗章為真；`expires_at − issued_at` 恰為 30 天；JSON 字串與映射兩種回應都能吃；伺服器回**別的機器**的租約 → `ConfigError` 且不落地；簽章被換掉 → 拒絕；簽章非十六進位或長度不是 128 字元 → 拒絕並給**可讀原因**（指出十六進位或 128）；租約長度不是 30 天 → 拒絕；4xx → `ConfigError`、5xx／`OSError`／`SourceError` → `SourceError`（任何失敗都不落地）；回應畸形 → `ConfigError`；未指定公鑰時用 `LICENSE_PUBLIC_KEY`（全零佔位）→ **fail closed**；空白／非字串密鑰不必浪費網路請求；落地原子性（唯讀目錄時既有租約不損毀、不留 `.tmp`）；租約檔權限 `0600`；缺檔回 `None`、損毀丟 `ConfigError`；未指定路徑時落在 `$EDIAAD_HOME`。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_license_activate.py tests/test_license_startup.py -q` | 2 | collection error：`ImportError: cannot import name 'CLOCK_TOLERANCE_SECONDS'` | 尚未有實作／2026-09-24 |
| Green | 同上 | 0 | `32 passed in 0.39s` | snap-2026-09-24-ocaievo-license-activate／2026-09-24 |

## Cycle 2：離線啟動驗證與時鐘防護（AC-053、AC-058）

- 測試（17 個）：
  - **AC-053 零網路**：有效租約走啟動路徑時假 HTTP 的 `call_count == 0`（客戶端甚至設定成「任何呼叫都丟 `AssertionError`」）；把客戶端換成「任何呼叫都拋 `SourceError`」也必須 `ok=True`。
  - **驗證順序**：缺租約 → `ok=False` 且訊息提到「啟用」；指紋不符 → `ok=False` 且訊息指出指紋；簽章被換掉或非十六進位 → `ok=False` 且訊息指出簽章；到期判定為 `now > expires_at`（**等於到期時刻仍可啟動**，邊界兩側都有斷言）。
  - **AC-058 第一層（簽章內的 `issued_at`）**：`now = issued_at − 900` 不觸發、`now = issued_at − 901` → `force_online=True`。
  - **AC-058 第二層（本地 `high_water`）**：`now = high_water − 900` 不觸發、`−901` → `force_online=True`；首次啟動（無水位）不觸發；**成功啟動不得把水位往回寫**（容忍值內的小幅調鐘不得磨掉防線）。
  - **強制線上**：沒有客戶端／客戶端失敗／服務回 4xx → `ok=False` 且訊息說明「不以本地時間延長授權」；服務可用 → 以伺服器回的新租約放行（`POST <url>/v1/verify`、payload 含 `key_id` 與指紋）、新租約落地、水位推進；線上回來的租約仍要驗指紋（別的機器 → 拒絕）與到期（已過期 → 拒絕）。
  - **水位檔案**：缺檔／非 JSON／非數值都視為「沒有水位」（報告第 6.4 節的已知限制：可被刪檔繞過）；寫入權限 `0600`。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 2 | 與 Cycle 1 同一次 collection error（兩個測試檔一起收） | 同上／2026-09-24 |
| Green | 同上 | 0 | `29 passed in 0.36s`（Cycle 2 的四個補強案例加入後為 32） | 同上／2026-09-24 |

- 實作：`activate`（請求 → 狀態碼分層 → 租約契約檢查（機器、30 天、簽章）→ 原子落地）與 `check_lease`（讀租約 → 指紋 → 簽章 → 到期 → 兩層時鐘 → 必要時強制線上 → 推進水位）。
- **`verify_lease` 的簽章沒有被改動（與 TASK-030.md 的文字不同，已在 Review 記錄）**：TASK-030.md 提議 `verify_lease(lease, *, fingerprint, public_key, now, high_water, tolerance_seconds) -> LeaseVerdict`。但 TASK-028 已經交付並 Review 過 `verify_lease(lease, fingerprint=None, verify_sig=None) -> bool`（指紋＋簽章的閘門，有 16 個測試）。把同一個名字換成不同簽章會破壞已完成的公開契約，因此本張以**新函式 `check_lease`** 實作完整啟動判定，並**重用** `verify_lease` 當作指紋＋簽章的閘門（把 `verify_sig` 綁到 `ed25519_verify` ＋ `signing_payload` ＋ `sig_bytes`）。這是「同一結構被兩張 Task 重複定義」風險的具體處置，已列為 Review 的追認項。
- **簽章涵蓋範圍只有一份**：`activate` 與 `check_lease` 都用 TASK-028 的 `signing_payload`（TASK-028 的 A-1），沒有任何地方自行序列化被簽內容。
- **時間全部注入**：`activate`／`check_lease` 都不呼叫 `datetime.now()`（唯一的預設值 `_default_now` 本身才用），符合 SPEC 第 5 節原則 2。
- **錯誤分層與 exit code 語意一致**：4xx（無效密鑰）→ `ConfigError`（exit 2）、5xx／連線失敗／落地失敗 → `SourceError`（exit 1）；任何失敗都不落地。
- **`high_water` 寫不進去不阻止啟動**：它是可被刪檔繞過的**第二層**防護，真正的防線是簽章內的 `issued_at`；為了一個可繞過的檔案讓服務起不來並不合理（已註解）。
- **測試簽章夾具的公鑰有自我檢查**：`_ed25519_fixture` 在 import 時就斷言「由 RFC TEST 1 的 secret key 推導出的公鑰等於向量值」——夾具本身錯了就整個測試群不可信。夾具只存在於 `tests/`，不進 `ediaad/`，也不引入 `cryptography`。

## 變異測試（兩階段：先殺存活者，再跑凍結版）

- 工具：`/tmp/mutate_task030.py`（整行替換、`count(frm) == 1` 才套用、逾時 180 秒、跑完立即還原並比對 sha256、`flock`、`PYTHONDONTWRITEBYTECODE=1`）。
- 矩陣：**25 個變異**（`license.py` 23、`paths.py` 2），涵蓋啟用請求端點與 payload、狀態碼分層的兩個方向、租約的機器／長度／簽章三個契約檢查、落地的有無、30 天常數、簽章格式檢查、水位的型別檢查、水位的「只能往前」、線上刷新租約的三個檢查（機器／到期／狀態碼）、到期的兩側、兩層時鐘防護、缺租約、強制線上不可用、`verify_sig` 的綁定、預設產物路徑。
- **第一階段抓到 1 個真實存活者並補強測試擊殺**：`A10`（`sig_bytes` 的長度檢查拿掉）存活——錯誤長度的簽章會被 `ed25519_verify` 的長度檢查擋下，呼叫端一樣丟 `ConfigError`，因此「有沒有那行」在行為上等價。但那一行提供的是**可讀的原因**（「必須是 128 個十六進位字元」而不是籠統的「簽章驗證失敗」），因此補上「錯誤訊息必須指出十六進位或 128」的斷言——這是可觀測的契約，不是為了讓變異死掉而加測試。
- **另有三處在跑之前就先補強**（避免製造假存活者）：錯誤長度的**合法十六進位**簽章（`ab`×32、`ab`×65）、容忍值內的成功啟動不得把水位往回寫、線上回來的租約已過期、預設產物路徑落在 `$EDIAAD_HOME`。
- **最終凍結版結果：25／25 全數偵測到（0 存活、0 無效）**，逐輪輸出形如 `31 passed, 1 failed`（32 個測試）。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `.venv/bin/python -m pytest tests/test_license_activate.py tests/test_license_startup.py -q` | 0 | `32 passed in 0.39s` |
| `.venv/bin/python -m pytest -q` | 0 | `868 passed, 2 warnings in 131.40s` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |

## 未執行或受阻

- 無自動測試受阻。本張沒有需要人工或視覺檢查的項目；授權服務是真的（TASK-033 的 Cloudflare Worker），因此端到端啟用仍待 TASK-033 之後。
- 已知的**後續依賴**（不是本張的缺口）：續期、到期停止與導流、功能分級屬 TASK-031；`LICENSE_PUBLIC_KEY` 仍是 fail-closed 佔位值（TASK-033 產生 Worker 金鑰後替換）；週期性的「每 24 小時線上驗證」屬 TASK-031。
