# TASK-031：續期、到期停止、撤銷與功能分級

- id：TASK-031
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-056","AC-057"]
- depends_on：["TASK-030"]
- test_evidence：["docs/workflow/tdd/TASK-031.md"]
- review_evidence：["docs/workflow/reviews/TASK-031.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：
  - AC-056：`renew(lease, ...)` 以注入的 HTTP 客戶端呼叫 `POST <url>/v1/renew`，成功後以 `now + 30 天` **重算**到期日並原子覆寫 `$EDIAAD_HOME/lease.json`；每次呼叫都帶 `trigger`，且只接受 `start`（每次開啟）／`timer`（每 24 小時）／`manual`（使用者手動或網頁更換密鑰），與後端 `renewals` 記錄一致。租約已過期且超過 30 天未連線 → `lease_status` 為 `expired`，服務停止並顯示重新申請訊息。密鑰被撤銷 → 下次驗證（續期或線上驗證）失敗即停止，`lease_status` 為 `revoked`。**後端對已過期租約的 `renew` 必須回 403**：客戶端收到 403 時必須判為過期／撤銷並導流重新申請，絕不得以本地時間或舊租約續用（否則導流被繞過）。此約束的後端實作屬 AC-060／TASK-033，本張以假 HTTP 注入 403 驗證客戶端行為，並在交接註記該後端斷言。
  - AC-057：`features` 功能分級生效；`features == ["start"]` 時更新功能停用（TASK-032 的 `check_update` 收到 `enabled=False`、不發出請求），但服務仍可啟動與監控；`features == ["start","update"]` 時更新檢查可用。網頁可輸入新密鑰更換：更換成功後以新租約為準，舊租約與舊 `key_id` 不再被接受。
- 本張不做：不實作 Ed25519 驗章（TASK-029）；不做首次啟用、離線啟動驗證與時鐘防護（TASK-030）；**不修改 Worker 端 `handleRenew` 的 403 判定**（TASK-033）；不做授權頁 UI 與 HTTP 端點（TASK-020、TASK-025 的 G11 欄位）；不做更新檢查與六條約束本身（TASK-032）；不做 CLI 子命令的參數與 exit code 封裝（TASK-036）；不做重新申請頁（TASK-035）。
- 每個 AC 在本張負責的範圍：AC-056 全部（成功續期重算 30 天、觸發來源如實記錄、逾期停止服務與導流、撤銷後停止、收到後端 403 的正確處置）；AC-057 全部（`features` 分級、缺少 `update` 時服務仍可用、更換密鑰以新租約為準）。本張不重複驗證 AC-052／AC-053 的啟用與離線驗章。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-056／AC-057、第 5 節租約格式（`features`）與「資料生命週期／授權狀態轉移」（未啟用 → 已啟用 → 已過期 → 已撤銷）、第 5 節外部依賴表（Cloudflare 授權服務：續期失敗不影響有效期內使用、逾期停止服務）、第 7 節測試策略列；`docs/architecture/ENGINEERING-REPORT.md` 第 6.4 節「三個觸發點與各自的驗證方式」、「撤銷與導流」（撤銷立即生效、過期後必須重新申請新金鑰不自動續期、**後端必須拒絕已過期租約的 `renew`（回 403）**、重新申請頁對已撤銷指紋自動拒絕）、第 3.2 節 G14～G18。
- 模組與公開介面：`ediaad/license.py`（與 TASK-028～TASK-030 同一模組）新增
  - `renew(lease, *, http, url: str, now, trigger: str, timeout: float = 10.0) -> Lease`：成功回傳新租約並覆寫落地檔；`http` 介面同 TASK-030 的 `post(url, payload, timeout) -> (status, body)`。
  - `lease_status(lease, *, now) -> LeaseStatus`：值域 `unactivated`／`active`／`expired`／`revoked`。
  - `has_feature(lease, name: str) -> bool`：供 `check_update(enabled=...)` 與版本頁使用。
  - 常數 `RENEW_TRIGGERS = ("start", "timer", "manual")`，與 TASK-033 的後端 schema 對齊。
  - 授權狀態與導流訊息由本模組回傳結構化結果（供 TASK-025 的授權頁與 TASK-036 的 CLI 轉譯），不在本模組直接寫網頁或印訊息。
- 預計觸及的檔案：`ediaad/license.py`、`tests/test_license_renew.py`、`tests/test_license_features.py`；必要時 `ediaad/store.py` 的租約快取讀寫路徑（屬 TASK-018，本張不新增表）；實作前重新查證。
- 必要環境／依賴：`.venv`＋`pytest`；假 HTTP 客戶端（可注入 200／403／429／逾時／`SourceError`）與假時鐘；`tmp_path` 充當 `$EDIAAD_HOME`；合成租約與測試夾具簽章（沿用 TASK-030 的 `tests/_ed25519_fixture.py`）；全程離線。

## 測試計畫

- 測試公開邊界：只呼叫 `renew`、`lease_status`、`has_feature`；HTTP 與時鐘全部注入；以 `tmp_path` 觀察 `lease.json` 的覆寫結果，不啟動真實服務。
- 第一個失敗行為與預期斷言：實作前 import 失敗；首案 `test_renew_extends_thirty_days` 以 `issued_at = 2026-09-24T12:00:00Z`、`now = 2026-10-20T12:00:00Z` 呼叫 `renew(..., trigger="timer")`，斷言新租約 `expires_at == 2026-11-19T12:00:00Z`、`issued_at` 更新為 `now`、假 HTTP 收到的 payload `trigger == "timer"`、`lease.json` 已被原子覆寫為新租約。
- 後續例外／邊界情境：
  1. **後端對過期租約回 403**（`renew` 的核心導流情境）：假 HTTP 回 403 → `renew` 必須回報「過期／拒絕」且**不得**修改本地租約的 `expires_at`；後續 `lease_status(..., now)` 為 `expired` 並附重新申請訊息。
  2. 撤銷：假 HTTP 回 403 且後端狀態為 `revoked` → `lease_status` 為 `revoked`，服務停止；同一 key_id 之後不再被接受。
  3. 續期期間網路逾時 → 不影響有效期內使用：租約檔不變、`lease_status` 仍為 `active`、不停止服務（對應 SPEC 第 5 節外部依賴表）。
  4. `features == ["start"]` → `has_feature(lease, "update") is False`；以 `enabled=False` 呼叫更新檢查時假 HTTP 請求計數為 0，而啟動與監控路徑仍正常。
  5. `features == ["start","update"]` → `has_feature(lease, "update") is True`。
  6. 更換密鑰：以新密鑰啟用成功後，以舊 `key_id` 製作的租約在 `lease_status` 中不再為 `active`（以新租約為準）。
  7. 三種 `trigger` 各自只寫一筆且值正確；非法 `trigger`（如 `"cron"`）丟 `ConfigError`。
  8. 連續兩次續期（同一 `now` 相差 1 秒）不得使 `expires_at` 被無限延長成非 30 天（以 `now + 30 天` 重算，而非累加）。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_license_renew.py tests/test_license_features.py -q`；回歸 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用，本張全部行為皆可以假 HTTP／假時鐘先寫 Red。
- 必要的人工檢查：無自動化不可及項。交接註記：後端「過期租約的 `renew` 回 403」由 `cloudflare/test/activate.test.mjs`（TASK-033）對 `keys.expires_at < now` 的請求斷言；本張只以假 HTTP 注入 403 驗證客戶端導流，兩張合起來才構成 AC-056 的完整證據。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-030 的交付物（全套 **868 passed**），檔案樹 sha256 `582e6e88aff091027e99d12341796947843b885e0eae420c8fda413362adf2b2`（85 檔）；本次修改 `ediaad/license.py`（`renew`／`lease_status`／`has_feature`／撤銷標記／`check_lease` 的撤銷檢查）與 `ediaad/paths.py`（`revoked_path`），新增 `tests/test_license_renew.py`／`tests/test_license_features.py`（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-031.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-031.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-license-renew` sha256:e37eec7cf2cd17238cb489a9e0d338c078cbed1482f59624ed60f3514131314a（原始碼樹，87 檔）；`ediaad/license.py` `711aaf94…`、`ediaad/paths.py` `cf51cea1…`、`tests/test_license_renew.py` `2fd123b9…`、`tests/test_license_features.py` `816f852f…`；全套 **888 passed**；變異矩陣 21／21 偵測到（0 存活）
- 取消、重開或變更原因：無
