# TASK-033：Cloudflare Worker 啟用與續租 API

- id：TASK-033
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-060"]
- depends_on：["TASK-001"]
- test_evidence：["docs/workflow/tdd/TASK-033.md"]
- review_evidence：["docs/workflow/reviews/TASK-033.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`cloudflare/worker/src/` 提供 `handleActivate(request, env)`、`handleRenew(request, env)`、`signLease(payload, env)`、`verifyLicenseKey(key, env)`；對合法密鑰的 `POST /v1/activate` 回傳以私鑰（WebCrypto Ed25519，私鑰由 `env` 的 secret 注入）簽章的租約，欄位與 SPEC 第 5 節租約 JSON 一致且有效期 30 天；對已撤銷密鑰拒絕；**對已過期租約的 `renew` 回 403**（否則導流被繞過）；每次成功的 `renew` 寫入 `renewals` 一筆並如實記錄 `trigger`（只接受 `start`／`timer`／`manual`）；`cloudflare/schema.sql` 定義 `keys`／`devices`／`renewals`／`blacklist`／`audit` 五張表；`cloudflare/wrangler.toml` 以佔位值（`account_id`、`database_id`、路由網域）填寫並可被 `node --test` 讀取，**不含任何真實資源識別碼**。
- 本張不做：不部署（`wrangler deploy` 未授權）、不連線或驗證真實 Cloudflare 帳號／D1／網域、不申請或持有真實簽章私鑰（測試只用合成密鑰與佔位 secret）、不做靜態 manifest 與 catalog 端點（TASK-034）、不做後台操作與公開重新申請頁（TASK-035）、不做客戶端純 Python 驗章（TASK-029／TASK-030）、不引入 npm 依賴。
- 每個 AC 在本張負責的範圍：AC-060 全部（合法密鑰回簽章租約、每次 renew 寫 `renewals` 並記 `trigger`、撤銷者被拒絕、過期租約的 renew 回 403）。靜態端點的 schema 與可快取性屬 AC-061（TASK-034）；五張表的完整後台操作與重新申請頁屬 AC-062／AC-063（TASK-035），本張只交付建表 SQL 與 activate／renew 所需的欄位。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-060、第 5 節模組表 `cloudflare/worker/src/` 的四個公開 API 與租約「資料契約」、第 7 節測試策略列（`cloudflare/worker` 純函式以 `node --test` 與假 D1 驗證）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.7 節（Worker API 兩個端點、D1 五表、Secret 私鑰、`renewals` 以 `count(trigger='start')` 區分啟動次數）、第 6.4 節「撤銷與導流」（後端必須拒絕已過期租約的 renew 回 403）、第 6.1 節元件圖（Worker `POST /v1/activate`、`POST /v1/renew`）；`docs/workflow/PROJECT.md` 的授權範圍（部署一律未授權）與環境實測表（Node v24.21.0、`wrangler` 未安裝、無真實帳號／D1／網域）。
- 模組與公開介面：`cloudflare/worker/src/` 下新增
  - `activate.js`：`handleActivate(request, env) -> Response`、`verifyLicenseKey(key, env) -> Promise<KeyRow|null>`。
  - `lease.js`：`signLease(payload, env) -> Promise<object>`（以 `env.LICENSE_PRIVATE_KEY_JWK` 佔位 secret 簽章）、`leasePayload(keyRow, machine, now, catalogVersion) -> object`、`LEASE_DAYS = 30`。
  - `renew.js`：`handleRenew(request, env) -> Response`（含過期回 403、撤銷回 4xx、`trigger` 驗證）。
  - `db.js`：D1 轉接層最小介面 `getKey(db, keyId)`、`getDevice(db, fingerprint)`、`insertRenewal(db, row)`、`touchDevice(db, row)`、`isRevoked(db, keyId)`，全部使用 `prepare().bind().first()/all()/run()`。
  - `router.js`：路徑 → handler 對照（含 `/v1/activate`、`/v1/renew`）。
  - `cloudflare/schema.sql`、`cloudflare/wrangler.toml`（佔位值＋註解標明待部署時填入）。
- 預計觸及的檔案：`cloudflare/worker/src/activate.js`、`cloudflare/worker/src/lease.js`、`cloudflare/worker/src/renew.js`、`cloudflare/worker/src/db.js`、`cloudflare/worker/src/router.js`、`cloudflare/schema.sql`、`cloudflare/wrangler.toml`、`cloudflare/test/activate.test.mjs`、`cloudflare/test/fake-d1.mjs`（測試專用記憶體 D1 轉接層）；實作前重新查證。
- 必要環境／依賴：Node v24.21.0，工作目錄 `cloudflare/` 執行 `node --test`（Node 內建測試框架與 `node:crypto`，不需 `wrangler`、不需 npm install、不需網路）；測試私鑰以 `crypto.subtle.generateKey("Ed25519", ...)` 現場產生，或使用 RFC 8032 向量的合成私鑰。

## 測試計畫

- 測試公開邊界：以節點測試直接呼叫 `handleActivate`／`handleRenew`，輸入以 `new Request(url, {method:"POST", body: JSON.stringify(...)})` 建構，`env` 注入假 D1（`cloudflare/test/fake-d1.mjs`）與佔位私鑰；斷言回應 `status` 與 JSON body，以及假 D1 內實際落表的列。
- 第一個失敗行為與預期斷言：檔案尚未建立時 `node --test` 找不到測試檔或 import 失敗；首案 `test_activate_returns_thirty_day_lease` 斷言合法密鑰回 200、租約鍵集合等於 SPEC 第 5 節的七個鍵加 `sig`、`expires_at − issued_at` 為 30 天、`machine` 等於請求送出的指紋、`features` 與 `keys` 列一致、`devices` 新增一列。
- 後續例外／邊界情境：
  1. 已撤銷密鑰（`keys.status = 'revoked'` 或命中 `blacklist`）→ 拒絕（4xx）且不簽發租約、不寫 `renewals`。
  2. **過期租約的 renew → 403**：`keys.expires_at < now` 時 `handleRenew` 必須回 403，且不寫 `renewals`、不延長到期。
  3. 每次成功 renew 寫入恰一筆 `renewals`；`trigger` 分別為 `start`／`timer`／`manual` 三種輸入皆正確落表；非法 `trigger`（如 `"cron"`、缺欄位）回 400 且不落表。
  4. 簽章可被對應公鑰驗證：以 `crypto.subtle.verify("Ed25519", publicKey, sig, canonicalPayload)` 對 `signLease` 的輸出斷言為真，並以改動 `expires_at` 一位元的負例斷言為假（證明到期日受簽章保護）。
  5. 缺欄位、非 JSON body、非 POST method → 回可讀錯誤 JSON（`{"error":{"code":...,"message":...}}`）與 4xx，不得洩漏 stack trace。
  6. `wrangler.toml` 內的 `account_id`／`database_id` 皆為佔位字串（測試斷言不含真實 UUID 或網域），避免誤把未授權資源寫進版控。
- 單項及相關回歸的實際命令／工作目錄：`cloudflare/` 下執行 `node --test`（單檔可用 `node --test test/activate.test.mjs`）；沿用 `docs/workflow/PROJECT.md` 的指令表。全套的回歸入口為 TASK-037。
- 非程式任務的替代驗證與理由：不適用。惟須誠實標示：真實 Cloudflare 帳號、D1 與部署無法驗證（無帳號／網域／部署授權），本張只以假 D1 驗證純函式與轉接介面，未驗證項由 TASK-037 的 DELIVERY 明列。
- 必要的人工檢查：無自動化可及的真實後端檢查；人工複核項僅為確認 `wrangler.toml` 不含真實資源識別碼、且沒有任何部署指令被執行。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-032 與 TASK-025 的交付物（Python 全套 **966 passed**），檔案樹 sha256 `9831e0acb59672b1c9af4bae7c419aad8438f814f67abb5c74028d3f92bb3d55`（94 檔，即 TASK-032 的 `checked_version`；`cloudflare/` 尚不存在）。本次新增 `cloudflare/` 下 16 個檔案（`schema.sql`／`wrangler.toml`／`package.json`／`worker/src/` 六個模組／`test/` 六個檔案），並調整 `tests/test_update.py` 的背景輪詢上限（TASK-032 測試的穩健性，逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-033.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-033.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-cloudflare-license` sha256:729d545795e5a2158bcd15cfaa77f3a6189b73e50d1206b45e95fbdc40cec362（原始碼樹，110 檔）；`cloudflare/schema.sql` `fae3fe0c…`、`wrangler.toml` `ecb88c71…`、`package.json` `cac00dfb…`、`worker/src/lease.js` `05cd3896…`、`http.js` `5a01c27f…`、`db.js` `ecfb3839…`、`activate.js` `e5d9b0c9…`、`renew.js` `5522e021…`、`router.js` `b8b050b2…`、`test/support.mjs` `f4fa76e3…`、`fake-d1.mjs` `2c3ec8d2…`、`lease.test.mjs` `edb06787…`、`activate.test.mjs` `4e0908fe…`、`renew.test.mjs` `368b0149…`、`schema.test.mjs` `6f8305d1…`、`router.test.mjs` `40f5a86b…`、`tests/test_update.py` `c8df0673…`；`node --test` **42 passed**（40 個測試案例）、Python 全套 **966 passed**；變異矩陣 53 個 → **53 偵測到**（0 存活、0 無效）
- 取消、重開或變更原因：無（第 1 輪 Review 移除 AUTOINCREMENT、處理 2 個變異存活者；另調整 TASK-032 測試的一處穩健性）
