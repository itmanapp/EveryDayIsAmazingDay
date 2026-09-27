# TASK-033 Code Review

- task_id：TASK-033
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-cloudflare-license sha256:729d545795e5a2158bcd15cfaa77f3a6189b73e50d1206b45e95fbdc40cec362
- Task／Spec 版本：TASK-033 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-25，第 1 輪（含兩個變異存活者的處理、跨 Task 測試穩健性調整與 `node:sqlite` 假 D1 的取捨）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `9831e0acb59672b1c9af4bae7c419aad8438f814f67abb5c74028d3f92bb3d55`（94 個檔案，即 TASK-032 的 `checked_version`；`cloudflare/` 尚不存在）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `729d545795e5a2158bcd15cfaa77f3a6189b73e50d1206b45e95fbdc40cec362`（110 個檔案）；本張新增 `cloudflare/` 下 16 個檔案（逐檔 sha256 見 TDD 的交付檔案表）；修改 `tests/test_update.py` `c8df0673…`（見 A-10）
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：`cloudflare/schema.sql`、`cloudflare/wrangler.toml`、`cloudflare/package.json`、`cloudflare/worker/src/{lease,http,db,activate,renew,router}.js`、`cloudflare/test/{support,fake-d1}.mjs`、`cloudflare/test/{lease,activate,renew,schema,router}.test.mjs`＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`ediaad/markets/catalog.py`（TASK-017）、`ediaad/license.py`（TASK-028～031）本張只**對齊契約**未修改；Python 產品程式碼本張完全未動（唯一的 Python 變更是 TASK-032 的測試檔，見 A-10）
- 程式規範來源：`docs/workflow/SPEC.md` AC-060、第 5 節租約「資料契約」與 `cloudflare/worker/src/` 的公開 API、第 7 節測試策略列（`cloudflare/worker` 純函式以 `node --test` 與假 D1 驗證）、第 2 節 out of scope（不部署、無真實帳號）；`docs/workflow/tasks/TASK-033.md`；`docs/architecture/ENGINEERING-REPORT.md` 第 6.7 節（兩個端點、D1 五表、Secret 私鑰、`renewals` 的 `trigger` 設計）、第 6.4 節「撤銷與導流」（**後端必須拒絕已過期租約的 renew 回 403**）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-060（合法密鑰回簽章租約） | `worker/src/activate.js`、`worker/src/lease.js`；`test/activate.test.mjs` 的 10 個案例與 `test/lease.test.mjs` 的 8 個案例 | 符合 | A-1～A-4、A-6、A-7 |
| AC-060（每次 renew 寫 `renewals` 並記 `trigger`） | `worker/src/renew.js`、`worker/src/db.js`；`test/renew.test.mjs` 的三種 trigger 與「恰一筆」案例 | 符合 | A-5 |
| AC-060（撤銷者被拒絕） | `renew.js`／`activate.js` 的 revoked 分支＋`blacklist` 查詢；`test/renew.test.mjs`／`test/activate.test.mjs` | 符合 | A-3 |
| AC-060（**過期租約的 renew 回 403**） | `renew.js` 的 `expires_at` 判斷（含讀不懂時 fail closed）；`test/renew.test.mjs` 的兩個 403 案例 | 符合 | A-5 |
| 租約欄位與 SPEC 第 5 節一致、有效期 30 天 | `leasePayload`／`signLease`；金標 canonical JSON 與金標簽章；30 天以「到期 − 簽發」斷言 | 符合 | A-4 |
| 簽章私鑰由 `env` 的 secret 注入 | `lease.js` 的 `privateKeyJwk`（`LICENSE_PRIVATE_KEY_JWK`）；缺設定時拒絕簽章並回固定 500 | 符合 | A-6、A-8 |
| `cloudflare/schema.sql` 定義五張表 | `schema.sql`；`test/schema.test.mjs`（恰五張表、欄位、UNIQUE／CHECK、索引） | 符合（五張表的**完整後台操作**屬 AC-062／TASK-035） | — |
| `cloudflare/wrangler.toml` 只有佔位值 | `wrangler.toml`；`test/schema.test.mjs` 的佔位與「不得含真實識別碼」斷言 | 符合 | A-9 |

逐條核對（AC-060）：

- **合法者回傳以私鑰簽章的租約**：`POST /v1/activate` 以 `key`（secret）查詢密鑰列 → 建 30 天租約內容 → WebCrypto Ed25519 簽章 → 回傳**租約物件本身**（鍵恰為 `catalog_version`／`expires_at`／`features`／`issued_at`／`key_id`／`machine`／`sig`）。簽章範圍是 `canonicalJson`（鍵排序、無空白），**與 Python `signing_payload` 的金標字串逐字相同**，且 Node 簽出的簽章**逐字等於 Python 夾具簽出的簽章**——因此「客戶端驗得過」是交叉實作的證據，不是宣稱。符合。
- **每次 renew 寫入 `renewals` 並記錄 `trigger`**：成功的續期恰寫一筆（`key_id`／`fingerprint`／`trigger`／`version`／`created_at`），三種 trigger 各自如實；非法 trigger 在寫入前就回 400。符合。
- **撤銷者被拒絕**：`keys.status = 'revoked'` 或請求指紋命中 `blacklist` → 403（activate 為 4xx 並帶訊息），**不簽發租約、不寫 `renewals`、不延長到期**。`verifyLicenseKey` 刻意對已撤銷者回傳整列，讓 handler 能給「已被撤銷」而不是「找不到這把密鑰」。符合。
- **過期租約的 renew 回 403**：`keys.expires_at < now` → **403 ＋ `status:"expired"`**，不寫 `renewals`、不延長；到期時間**無法解讀時同樣回 403**（fail closed）。這正是 TASK-031 的 A-1 所指的後端那一半。符合。

## 品質 Review

- **跨實作的金標貫穿兩端（本張最重要的品質基礎）**：`canonicalJson` 以 Python 產生的金標字串固定（`test/lease.test.mjs`），`signLease` 以 Python 夾具的簽章固定，金鑰是 RFC 8032 的公開測試向量。變異 `L03`（拿掉鍵排序）與 `L04`（分隔符多一個空白）都被金標測試當場抓到——這兩個正是「兩邊各自都覺得自己是對的」而客戶端全數驗章失敗的典型。
- **假 D1 執行的是真的 SQL**：`test/fake-d1.mjs` 建立在 `node:sqlite` 上，`schema.sql` 與每一句查詢真的被 SQLite 執行。變異 `D03`（把 `blacklist` 查詢寫成 `keys`）與 `S05`（`expires_at` 改名）都以 SQL 錯誤或欄位斷言失敗被抓到；手寫字串比對的替身做不到這件事。
- **單一簽章範圍**：`canonicalJson` 是 Worker 端唯一的序列化點，`signing_payload` 是 Python 端唯一的序列化點，兩者以金標釘住；沒有任何地方「順手」用 `JSON.stringify` 簽章（`L10` 把 `sig` 改名 `signature` 會被測試抓到）。
- **導流閘門只有一條路**：`expires_at` 的判斷集中在 `handleRenew`，並在每一條拒絕路徑上都先返回（測試對每種拒絕都斷言「`renewals` 0 筆、`keys.expires_at` 未變」）。過期的判斷採 **fail closed**：讀不懂的時間視為過期，不默默延長授權。
- **錯誤格式同時服務兩個讀者**：回應是 `{"error":{"code","message"},"message":..., ...}`——SPEC 第 5 節的格式在，Python 客戶端的 `_body_message`（只認字串值的 `message`）也讀得到可讀訊息；導流用的 `status` 只在 403 出現。未知例外一律回固定的 500 訊息（`logUnexpected` 只把訊息寫進 Cloudflare 日誌，不把堆疊放進回應），變異 `H01`（拿掉頂層 `message`）被測試抓到。
- **密鑰與私鑰的邊界清楚**：簽章私鑰只從 `env.LICENSE_PRIVATE_KEY_JWK`（secret）來，`wrangler.toml` 不得出現它（有測試）；缺少或格式不對時**拒絕簽章**而不是簽出無效租約。`keys.secret` 只用於 activate 的查詢，renew 走 `key_id`（有測試證明兩者不可互換）。
- **資料層的幂等與唯一性**：`upsertDevice` 用 `ON CONFLICT(fingerprint)`（重複啟用只留一列、`first_seen` 不變、`last_seen` 更新）；`schema.sql` 以 `IF NOT EXISTS` 可重複套用；`renewals.trigger` 的 CHECK 讓資料庫成為最後一道防線。
- **變異矩陣的強度**：53 個變異在凍結版**全數被抓到**；第一階段抓到的 2 個存活者都是**真實的測試缺口**（`first_seen` 沒被斷言、索引只斷言「有一個含 renewals 的」），已補強而非放寬實作。
- **測試品質**：全程離線、不需要 `wrangler` 或 npm；每個端點案例同時斷言「回應」與「假 D1 內實際落表的列」；沒有任何測試以 `sleep` 等待。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 交付檔案超出 Task 文件清單 | advisory（需追認） | 新增 `cloudflare/package.json`（只宣告 `"type": "module"` 與 `"test": "node --test"`，**無依賴**）：沒有它，Node 會把 `worker/src/*.js` 當 CommonJS，ESM `import` 無法執行 | 追認：這是 Worker 專案的慣例（Wrangler 也吃 `package.json`），且不引入任何 npm 依賴 | 已記錄（`node --test` 的 42 個案例都靠它執行） |
| A-2 | 交付檔案超出 Task 文件清單 | advisory（需追認） | 另有 `worker/src/http.js`、`test/support.mjs` 與四個額外測試檔（`lease`／`renew`／`schema`／`router`），比 Task 文件列的「activate.test.mjs／fake-d1.mjs」多 | 追認：`http.js` 是兩個 handler 共用的請求／回應規則（錯誤格式只有一份），測試檔依端點拆分讓失敗定位更快；Task 文件的清單本來就註明「實作前重新查證」 | 已記錄（TDD 的交付檔案表是權威清單） |
| A-3 | 安全 | advisory | `keys.secret` 以**明文**存 D1（activate 需要以 secret 查詢）；資料庫若外洩，所有未使用的密鑰可直接被啟用 | 報告第 6.7 節未要求雜湊；上線前可改存 `sha256(secret)` 並以 mail 或申請頁一次性顯示密鑰。這是**真實的取捨**，應在 DELIVERY 明列或另開 Task | 已記錄（目前與 TASK-035 的「批次產生密鑰」一致：密鑰要能交給使用者） |
| A-4 | 與 TASK-034 的接縫 | advisory | 租約的 `catalog_version` 來自密鑰列 → `env.CATALOG_VERSION` → `"unknown"`；若 TASK-034 的 manifest 帶的 `catalog_version` 與此不同，客戶端的 catalog 更新判斷會以 manifest 為準（不影響授權） | TASK-034 應讓 manifest 的 `catalog_version` 與 `wrangler.toml` 的 `CATALOG_VERSION` 同源（同一份設定或部署腳本注入），避免兩個版本來源分岔 | 待辦（已記於 `STATE.md` 待決事項） |
| A-5 | 狀態碼語意 | advisory | 機器不符刻意用 **409**（Task 文件只說 4xx）；過期／撤銷才用 403 並帶 `status` | 追認：把「機器不符」混進 403 會讓客戶端顯示「請重新申請新密鑰」的誤導訊息。測試斷言 409 且**不得**帶 `status` | 已記錄（`test/renew.test.mjs`） |
| A-6 | 濫用防護 | advisory | 沒有速率限制（activate 可被暴力嘗試密鑰、renew 可被大量呼叫） | 報告未要求；上線前應加 Cloudflare Rate Limiting 或 Worker 內的計數（D1／KV），並考慮 activate 的失敗計數 | 已記錄（TDD 的「未執行或受阻」第 4 點） |
| A-7 | 時鐘注入與 Workers 簽章 | advisory | handler 的第三個參數在正式執行時是 Workers 的 `ExecutionContext`，本服務不使用它；測試以 `{ now }` 注入時鐘（`resolveNow` 只讀 `options.now`） | 追認：正式路徑不傳第三個參數（`Date.now()`），因此 ctx 不會被誤讀；若日後要用 `ctx.waitUntil`，應改成明確的選項物件 | 已記錄（`router.js` 的檔頭說明） |
| A-8 | 觀測性 | advisory | 未預期例外只以 `console.error` 記「訊息」（Cloudflare 日誌），已刻意不放堆疊到回應 | 若要完整堆疊，應改記 `error.stack`（伺服器端）並確認日誌保留策略；本張的測試只斷言**回應**不含堆疊 | 已記錄（`logUnexpected`） |
| A-9 | 部署設定 | advisory（人工複核） | `wrangler.toml` 的三處佔位（`account_id`／`database_id`／路由）與 `CATALOG_VERSION` 需在部署時填入；路由目前以註解保留（`.invalid` 網域） | 部署前逐項填入並確認沒有把真實識別碼提交進版控（測試已斷言「不得含 32 位十六進位與 `.workers.dev`」） | 已記錄（人工複核項） |
| A-10 | 跨 Task 的測試變更 | advisory（需在 TASK-037 複核） | `tests/test_update.py`（TASK-032 的證據）被調整：背景執行緒輪詢上限 10 秒 → 30 秒。因此**該檔的 sha256 與 TASK-032 的 `checked_version` 不同**（TASK-032 的凍結版仍對應它當時的內容；產品程式碼未變） | TASK-037 的整體驗收應以「現行檔案樹」重跑全套並在 DELIVERY 說明這類「後續 Task 調整前一張測試」的差異 | 已記錄（TDD 的「如實記載」第 5 點） |
| A-11 | 真實後端未驗證 | advisory（**未執行**） | 無帳號／D1／網域、`wrangler` 未安裝，因此「真的部署起來」與真實 D1 的行為未驗證；`node:sqlite` 與 D1 在 SQL 方言與 `meta` 細節上可能有差異 | 取得帳號後：`wrangler d1 execute --file schema.sql`、`wrangler dev` 跑一次 activate／renew、以 Python 客戶端做一次端到端（TASK-036／037） | 待辦（DELIVERY 明列） |
| A-12 | 流程記載 | advisory（非程式） | （a）`AUTOINCREMENT` 讓 `sqlite_sequence` 出現，一度讓「恰五張表」失敗；（b）測試 helper 對 GET 帶主體觸發 undici 的 `TypeError`；（c）索引測試的寬鬆斷言與 `first_seen` 未被斷言，各造成一個變異存活者 | 已全部修正並如實記載（TDD 的「如實記載」第 1～4 點） | **已記載** |

## 修正與重審

- 第 1 輪 Spec Review：AC-060 的四項宣稱逐條符合（簽章租約、renewals 與 trigger、撤銷拒絕、過期回 403）；租約欄位、30 天、secret 注入與五張表 schema 亦符合。
- 第 1 輪品質 Review 修正 3 處：`schema.sql` 移除 `AUTOINCREMENT`（避免內部表讓「恰五張表」模糊）、假 D1 排除 `sqlite_*` 內部物件、測試 helper 對 GET／HEAD 不帶主體。
- 依變異檢查處理 **2 個真實存活者**：補 `first_seen` 不得被重複啟用覆寫的斷言（`D04`）、索引改成完整清單比對（`S04`）。
- 跨 Task 的測試穩健性調整 1 處：TASK-032 的 daemon 執行緒輪詢上限 10 秒 → 30 秒（詳見 A-10）。
- 重審：重跑 `node --test`（**42 passed**）、單檔逐一套（8／10／12／6／4）、Python 全套（**966 passed**）、兩個流程驗證器（exit 0），並在凍結版重跑變異矩陣（**53／53 偵測到，0 存活、0 無效**）；重讀 `lease.js`（canonical 與簽章）、兩個 handler 的每一條拒絕路徑、`db.js` 的九句 SQL、`schema.sql` 的五張表與索引、`router.js` 的兩個錯誤分支。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-060 四項逐條符合）
- 品質 Review：passed（無 blocking；A-1／A-2 為交付檔案清單的追認，A-3／A-6／A-8／A-11 為上線前的取捨與未驗證項，A-4／A-10 交後續 Task，A-5／A-7／A-9 已記錄，A-12 為流程記載）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1／A-2（追認新增檔案）、A-3（密鑰明文儲存需另外決定，報告未要求）、A-4（TASK-034 對齊 catalog 版本）、A-5／A-7（已記錄的刻意選擇）、A-6（速率限制需新需求）、A-8（日誌策略）、A-9（部署前人工複核）、A-10（TASK-037 複核跨 Task 測試差異）、A-11（需帳號與部署授權）、A-12（已記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：真實 Cloudflare 帳號／D1／部署未驗證（**未執行任何部署指令**）；`node:sqlite` 與 D1 的差異未實測；沒有速率限制；密鑰以明文存於 D1；`audit`／後台與重新申請頁屬 TASK-035；客戶端與 Worker 的端到端整合未跑（TASK-036／037）；`tests/test_update.py` 的調整使 TASK-032 的檔案雜湊與其 evidence 不同（A-10）
