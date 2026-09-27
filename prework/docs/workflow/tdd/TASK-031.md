# TASK-031 測試紀錄

- task_id：TASK-031
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-license-renew sha256:e37eec7cf2cd17238cb489a9e0d338c078cbed1482f59624ed60f3514131314a
- alternative_reason：不適用（全部行為可用假 HTTP（200／403／429／5xx／例外）與假時鐘先寫 Red 再實作；不啟動真實服務，租約簽章沿用 TASK-030 的測試夾具，全程離線）。
- Task／Spec 版本：TASK-031 / SPEC-001 v0.4
- 測試邊界：只呼叫 `renew`／`lease_status`／`has_feature`／`check_lease`／`activate`；HTTP 與時鐘全部注入，產物以 `tmp_path` 觀察。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-030 的交付物，全套 **868 passed**（本張完成後為 **888 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `582e6e88aff091027e99d12341796947843b885e0eae420c8fda413362adf2b2`（85 個檔案）。
- TDD 不適用的理由與替代驗證（若有）：無。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/license.py` | `711aaf94` | 修改：`RENEW_TRIGGERS`／`REVOKED_FILE_NAME`、`LeaseStatus`、`renew`、`lease_status`、`has_feature`、撤銷標記讀寫（`_revoked_key`／`_mark_revoked`／`_indicates_revoked`／`_default_revoked_path`）；`check_lease` 新增 `revoked_path` 與撤銷檢查 |
| `ediaad/paths.py` | `cf51cea1` | 修改：`revoked_path`（`<home>/revoked.json`） |
| `tests/test_license_renew.py` | `2fd123b9` | 新增：10 個測試（成功續期、三個觸發來源、403 導流、錯誤分層、回應契約） |
| `tests/test_license_features.py` | `816f852f` | 新增：9 個測試（features 分級、授權狀態、撤銷標記、更換密鑰、預設路徑） |

## Cycle 1：續期與 403 導流（AC-056，真實 Red → Green）

- 測試（10 個）：
  - **成功續期**（任務指定的第一個失敗行為）：`now = 2026-10-20T12:00:00Z`、`trigger="timer"` → 假 HTTP 恰一次 `POST <url>/v1/renew`，payload 含 `key`／`machine`／`trigger`；回傳租約的 `expires_at == 2026-11-19T12:00:00Z`（`now + 30 天`）、`issued_at == now`；`lease.json` 被原子覆寫且不留 `.tmp`；續期後的租約通過啟動驗證。
  - **三個觸發來源**（`start`／`timer`／`manual`）逐一驗證；未知 trigger → `ConfigError` 且**不發出請求**（不合法的觸發來源沒有必要送出去）。
  - **403 導流（核心）**：後端回 403 → `ConfigError`、**本地租約的到期日完全沒被動到**，且 `lease_status` 接著回報 `expired` ＋「重新申請」訊息。
  - **撤銷**：403 且回應指出 `revoked` → 落地撤銷標記、`lease_status` 為 `revoked`、**之後同一把密鑰的 `check_lease` 也停止**（即使租約本身還沒到期）。
  - **錯誤分層**：429／5xx／`OSError`／`SourceError` → `SourceError`（可重試）；400 → `ConfigError`；每一種都斷言租約未被改寫。
  - **回應契約**：五種不合格的回應各自被拒（長度不是 30 天、到期時間沒有延後、別的機器、簽章無效、換了 `key_id`），且都不落地。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_license_renew.py tests/test_license_features.py -q` | 2 | collection error（`renew`／`lease_status`／`has_feature` 不存在） | 尚未有實作／2026-09-24 |
| Green | 同上 | 0 | `19 passed in 0.26s`（補強後 19 個案例） | snap-2026-09-24-ocaievo-license-renew／2026-09-24 |

- 實作：`renew`（trigger 驗證 → 請求 → 狀態碼分層（403／429／其他 4xx／5xx）→ 回應契約五項檢查 → 原子覆寫）；`403` 且指出撤銷時落地標記。
- **403 的處置是這一張的目的**：SPEC 的 AC-056 明訂「後端對過期租約的 `renew` 回 403」，因此客戶端**絕不以本地時間或舊租約續用**；測試直接斷言「失敗後本地租約的到期日不變」＋「接著判為過期並附重新申請訊息」。
- **429 與其他 4xx 分開**：429 是暫時狀態（客戶端沒錯、可重試）→ `SourceError`（exit 1）；其餘 4xx 是輸入／授權被拒 → `ConfigError`（exit 2）。這是變異 `R13` 的偵測點。
- **撤銷標記放在租約旁邊**（`<lease_dir>/revoked.json`，`0600`，原子寫入）：不同 `$EDIAAD_HOME` 天然隔離，測試也因此不需要碰真實家目錄；只有**同一把** `key_id` 會被擋（更換密鑰後舊標記不影響新密鑰）。
- **續期只走線上、失敗不影響有效期內使用**：只有成功才覆寫；任何失敗路徑都不動本地租約（SPEC 的外部依賴表要求）。

## Cycle 2：功能分級、授權狀態與更換密鑰（AC-057，真實 Red → Green）

- 測試（9 個）：`has_feature` 精確比對（含大小寫與空 `features`）；`features == ["start"]` 時**服務仍可啟動**（`check_lease` 回 `ok=True`）但 `update` 為 `False`（TASK-032 會據此傳 `enabled=False`）；`lease_status` 四態——沒有租約 → `unactivated` ＋「請輸入密鑰完成啟用」；有效 → `active` ＋剩餘天數（23.0 天）；到期邊界（等於到期時刻仍有效、超過才 `expired` ＋重新申請訊息）；**撤銷只認同一把 `key_id`**（別的密鑰不受影響）；撤銷標記檔損毀／型別不對 → 視為沒有標記（不因標記壞掉而擋住服務）；更換密鑰後以新租約為準且**不被舊 key_id 的撤銷標記擋住**；以已撤銷的密鑰重新啟用時伺服器回 403 → 拒絕且不落地；未指定路徑時 `paths.revoked_path()` 落在 `$EDIAAD_HOME`。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 2 | 與 Cycle 1 同一次 collection error | 同上／2026-09-24 |
| Green | 同上 | 0 | `19 passed`（兩個測試檔合計） | 同上／2026-09-24 |

- 實作：`LeaseStatus`／`has_feature`／`lease_status`／撤銷標記；`check_lease` 在載入租約後先看撤銷標記（同一把 `key_id` 就停止）。
- **`check_lease` 的撤銷檢查是 TASK-030 之後新增的**：AC-056 要求「撤銷後下次驗證即停止」，因此同一個啟動驗證函式必須看撤銷標記；TASK-030 的既有測試不受影響（沒有標記時行為完全相同），已回歸確認。
- **`lease_status` 是結構化結果**：本模組只回傳 `state`／`message`／`expires_at`／`days_remaining`／`reapply`，不印訊息、不寫網頁——授權頁（TASK-025）與 CLI（TASK-036）各自轉譯。

## 變異測試（兩階段：先殺存活者，再跑凍結版）

- 工具：`/tmp/mutate_task031.py`（整行替換、`count(frm) == 1` 才套用、逾時 180 秒、跑完立即還原並比對 sha256、`flock`、`PYTHONDONTWRITEBYTECODE=1`）。
- 矩陣：**21 個變異**（`license.py` 20、`paths.py` 1），涵蓋 trigger 驗證與常數、端點、payload、403 與 429 的分支、撤銷判定、回應契約五項檢查、落地、`has_feature`、`lease_status` 的四態與剩餘天數、撤銷標記的比對與預設位置、`check_lease` 的撤銷檢查。
- **第一階段抓到 2 個真實存活者並補強測試擊殺**：`R09`（續期後的租約長度檢查）與 `R11`（「到期時間必須延後」檢查）——兩者**互相掩蓋**：我原本的「不合格回應」清單裡，「不是 30 天」的那一筆同時也沒有延長（被延長檢查擋下），而「沒有延長」的那一筆長度也不是 30 天（被長度檢查擋下），因此任一條被拿掉都還會有另一條接住。已把案例重新設計成**各自只違反一項**（`now + 60 天` 只違反長度；`issued_at = 過期前 60 天、expires_at = 過期前 30 天` 只違反延長），兩條檢查就各自可觀測。
- **最終凍結版結果：21／21 全數偵測到（0 存活、0 無效）**，逐輪輸出形如 `19 passed, 1 failed`（19 個測試），並以 `/tmp/b31.log` 的摘要區塊確認工具正常結束（不是因為崩潰而沒有輸出）。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `.venv/bin/python -m pytest tests/test_license_renew.py tests/test_license_features.py -q` | 0 | `19 passed in 0.26s` |
| `.venv/bin/python -m pytest -q` | 0 | `888 passed, 2 warnings in 134.78s` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |

## 未執行或受阻

- 無自動測試受阻。本張沒有需要人工或視覺檢查的項目。
- 已知的**後續依賴**（不是本張的缺口）：
  1. **後端對過期租約的 `renew` 必須回 403**（AC-060／TASK-033 實作）。本張以假 HTTP 注入 403 驗證客戶端行為，但**後端那條斷言還沒有實作**——若 TASK-033 忘了它，導流會被繞過。已寫進 Review 的追認項與 `STATE.md` 待決事項。
  2. 週期性的「每 24 小時」與「每次開啟」觸發需要有人呼叫 `renew`（TASK-025 的服務排程／TASK-036 的 CLI）；本張只交付函式與觸發來源列舉。
  3. `features` 分級對更新功能的實際停用由 TASK-032 的 `check_update(enabled=has_feature(lease, "update"))` 消費。
  4. 授權頁（AC-066，TASK-025）與重新申請頁（TASK-035）尚未呈現 `LeaseStatus`。
