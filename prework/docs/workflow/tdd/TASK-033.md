# TASK-033 測試紀錄

- task_id：TASK-033
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-cloudflare-license sha256:729d545795e5a2158bcd15cfaa77f3a6189b73e50d1206b45e95fbdc40cec362
- alternative_reason：**部分替代**——真實 Cloudflare 帳號、D1 與部署無法驗證（無帳號／網域，且部署未授權，見 `PROJECT.md` 的對外動作清單）；本張以「**真的 SQL**（假 D1 建立在 Node 內建的 `node:sqlite` 上，因此 `schema.sql` 與每一句查詢都是真的被 SQLite 執行）＋ 注入的時鐘 ＋ RFC 8032 公開測試向量金鑰」在 `node --test` 下逐條固定；`wrangler` 未安裝、也沒有任何部署指令被執行（人工複核項）。未驗證項由 TASK-037 的 DELIVERY 明列。
- Task／Spec 版本：TASK-033 / SPEC-001 v0.4
- 測試邊界：（1）純函式：`canonicalJson`／`utcStamp`／`leasePayload`／`signLease`／`verifyLicenseKey`；（2）端點：以 `new Request(...)` 直接呼叫 `handleActivate`／`handleRenew`（以及經由 `handleRequest` 的路由），`env` 注入假 D1 與佔位私鑰，斷言回應的 `status`／JSON 與假 D1 內**實際落表的列**；（3）`schema.sql` 在空資料庫上的建表、欄位、UNIQUE／CHECK 約束與索引；（4）`wrangler.toml` 只有佔位值。全程離線、不需要 `wrangler`、不需要 npm install。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-032 與 TASK-025 的交付物（`cloudflare/` 尚不存在），Python 全套 **966 passed**（本張完成後同為 **966 passed**，Node 為 **42 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `9831e0acb59672b1c9af4bae7c419aad8438f814f67abb5c74028d3f92bb3d55`（94 個檔案，即 TASK-032 的 `checked_version`）。
- TDD 不適用的理由與替代驗證（若有）：見「未執行或受阻」第 1 點（真實 Cloudflare 後端與部署）。

工作目錄一律為 `ocaievo/cloudflare/`，命令一律為 `node --test`（可用 `node --test test/<檔名>.test.mjs` 跑單檔）。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `cloudflare/schema.sql` | `fae3fe0c` | 新增：`keys`／`devices`／`renewals`／`blacklist`／`audit` 五張表（`IF NOT EXISTS`，可重複套用）＋ 五個索引；`renewals.trigger` 有 CHECK 约束 |
| `cloudflare/wrangler.toml` | `ecb88c71` | 新增：`main`／`compatibility_date`／D1 綁定 `DB`／`CATALOG_VERSION` var；`account_id`／`database_id` 一律 `REPLACE_WITH…`，路由以 `.invalid` 網域註解掉 |
| `cloudflare/package.json` | `cac00dfb` | 新增：只宣告 `"type": "module"` 與 `"test": "node --test"`（**無任何依賴**）；`worker/src/*.js` 因此是 ESM |
| `cloudflare/worker/src/lease.js` | `05cd3896` | 新增：`canonicalJson`（與 Python `signing_payload` 同一種 bytes）、`utcStamp`／`expiresAt`、`leasePayload`、`signLease`（WebCrypto Ed25519，私鑰由 secret 注入）、`LEASE_DAYS`／`LEASE_FIELDS` |
| `cloudflare/worker/src/http.js` | `5a01c27f` | 新增：`jsonResponse`／`errorResponse`／`RequestError`／`readJsonBody`／`requireText`／`optionalText`／`requireMachine`／`resolveNow`／`resolveCatalogVersion`／`requireDb`／`logUnexpected` |
| `cloudflare/worker/src/db.js` | `ecfb3839` | 新增：D1 轉接層（`getKeyBySecret`／`getKeyById`／`getDevice`／`isBlacklisted`／`countRenewals`／`upsertDevice`／`insertRenewal`／`markKeyActivated`／`markKeyRenewed`），全部使用綁定參數 |
| `cloudflare/worker/src/activate.js` | `e5d9b0c9` | 新增：`handleActivate`、`verifyLicenseKey`（以 secret 查詢，**已撤銷者也回傳整列**讓 handler 能區分訊息） |
| `cloudflare/worker/src/renew.js` | `5522e021` | 新增：`handleRenew`、`RENEW_TRIGGERS`（過期／撤銷回 403 並附 `status`；機器不符回 409） |
| `cloudflare/worker/src/router.js` | `b8b050b2` | 新增：`ROUTES`（恰兩個端點）、`handleRequest`／預設 export `fetch` |
| `cloudflare/test/fake-d1.mjs` | `2c3ec8d2` | 新增：記憶體假 D1（`node:sqlite`），介面對齊 `prepare().bind().first()/all()/run()`＋`batch` |
| `cloudflare/test/support.mjs` | `f4fa76e3` | 新增：測試夾具（RFC 8032 金鑰 JWK、金標 canonical 與簽章、`Request` 建構、建表資料列的 helper） |
| `cloudflare/test/lease.test.mjs` | `edb06787` | 新增：8 個測試 |
| `cloudflare/test/activate.test.mjs` | `4e0908fe` | 新增：10 個測試 |
| `cloudflare/test/renew.test.mjs` | `368b0149` | 新增：12 個測試 |
| `cloudflare/test/schema.test.mjs` | `6f8305d1` | 新增：6 個測試 |
| `cloudflare/test/router.test.mjs` | `40f5a86b` | 新增：4 個測試 |
| `tests/test_update.py` | `c8df0673` | 修改（TASK-032 的測試）：背景執行緒輪詢的上限由 10 秒放寬為 30 秒，理由見「如實記載」第 5 點 |

## Cycle 1：租約內容與簽章（8 個測試）

- 測試：`canonicalJson` 的輸出**逐字等於** Python `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))` 的金標字串（且等於測試端獨立參考實作的輸出）、與鍵的插入順序無關；`signLease` 以 RFC 8032 TEST 1 金鑰簽出的 `sig` **逐字等於 Python 夾具簽出的簽章**（Ed25519 決定性），且是 128 個小寫十六進位字元；改動 `expires_at` 或 `machine` 一位元就驗不過（以 WebCrypto 對應公鑰驗章）；`utcStamp` 是秒級、`Z` 結尾、不含毫秒；`leasePayload` 的鍵恰為 SPEC 第 5 節的六個（不含 `sig`）、`expires_at − issued_at` 恰為 30 天、`features` 由 JSON 字串解析；`machine`／`catalog_version`／`features`（非法 JSON、空陣列）不合法時丟出可讀錯誤；缺少／空字串／壞 JSON／型別不對／缺 `d` 或 `x` 的私鑰 secret 一律拒絕簽章且訊息指出原因。
- 實作：`lease.js`（含 `LEASE_DAYS = 30`）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `node --test` | 1 | 4 個測試檔 `ERR_MODULE_NOT_FOUND`（`worker/src/*.js` 不存在）＋ 6 個 schema 測試失敗（`schema.sql`／`wrangler.toml` 不存在） | 尚未有 `cloudflare/`／2026-09-25 |
| Green | `node --test test/lease.test.mjs` | 0 | `ℹ tests 8 / pass 8 / fail 0` | snap-2026-09-24-ocaievo-cloudflare-license／2026-09-25 |

- **跨實作的金標不是「兩邊都說自己是 Ed25519」**：金標字串來自 Python 的 `signing_payload`，金標簽章來自 Python 的 `tests/_ed25519_fixture.py`（同一把 RFC 8032 TEST 1 公開向量金鑰）。Node 端必須得到同樣的 bytes 與同樣的簽章，因此「Worker 簽的租約能被客戶端 `ed25519_verify` 驗過」是**交叉實作**的證據。
- **私鑰只以 secret 注入**：`env.LICENSE_PRIVATE_KEY_JWK`（`wrangler secret put`）；`wrangler.toml` 不得出現私鑰（有測試斷言）。缺設定時 `signLease` 直接拒絕，不會簽出沒人能驗的租約——handler 端則回固定的 500（不洩漏設定內容）。

## Cycle 2：`schema.sql` 與 `wrangler.toml`（6 個測試）

- 測試：空資料庫上建立**恰五張表**；`schema.sql` 可重複套用；`activate`／`renew` 用到的每個欄位都存在；資料庫層的約束是真的（`renewals.trigger` 的 CHECK 擋下 `'cron'`、`keys.secret` UNIQUE、`blacklist.fingerprint` 唯一）；五個索引名稱逐一如預期；`wrangler.toml` 的 `main`／`binding = "DB"`／兩個 `REPLACE_WITH…` 佔位、且**不含** 32 位十六進位識別碼、不含 `.workers.dev` 網域、不含私鑰設定（但要留下 secret 名稱的說明）。
- 實作：`schema.sql`、`wrangler.toml`、`package.json`、`fake-d1.mjs`。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/schema.test.mjs` | 0 | `ℹ tests 6 / pass 6 / fail 0` |

- **假 D1 刻意建立在 `node:sqlite` 上**：D1 就是 SQLite，所以 `schema.sql` 與每一句查詢在測試裡都是真的被執行——欄位名拼錯、語法錯誤、UNIQUE／CHECK 違反當場失敗。手寫一個字串比對式的「假 SQL」會讓這些都測不出來（變異 `D03` 把 `blacklist` 寫成 `keys` 就是靠這一點被抓到）。
- 與真實 D1 的差異（網路、`meta` 細節、migration 行為）不在本張的可驗證範圍，已記於「未執行或受阻」。

## Cycle 3：啟用端點（10 個測試）

- 測試：合法密鑰 → 200、回應**就是租約物件**（鍵恰為七個）、`machine` 等於請求指紋、30 天、`features` 與密鑰列一致、簽章可被公鑰驗證、`keys` 列被更新為 `active` 且記下 `machine`／`expires_at`／`activated_at`、`devices` 新增一列、**不寫 `renewals`**；`platform`／`version` 選填且如實記錄；同一把密鑰重複啟用是幂等的（以新的現在時間重算 30 天、`devices` 仍只有一列、`first_seen` 不變、`last_seen` 更新）；已撤銷密鑰 → 4xx＋訊息含「撤銷」且不簽發、不改狀態、不延長到期；黑名單指紋 → 4xx＋訊息含「黑名單」且密鑰狀態不變、無裝置紀錄；未知密鑰 → 404＋`error.code="unknown_key"`；`verifyLicenseKey` 以 secret 查詢且**對已撤銷者也回傳整列**（否則 handler 無法區分「查無此密鑰」與「已撤銷」）；八種不合法請求（GET／壞 JSON／陣列主體／缺 `key`／空白 `key`／缺 `machine`／非十六進位／大寫十六進位）各自回對應狀態與 `error.code`，且回應有**字串的 `message`**（Python 客戶端的 `_body_message` 讀它）且不含堆疊；沒有簽章私鑰時回固定訊息的 500、不留裝置紀錄；`catalog_version` 的來源順序（密鑰列 → 環境變數 → `"unknown"`）。
- 實作：`activate.js`、`http.js`、`db.js`、`lease.js`。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/activate.test.mjs` | 0 | `ℹ tests 10 / pass 10 / fail 0` |

- **成功回應一個欄位都不多加**：Python 的 `Lease.from_json` 會拒絕多餘的鍵，因此「順手多包一層 `{lease: …}`」會讓客戶端直接失敗——測試以鍵集合斷言釘住。
- **「查無此密鑰」與「已撤銷」必須分開**（與 F-003 同一條紀律）：變異 `A05`（讓 `verifyLicenseKey` 對已撤銷者回 `null`）會讓使用者看到「找不到這把密鑰」而不是「已被撤銷」，測試抓到這個差異。

## Cycle 4：續租端點（12 個測試）

- 測試：成功續期 → 200、以新的現在時間重算 30 天、到期時間**真的比原本晚**、簽章可驗、恰一筆 `renewals`（`trigger`／`fingerprint`／`created_at` 如實）、`devices.last_seen` 更新、`keys.expires_at` 與租約一致且 `last_renewed_at` 寫入、狀態維持 `active`；三種 `trigger` 各自如實落表；**過期租約 → 403 ＋ `status:"expired"`、不寫 `renewals`、不延長、不附任何租約**；**到期時間讀不懂時 fail closed**（回 403 expired 且不覆寫壞值）；已撤銷 → 403 ＋ `status:"revoked"` 且不寫表；黑名單指紋 → 同樣 403 revoked；未知密鑰 → 404；**以 secret 當 `key` 續期 → 404**（證明續期查的是 `key_id`）；換一台機器 → 409（**不帶** `expired`／`revoked` 標記，避免被客戶端當成要重新申請）；尚未綁定機器的密鑰首次續期會綁定目前這台；五種非法 `trigger`（`cron`／空字串／數字／缺欄位／`TIMER`）各回 400 且不落表、不延長；五種不合法請求皆為可讀 JSON 且不含堆疊；連續三次續期都不會累加成非 30 天。
- 實作：`renew.js`（＋`http.js` 的 trigger 驗證與 `db.js` 的寫入）。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/renew.test.mjs` | 0 | `ℹ tests 12 / pass 12 / fail 0` |

- **403 是導流閘門**：過期與撤銷都回 403 但**用 `status` 區分**（客戶端 `_indicates_revoked` 只認 `status === "revoked"`；其餘 403 走「重新申請」訊息）。兩者都**不寫 `renewals`、不延長到期**，因此「用舊租約一直續期」在後端就被擋住（TASK-031 的 A-1 在此完成）。
- **機器不符刻意用 409**：它不是「要重新申請」的狀態，混進 403 會讓使用者看到誤導的導流訊息。
- **失敗一律不落地**：所有拒絕路徑都在寫入之前返回；測試對每一種拒絕都斷言 `renewals` 筆數為 0 且 `keys.expires_at` 未被改寫。

## Cycle 5：路由（4 個測試）

- 測試：`ROUTES` 恰有 `POST /v1/activate` 與 `POST /v1/renew` 兩個鍵；兩條路徑都通；未知路徑回 404（`error.code="not_found"`）、已知路徑用錯方法回 405（`method_not_allowed`、訊息提到 `POST`、不含堆疊）；Worker 的預設 export `fetch` 走同一個入口。
- 實作：`router.js`。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/router.test.mjs` | 0 | `ℹ tests 4 / pass 4 / fail 0` |

## Red → Green 的實際順序

| 階段 | 命令（`ocaievo/cloudflare/`） | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Red | `node --test` | 1 | 4 個測試檔 `ERR_MODULE_NOT_FOUND`＋6 個 schema 測試 `ENOENT`（測試先寫、實作不存在） |
| Green 1（實作完成） | `node --test` | 1 | `ℹ tests 42 / pass 35 / fail 7`（schema 的 `sqlite_sequence`、測試 helper 對 GET 帶主體） |
| Green 2 | `node --test` | 0 | `ℹ tests 42 / pass 42 / fail 0`（40 個測試案例＋2 個 Node 回報的檔案層級項目） |
| Green 3（凍結版） | `node --test` | 0 | `ℹ tests 42 / pass 42 / fail 0`（補強兩個存活者的斷言後） |

## 變異測試（兩階段：先殺存活者，再跑凍結版）

- 工具：`/tmp/mutate_task033.py`（整行／整段替換、`count(frm) == 1` 才套用、每輪逾時 180 秒、跑完立即還原並比對 sha256、`flock` 確保單一行程、**SIGTERM／SIGINT／`atexit` 會還原正在跑的變異**；測試指令為 `node --test <相關測試檔>`，結果以 `ℹ pass`／`ℹ fail` 解析）。
- 矩陣：**53 個變異**（`lease.js` 12、`http.js` 7、`db.js` 8、`activate.js` 5、`renew.js` 11、`router.js` 3、`schema.sql` 6、`wrangler.toml` 1），涵蓋 canonical 序列化（排序、分隔、毫秒）、租約長度與欄位順序、指紋格式、features 解析、私鑰 JWK 的三種壞法、簽章長度、時鐘注入、`catalog_version` 的來源順序與佔位值、錯誤回應的形狀（頂層 `message`）與主體型別檢查、五個 D1 查詢／寫入的每一句 SQL（含欄位對調與 `ON CONFLICT`）、三個 activate 拒絕分支、續期的過期／撤銷／trigger／機器／延長五個決策點、路由表與兩個錯誤分支、schema 的 CHECK／UNIQUE／`IF NOT EXISTS`／欄位名／索引，以及 `wrangler.toml` 的佔位值。
- **第一階段抓到 2 個真實存活者，補強測試後擊殺**：
  1. `D04`（`upsertDevice` 的 `ON CONFLICT` 加上 `first_seen = excluded.first_seen`）——存活是因為「重複啟用只留一列」的測試只斷言了 `last_seen` 有更新。已補 `first_seen` 必須保持第一次的時間。
  2. `S04`（移除 `idx_renewals_key_id`）——存活是因為索引測試只斷言「有某個名字含 `renewals` 的索引」，而另外兩個索引仍在。已改成比對五個索引名稱的完整清單（索引名稱是交付物的一部分）。
- **最終凍結版結果：53／53 全數偵測到（0 存活、0 無效）**；逐輪輸出形如 `ℹ pass 9 / fail 1`。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `node --test`（工作目錄 `ocaievo/cloudflare/`） | 0 | `ℹ tests 42 / pass 42 / fail 0`（40 個測試案例） |
| `.venv/bin/python -m pytest -q`（工作目錄 `ocaievo/`） | 0 | `966 passed, 2 warnings in 152.62s` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |
| 凍結版檔案樹 | — | sha256 `729d545795e5a2158bcd15cfaa77f3a6189b73e50d1206b45e95fbdc40cec362`（110 個檔案） |

## 如實記載的實作／測試錯誤

1. **`AUTOINCREMENT` 讓「恰五張表」多一張**：`INTEGER PRIMARY KEY AUTOINCREMENT` 會讓 SQLite 建立內部的 `sqlite_sequence` 表，於是「恰五張表」的斷言失敗。已改為 `INTEGER PRIMARY KEY`（同樣自動配號，不需要 AUTOINCREMENT），並在假 D1 的 `tableNames()`／索引查詢排除 `sqlite_*` 內部物件。
2. **測試 helper 對 GET 帶主體**：`new Request(url, {method: "GET", body})` 在 undici 直接丟 `TypeError: Request with GET/HEAD method cannot have body`，因此「方法不對」的案例在建立請求時就爆掉（不是被測程式碼的問題）。已讓 helper 對 GET／HEAD 不帶主體。
3. **索引測試一開始被自己的寬鬆斷言掩蓋**（`S04` 存活者）：已改成完整清單比對。
4. **`first_seen` 的覆寫沒有被斷言**（`D04` 存活者）：已補。
5. **TASK-032 的 daemon 執行緒測試在整套高負載下出現一次 flake**：`test_background_without_an_executor_uses_a_daemon_thread` 以 10 秒為上限輪詢背景寫入的快取，在整套測試執行時曾觀察到一次超時（單獨執行該檔 3/3 穩定通過、全套重跑兩次皆通過）。已把上限放寬為 30 秒並加註理由——**這是跨 Task 的測試穩健性調整**，`tests/test_update.py` 的 sha256 因此與 TASK-032 的 `checked_version` 不同（TASK-032 的證據仍對應它當時的凍結版；本調整不改變任何產品程式碼）。
6. **`cloudflare/package.json` 是必要的**：`worker/src/*.js` 使用 ESM `import`，而沒有 `package.json` 時 Node 會把 `.js` 當 CommonJS。這個檔案只宣告 `"type": "module"` 與測試指令，**沒有任何依賴**（不引入 npm 套件）。

## 未執行或受阻

1. **真實 Cloudflare 後端未驗證**：沒有帳號、D1 或網域，`wrangler` 也未安裝；**沒有任何部署指令被執行**（`wrangler deploy`／`d1 execute` 皆未使用）。因此「Worker 真的跑在 Cloudflare 上」「真實 D1 的 SQL 相容性」「`secret put` 的實際行為」都屬未驗證，由 TASK-037 的 DELIVERY 明列。
2. **靜態 manifest 與 catalog 端點**（`GET /v1/latest`、`/catalog.json`）屬 TASK-034；本張的 router 只有兩個 POST 端點。
3. **後台操作與公開重新申請頁**（AC-062／AC-063）屬 TASK-035；本張只交付 `schema.sql` 與 activate／renew 需要的欄位，admin／reapply 的純函式與 `audit` 的寫入路徑尚未實作。
4. **沒有速率限制與濫用防護**：報告第 6.7 節未要求，本張也未實作（僅把 429 的語意留給客戶端重試）；真實上線前應評估。
5. **與客戶端的端到端整合未驗證**：Python 客戶端（`ediaad.license.activate`／`renew`）與本 Worker 之間只以「契約層級」對齊（金標 canonical JSON 與簽章、回應欄位、403 的 `status`）；把兩者接起來跑一次（例如本機以 `wrangler dev` 或假的 HTTP 伺服器）屬 TASK-036／TASK-037。
