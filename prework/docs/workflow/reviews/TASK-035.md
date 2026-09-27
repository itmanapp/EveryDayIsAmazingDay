# TASK-035 Code Review

- task_id：TASK-035
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-d1-admin sha256:45876364bc01a9749bb4597dcbd6f98453525f31b72ac3b2710a0d5dc4ff78f5
- Task／Spec 版本：TASK-035 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-25，第 1 輪（含三個變異存活者的處理、四個測試自身的錯誤修正與死碼移除）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `2b1d1b16deec9d682570dd12603643f048129e431b39d8bf2bb78d1de0678a65`（115 個檔案，即 TASK-034 的 `checked_version`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `45876364bc01a9749bb4597dcbd6f98453525f31b72ac3b2710a0d5dc4ff78f5`（119 個檔案）；本張新增 `cloudflare/worker/src/admin.js` `c1c1c2f9…`、`cloudflare/worker/src/reapply.js` `59d4bf7d…`、`cloudflare/test/admin.test.mjs` `4d6b33a0…`、`cloudflare/test/reapply.test.mjs` `418bb86c…`；修改 `cloudflare/worker/src/db.js` `0cb8c051…`、`cloudflare/worker/src/router.js` `e5891be0…`、`cloudflare/test/router.test.mjs` `901aefe8…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：上述七個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`cloudflare/schema.sql`（TASK-033 已交付五張表，本張只使用未修改）、`worker/src/{lease,http,activate,renew}.js` 未修改、`worker/src/static.js`（TASK-034）未修改、Python 產品程式碼完全未動
- 程式規範來源：`docs/workflow/SPEC.md` AC-062／AC-063、第 5 節模組表、第 7 節測試策略列（假 D1）、第 2 節 out of scope（不部署、無真實帳號）；`docs/workflow/tasks/TASK-035.md`；`docs/architecture/ENGINEERING-REPORT.md` 第 6.7 節（D1 五表、公開申請頁、後台功能、`renewals` 以 `count(trigger='start')` 區分啟動次數、活躍使用者 ≈ 過去 30 天有 renew 的 distinct key_id）、第 6.4 節「撤銷與導流」（重新申請頁對已撤銷指紋自動拒絕）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-062（五張表建立） | `cloudflare/schema.sql`（TASK-033 交付）；`cloudflare/test/schema.test.mjs` 的「恰五張表／欄位／約束／索引」 | 符合（**既有覆蓋**：本張沒有新的 Red） | — |
| AC-062（批次產生密鑰） | `admin.generateKeys`／`createKeys`；`test/admin.test.mjs` 的批次與序號案例 | 符合 | A-1～A-3 |
| AC-062（查詢清單與搜尋） | `admin.listKeys`／`db.findKeys`；遮蔽、篩選、搜尋、limit 案例 | 符合 | A-4、A-6 |
| AC-062（撤銷／恢復／延長） | `admin.revokeKey`／`restoreKey`／`extendKey`；黑名單互動與三種延長情境 | 符合 | A-5 |
| AC-062（統計以 `count(trigger='start')` 區分啟動次數） | `admin.stats`／`db.countStarts`／`countStartsForKey`；「3 start ＋ 2 timer → 3」與「不同 key_id 不互相加總」案例 | 符合 | A-9 |
| AC-062（每個後台寫入操作都在 `audit` 留一筆） | `admin.auditLog`（唯一寫入點）＋ 每個寫入操作的稽核斷言 | 符合 | A-1 |
| AC-063（過期者自助重新申請） | `reapply.handleReapply`；成功案例＋**以 TASK-033 的 `handleActivate` 真的啟用一次** | 符合 | A-3 |
| AC-063（黑名單指紋自動拒絕、不產生密鑰、不留可啟用的記錄） | `reapply.isBlacklisted` 的早退；黑名單案例斷言 `keys` 與 `audit` 都沒有新列 | 符合 | A-2 |
| AC-063（未命中黑名單且未過期者的行為有明確定義並被測試固定） | 未過期 → 409＋到期日；完全沒有紀錄 → 404；已撤銷但未進黑名單 → 403 | 符合 | — |
| 公開重新申請頁 | `reapplyPage()`／`handleReapplyPage`／`router.js` 的兩個新路由；頁面與路由案例 | 符合（最小 HTML 樣板，無前端框架、無外部資源） | A-1、A-2 |

逐條核對（AC-062／AC-063）：

- **批次產生**：`generateKeys(db, count, features, actor)` 產生 `EDIAAD-YYYY-NNNN` 的密鑰（狀態 `issued`、尚無到期日），**恰留一筆稽核**；序號取現有最大值 + 1，因此刪除後不重用（`key_id` 的 PRIMARY KEY 是最後一道防線）。參數不合法時**先失敗、不寫任何列**。符合。
- **清單與搜尋**：`listKeys` 預設遮蔽密鑰、預設由新到舊、附上每把密鑰的 `starts`／`renewals`；`status` 與 `search`（key_id／secret 子字串）都是綁定參數，`limit` 有上下限。符合。
- **撤銷／恢復／延長**：撤銷把 `keys.machine` 與 `devices` 兩條線索的指紋都放進 `blacklist`（冪等），恢復移除同一把密鑰的黑名單列並回到 `active`／`issued`；延長採「現在與原到期日的較晚者 + N 天」，因此**不會縮短**；三者都留一筆稽核，找不到密鑰時回 `unknown_key` 且不寫稽核。符合。
- **統計**：`starts` 只算 `trigger='start'`（timer 不算），逐把密鑰的 `starts` 不會互相加總；`active_last_30_days` 以 `COUNT(DISTINCT key_id)` 搭配 30 天前的切點；`keys` 的五個計數把已過期與已撤銷分開。符合。
- **稽核**：`auditLog` 是唯一的 `audit` 寫入點，自己驗證 `actor`／`action`，`details` 以 JSON 字串存、`created_at` 由注入時鐘決定。符合。
- **重新申請（AC-063）**：順序是「黑名單 → 有無紀錄 → 是否已撤銷 → 是否真的過期 → 才發新密鑰」，每一條拒絕路徑都在 `createKeys` 之前返回，因此不可能對黑名單或未過期的指紋發出密鑰；成功後把新密鑰交給使用者，並在測試中**真的走一次 `/v1/activate`**（簽章、指紋比對、30 天、落地）。符合。

## 品質 Review

- **安全性質是「順序」而不是「檢查」**：重新申請的四個判斷依序早退，任何一條成立就不會呼叫產生密鑰。測試對每一種拒絕都斷言 `keys` 與 `audit` **沒有新列**——這比只斷言狀態碼強（狀態碼對但偷偷寫了一筆才是最糟的）。
- **撤銷與恢復互為反操作，且與 TASK-033 對齊**：撤銷把指紋放進 `blacklist`，正好是 TASK-033 的 `handleRenew` 判 `status:"revoked"` 的依據（那條路徑在 TASK-033 已測）；恢復移除它，同一台機器才能重新申請。兩張 Task 的黑名單語意因此是同一個，不是兩套。
- **「稽核只記真的發生過的事」**：所有驗證都在寫入與稽核之前；找不到密鑰、參數不合法、黑名單指紋都不會留下任何稽核列。`auditLog` 是唯一寫入點，因此「每個寫入操作都有一筆稽核」靠的是「每個寫入操作都呼叫它」＋ 測試逐一斷言。
- **`trigger='start'` 的語意被釘住**：統計與逐把密鑰的 `starts` 都以 `WHERE trigger = 'start'` 為準，變異 `D03`（拿掉條件）被 `starts` 的斷言抓到；`A18`（把 starts 換成 renewals）也被抓到，代表「啟動次數」與「回報次數」在測試層是可分辨的。
- **遮蔽是預設、完整值要明確要求**：清單可能被截圖或誤傳，因此 `listKeys` 預設只露頭尾；後台需要「用密鑰找 key_id」時仍可搜尋（比對在 SQL 裡），但輸出維持遮蔽。
- **時間一律由呼叫端注入**：`createKeys`／`revokeKey`／`restoreKey`／`extendKey`／`stats`／`auditLog` 都接受 `{ now }`（毫秒），因此「序號的年份」「延期基準」「30 天切點」都能精確固定；`utcStamp` 沿用租約那一份（秒級、`Z` 結尾），所以資料庫裡的字串可以安全地做字典序比較（`findExpiredKeyForFingerprint` 就是在 SQL 裡比較）。
- **SQL 只有一份且全部綁定參數**：動態的 `findKeys` 只把「已驗證過的值」放進參數，子句本身是固定字串；指紋、密鑰、key_id 都不做字串串接。
- **假 D1 執行真的 SQL**：`node:sqlite` 讓 `schema.sql`、每一句查詢、UNIQUE 與 CHECK 約束都是真的被執行（變異 `D01`～`D07` 全部被抓到，其中 `D07` 把 `JSON.stringify(features)` 拿掉就撞上型別錯誤）。
- **變異矩陣的強度**：40 個變異在凍結版**全數被抓到**；第一階段的三個存活者都是**測試缺口**（`keys.machine` 與裝置列同值、撤銷與黑名單兩條路徑重疊、預設 features 從沒被走到），已各補一個案例擊殺，沒有為了全殺而放寬實作。
- **沒有動到既有契約**：`schema.sql`、`lease.js`、`http.js`、`activate.js`、`renew.js`、`static.js` 與 Python 產品程式碼完全未改；唯一的既有檔案變更是 `db.js`（新增函式與移除一個沒有呼叫端的函式）與 `router.js`（新增兩個路由，並修正 405 訊息讓它反映該路徑允許的方法）。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 後台沒有端點與認證 | advisory（**部署前必做**） | `admin.js` 只有純函式：沒有 `/admin/*` 路由、沒有登入／權限模型（`actor` 由呼叫端注入，測試以字串模擬）。任何人都不能從網路呼叫它——但也因此**目前沒有任何後台介面** | 部署時以 Cloudflare Access（或後台頁面＋驗證）包住一個薄的 `/admin` Worker；`actor` 應來自驗證身分而不是請求參數 | 已記錄（TDD 的「未執行或受阻」第 2 點） |
| A-2 | 重新申請頁的濫用防護 | advisory | `POST /reapply` 沒有速率限制：攻擊者可以用任意指紋列舉（只會對「已過期且未在黑名單」的指紋發新密鑰，但仍可大量嘗試） | 上線前加 Cloudflare Rate Limiting 或 Worker 內的失敗計數（與 TASK-033 的 A-6 同一項） | 已記錄（TDD 的「未執行或受阻」第 3 點） |
| A-3 | 重新申請的語意 | advisory | 重新申請只換一把新密鑰（`status='issued'`、無到期日）；使用者仍要完成啟用，租約才會被簽發。若使用者其實只是「還沒到期但想延長」，會拿到 409 而不是新密鑰 | 這是刻意的（授權一律由啟用流程簽發，重新申請頁不需要簽章私鑰）；延長屬後台操作。若日後要提供自助延長，需新的 AC 與金流／審核設計 | 已記錄（`handleReapply` 的檔頭說明；409 訊息附到期日） |
| A-4 | 清單的查詢效率 | advisory | `listKeys` 對每一列各發兩次 `COUNT`（N+1）；`limit` 上限 200，因此最差 400 次查詢。管理介面手動使用可接受 | 目錄變大時改成一次 `GROUP BY key_id` 的聚合查詢；`MAX_LIST_LIMIT` 已是現成的節流閥 | 已記錄（`MAX_LIST_LIMIT = 200`） |
| A-5 | 黑名單的歸屬 | advisory | 黑名單以 `fingerprint` 為主鍵、附帶 `key_id`；`restoreKey` 只刪「同一把 `key_id`」的列。若某指紋曾被另一把已撤銷的密鑰列入黑名單，恢復這一張不會解除那個封鎖 | 這是刻意的（黑名單是「這個指紋曾經被撤銷」的紀錄，恢復只針對該筆授權）；若要跨密鑰解除，應提供明確的管理操作並留稽核 | 已記錄（`removeBlacklistForKey(db, keyId)`） |
| A-6 | 短密鑰的遮蔽 | advisory | `maskSecret` 對長度 ≤ 8 的密鑰回 `"…"`（不洩漏任何字元） | 可接受；正常密鑰是 32 字元 | 已記錄（`test/admin.test.mjs` 的遮蔽案例） |
| A-7 | 跨 Task 的測試變更 | advisory（需在 TASK-037 複核） | `cloudflare/test/router.test.mjs`（TASK-033 的證據）由「恰兩個端點」改為「恰四個端點」（本張依 AC-063 新增 `GET`／`POST /reapply`），因此該檔的 sha256 與 TASK-033 的 `checked_version` 不同 | TASK-037 的整體驗收應以現行檔案樹重跑並在 DELIVERY 說明（與 TASK-032 測試的 10→30 秒調整同類） | 已記錄（TDD 的 Cycle 7；STATE 的待決事項） |
| A-8 | 真實 D1 與後台 UI 未驗證 | advisory（**未執行**） | 沒有帳號／`database_id`，**未執行任何 `wrangler d1 execute`**；`schema.sql` 在 D1 上的執行結果、D1 對這些查詢的相容性與後台 UI 都未驗證 | 取得帳號後：`wrangler d1 execute --file schema.sql`、以 `node --test` 的同一組情境對真實 D1 跑一次、再接上後台（TASK-037 的 DELIVERY 明列） | 待辦 |
| A-9 | `expired` 的計數來源 | advisory | `stats.keys.expired` 是「DB 裡狀態為 `expired` 的列」＋「`expires_at` 已過且狀態不是 `revoked`／`expired` 的列」；不維護狀態轉移（時間到了不會自動改 `status`） | 刻意如此：狀態由資料本身（到期時間）決定，避免需要定時工作；若日後要做「到期自動通知」，應另開 Task | 已記錄（`countExpiredKeys` 的 SQL） |
| A-10 | 流程記載 | advisory（非程式） | 四個測試自身的錯誤：（a）假密鑰每批重新編號 → UNIQUE 撞鍵；（b）統計測試的筆數算錯（6 寫成 5）；（c）`seedKey` 對同一指紋插第二筆裝置 → 主鍵撞鍵；（d）撤銷測試的幂等斷言少算一個指紋。另移除一個沒有呼叫端的 `db.getKeyByMachine` | 已全部修正並如實記載（TDD 的「如實記載」第 1～5 點） | **已記載** |

## 修正與重審

- 第 1 輪 Spec Review：AC-062 的六項與 AC-063 的三項逐條符合；五張表的建立沿用 TASK-033 已凍結的 `schema.test.mjs`（既有覆蓋，本張沒有新的 Red）。
- 第 1 輪品質 Review 修正 5 處：四個測試自身的錯誤（假密鑰編號、筆數、裝置主鍵、幂等斷言）與一個沒有呼叫端的 `db.getKeyByMachine`。
- 依變異檢查處理 **3 個真實存活者**：補「只有機器欄位、沒有裝置列」的撤銷案例（`A07`）、「已撤銷但沒有黑名單紀錄」的重新申請案例（`R02`）、「features 欄位壞掉」的重新申請案例（`R07`）。
- 重審：重跑 `node --test`（**82 passed**）、逐檔（admin 17／reapply 11／router 4）、Python 全套（**971 passed**）、兩個流程驗證器（exit 0），並在凍結版重跑變異矩陣（**40／40 偵測到，0 存活、0 無效**）；重讀 `admin.js` 的每個寫入路徑與稽核、`reapply.js` 的四條拒絕路徑、`db.js` 新增的每一句 SQL、`router.js` 的 405 分支與重新申請頁的 HTML。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-062／AC-063 逐條符合；五張表為既有覆蓋）
- 品質 Review：passed（無 blocking；A-1／A-2 為部署前必做，A-3～A-6／A-9 為已記錄的刻意選擇，A-7 交 TASK-037 複核，A-8 未驗證，A-10 為流程記載）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（後台端點與認證屬部署階段，需新需求或 Cloudflare Access）、A-2（速率限制需新需求）、A-3（自助延長需新的 AC）、A-4（目錄變大再優化）、A-5（跨密鑰解除黑名單需新的管理操作）、A-6（可接受）、A-7（TASK-037 複核跨 Task 測試差異）、A-8（需帳號與部署授權）、A-9（狀態由資料決定）、A-10（已記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：真實 D1 migration 與後台 UI 未驗證（未執行任何 `wrangler d1 execute`）；後台沒有 HTTP 端點與認證；重新申請沒有速率限制；新密鑰直接顯示在頁面上（無 Email 通知）；`active_last_30_days` 是近似值且依賴伺服器時間；`listKeys` 為 N+1 查詢（上限 200）
