# TASK-035：D1 資料模型、後台操作與重新申請頁

- id：TASK-035
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-062","AC-063"]
- depends_on：["TASK-033"]
- test_evidence：["docs/workflow/tdd/TASK-035.md"]
- review_evidence：["docs/workflow/reviews/TASK-035.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：
  - AC-062：`cloudflare/schema.sql` 在空 D1 上建立 `keys`／`devices`／`renewals`／`blacklist`／`audit` 恰五張表，欄位涵蓋密鑰、狀態、`features`、到期、指紋、平台、版本與 `trigger`；後台操作可批次產生密鑰、查詢清單、撤銷、恢復、延長、統計與稽核，且每個後台寫入操作都在 `audit` 留一筆；統計以 `count(trigger='start')` 區分啟動次數，不被 `timer` 的那筆汙染。
  - AC-063：公開重新申請頁讓過期者可自助重新申請（產生新密鑰並可走啟用流程）；黑名單指紋被**自動拒絕**，不產生密鑰、不留下可啟用的記錄；未命中黑名單且未過期者的行為有明確定義並被測試固定。
- 本張不做：不部署、不連真實 D1（不執行 `wrangler d1 execute`）、不做真實後台登入／權限模型（作者角色以注入的 `actor` 字串在測試中模擬）、不做 Worker 的 `/v1/activate`／`/v1/renew` 邏輯（TASK-033）、不做靜態 manifest 與 catalog（TASK-034）、不做前端視覺設計或瀏覽器互動測試（重新申請頁只交付可測的 handler 與最小 HTML 樣板）、不寄送 Email 或任何外部通知。
- 每個 AC 在本張負責的範圍：AC-062 全部（五張表建立、批次產生、清單、撤銷／恢復／延長、`count(trigger='start')` 統計、稽核）；AC-063 全部（過期者自助重新申請、黑名單自動拒絕）。本張只以假 D1 驗證 SQL 與純函式；未驗證項（真實 migration、後台 UI）由 TASK-037 的 DELIVERY 明列。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-062／AC-063、第 5 節模組表 `cloudflare/worker/src/`、第 7 節測試策略列（假 D1）、第 2 節 out of scope（不部署、無真實帳號）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.7 節（D1 五表與各自內容、公開申請頁、後台功能、`renewals` 表的設計重點：每次驗證寫一筆並記 `trigger`，活躍使用者 ≈ 過去 30 天有 renew 的 distinct `key_id`）、第 6.4 節「撤銷與導流」（重新申請頁對已撤銷指紋自動拒絕）；`docs/workflow/PROJECT.md` 授權範圍（部署未授權）與環境實測表（無真實 D1）。
- 模組與公開介面：`cloudflare/schema.sql`；`cloudflare/worker/src/admin.js` 提供 `generateKeys(db, count, features, actor)`、`listKeys(db, filter)`、`revokeKey(db, keyId, actor)`、`restoreKey(db, keyId, actor)`、`extendKey(db, keyId, days, actor)`、`stats(db)`、`auditLog(db, actor, action, target)`；`cloudflare/worker/src/reapply.js` 提供 `handleReapply(request, env) -> Response`、`isBlacklisted(db, fingerprint)`、`findExpiredKey(db, fingerprint)`；`cloudflare/worker/src/db.js` 的 D1 轉接層沿用 TASK-033。
- 預計觸及的檔案：`cloudflare/schema.sql`、`cloudflare/worker/src/admin.js`、`cloudflare/worker/src/reapply.js`、`cloudflare/test/d1.test.mjs`、`cloudflare/test/fake-d1.mjs`（沿用 TASK-033，支援 `prepare`／`bind`／`first`／`all`／`run`／`batch`）；必要時 `cloudflare/worker/src/db.js`；實作前重新查證。
- 必要環境／依賴：Node v24.21.0，工作目錄 `cloudflare/` 執行 `node --test`；記憶體假 D1（可執行 `schema.sql` 的建表語句）；不需網路、不需 `wrangler`、不需真實 D1。

## 測試計畫

- 測試公開邊界：以假 D1 執行 `cloudflare/schema.sql` 後呼叫 admin／reapply 純函式，斷言回傳值與假 D1 內部的列狀態；重新申請以合成 `Request` 呼叫 handler 並檢查回應 status 與 JSON。
- 第一個失敗行為與預期斷言：假 D1 尚未建表時 `stats(db)` 查詢失敗（`no such table: renewals`）；首案 `test_schema_creates_five_tables` 斷言執行 `schema.sql` 後假 D1 中恰有 `keys`、`devices`、`renewals`、`blacklist`、`audit` 五張表，且 `renewals` 含 `key_id`、`created_at`、`trigger` 三個必要欄位。
- 後續例外／邊界情境：
  1. 批次產生：`generateKeys(db, 5, ["start","update"], actor)` → `keys` 增 5 列且狀態為未啟用；`audit` 留 1 列（含 `actor`、`action`、`target`）。
  2. 撤銷／恢復／延長：三者各自改變 `keys.status` 或到期日，且每次都在 `audit` 追加一列；對不存在的 key_id 回可讀錯誤且不寫 `audit`。
  3. 統計不被汙染：同一 key 寫入 3 筆 `trigger='start'` 與 2 筆 `trigger='timer'` → `stats` 的啟動次數為 3；不同 `key_id` 不互相加總。
  4. 重新申請成功：指紋存在於 `devices` 且其密鑰已過期（`expires_at < now`）→ `handleReapply` 回 200 並在 `keys` 產生新密鑰、`audit` 留一列。
  5. 黑名單自動拒絕：`blacklist` 含該指紋 → `isBlacklisted` 為真、`handleReapply` 回 4xx，且不得新增 `keys` 列或 `audit` 的「已產生」紀錄。
  6. 未命中黑名單但未過期者與完全不存在的指紋 → 各自的行為（拒絕並附說明）明確定義並測試，不得誤發新密鑰。
- 單項及相關回歸的實際命令／工作目錄：`cloudflare/` 下執行 `node --test`（單檔 `node --test test/d1.test.mjs`）；全套回歸入口為 TASK-037；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用。須誠實標示：真實 D1 的 migration 執行結果與後台 UI 無法驗證（無帳號／無部署授權），本張只以假 D1 驗證 SQL 與純函式。
- 必要的人工檢查：人工複核 `schema.sql` 與 `wrangler.toml` 不含真實 `database_id`／`account_id`，且沒有任何 `wrangler d1 execute` 被執行。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-034 與 TASK-025 的交付物（Python 全套 **971 passed**、Node **54 passed**），檔案樹 sha256 `2b1d1b16deec9d682570dd12603643f048129e431b39d8bf2bb78d1de0678a65`（115 檔，即 TASK-034 的 `checked_version`）。本次新增 `cloudflare/worker/src/admin.js`／`reapply.js`、`cloudflare/test/admin.test.mjs`／`reapply.test.mjs`，並修改 `cloudflare/worker/src/db.js`（新增 20 個 D1 轉接函式、移除一個無呼叫端的函式）、`cloudflare/worker/src/router.js`（`GET`／`POST /reapply` 與 405 訊息）、`cloudflare/test/router.test.mjs`（路由表由兩端點改為四端點）（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-035.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-035.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-d1-admin` sha256:45876364bc01a9749bb4597dcbd6f98453525f31b72ac3b2710a0d5dc4ff78f5（原始碼樹，119 檔）；`worker/src/admin.js` `c1c1c2f9…`、`reapply.js` `59d4bf7d…`、`db.js` `0cb8c051…`、`router.js` `e5891be0…`、`test/admin.test.mjs` `4d6b33a0…`、`test/reapply.test.mjs` `418bb86c…`、`test/router.test.mjs` `901aefe8…`；Node `node --test` **82 passed**（80 個測試案例）、Python 全套 **971 passed**；變異矩陣 40 個 → **40 偵測到**（0 存活、0 無效）
- 取消、重開或變更原因：無（第 1 輪 Review 修正四個測試自身的錯誤、移除一個沒有呼叫端的函式，並補強三個變異存活者的案例）
