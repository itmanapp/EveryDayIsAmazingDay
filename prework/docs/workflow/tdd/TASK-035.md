# TASK-035 測試紀錄

- task_id：TASK-035
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-d1-admin sha256:45876364bc01a9749bb4597dcbd6f98453525f31b72ac3b2710a0d5dc4ff78f5
- alternative_reason：**部分替代**——真實 D1 的 migration 執行結果與後台 UI 無法驗證（無帳號／無部署授權，且 `wrangler d1 execute` 明令不執行）；本張以「**真的 SQL**（假 D1 建立在 `node:sqlite` 上，`schema.sql` 與每一句查詢都真的被 SQLite 執行）」＋注入的時鐘與 `secretFactory` 驗證；未驗證項由 TASK-037 的 DELIVERY 明列。
- Task／Spec 版本：TASK-035 / SPEC-001 v0.4
- 測試邊界：（1）admin 純函式（`generateKeys`／`listKeys`／`revokeKey`／`restoreKey`／`extendKey`／`stats`／`auditLog`）：回傳值＋假 D1 內**實際落表的列**；（2）reapply（`handleReapply`／`isBlacklisted`／`findExpiredKey`／`reapplyPage`）：合成 `Request` → 回應 `status` 與 JSON；（3）重新申請成功後**真的走一次 TASK-033 的 `handleActivate`**，證明新密鑰可用；（4）路由：`GET`／`POST /reapply`。全程離線、不需要 `wrangler`、不需要 npm install。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-034 與 TASK-025 的交付物（`admin.js`／`reapply.js` 尚不存在），Python 全套 **971 passed**、Node **54 passed**（本張完成後為 Python **971 passed**、Node **82 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `2b1d1b16deec9d682570dd12603643f048129e431b39d8bf2bb78d1de0678a65`（115 個檔案，即 TASK-034 的 `checked_version`）。
- TDD 不適用的理由與替代驗證（若有）：見「未執行或受阻」第 1 點（真實 D1 migration 與後台 UI）。

工作目錄一律為 `ocaievo/cloudflare/`，命令一律為 `node --test`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `cloudflare/worker/src/admin.js` | `c1c1c2f9` | 新增：`generateKeys`／`createKeys`（共用實作）／`listKeys`／`revokeKey`／`restoreKey`／`extendKey`／`stats`／`auditLog`、`maskSecret`／`parseKeyFeatures`；常數 `ADMIN_FEATURES`／`MAX_BATCH`／`MAX_EXTEND_DAYS`／`DEFAULT_LIST_LIMIT`／`MAX_LIST_LIMIT`／`KEY_STATUSES` |
| `cloudflare/worker/src/reapply.js` | `59d4bf7d` | 新增：`handleReapply`（黑名單 403／未過期 409／未知 404／已撤銷 403／過期才發新密鑰）、`isBlacklisted`、`findExpiredKey`、`reapplyPage()`、`handleReapplyPage`、`REAPPLY_PATH` |
| `cloudflare/worker/src/db.js` | `0cb8c051` | 修改：新增 20 個 D1 轉接函式（序號、插入、清單查詢、狀態／到期更新、黑名單、稽核、七種統計、指紋查詢），全部使用綁定參數；移除一個未被使用的中間版本函式 |
| `cloudflare/worker/src/router.js` | `e5891be0` | 修改：路由表加入 `GET /reapply` 與 `POST /reapply`；405 的訊息改為列出該路徑允許的方法 |
| `cloudflare/test/admin.test.mjs` | `4d6b33a0` | 新增：17 個測試（批次、序號、參數驗證、遮蔽、篩選、撤銷／恢復／延長、統計、稽核） |
| `cloudflare/test/reapply.test.mjs` | `418bb86c` | 新增：11 個測試（成功＋真的啟用一次、黑名單、已撤銷、未過期、未知、`findExpiredKey`、請求驗證、頁面、路由） |
| `cloudflare/test/router.test.mjs` | `901aefe8` | 修改（TASK-033 的測試）：路由表由兩個端點改為四個（TASK-035 依 AC-063 新增重新申請頁） |

## Cycle 1：批次產生密鑰與序號（2 個測試）

- 測試：`generateKeys(db, 3, ["start","update"], "作者")` → 三列 `EDIAAD-2026-0001..0003`、狀態 `issued`、`features` 如實、`expires_at` 為 `null`、密鑰符合 32 個十六進位字元、`created_at` 等於注入的時間；**恰一筆稽核**（`actor`／`action="generate_keys"`／`target` 含第一把 key_id）；序號接續既有密鑰，且**刪除中間的密鑰後不重用**（0002 刪除 → 下一批是 0004）。
- 實作：`admin.createKeys`（`generateKeys` 與重新申請共用）、`db.latestKeyId`／`insertKey`。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `node --test test/admin.test.mjs test/reapply.test.mjs` | 1 | `ERR_MODULE_NOT_FOUND`（`admin.js`／`reapply.js` 不存在） | 尚未有實作／2026-09-25 |
| Green | `node --test test/admin.test.mjs` | 0 | `ℹ pass 17 / fail 0` | snap-2026-09-24-ocaievo-d1-admin／2026-09-25 |

- **序號用「現有最大值 + 1」而不是「列數 + 1」**：列數在刪除後會倒退，造成 key_id 重用（那會讓舊租約指向新密鑰）。`latestKeyId` 以 `ORDER BY key_id DESC LIMIT 1` 取最大值，並由 `keys.key_id` 的 PRIMARY KEY 當最後一道防線（變異 `A20`／`D02` 都被抓到）。
- **稽核的動作名稱由呼叫端決定**：`createKeys(..., action)` 讓後台批次（`generate_keys`）與公開重新申請（`reapply`）共用同一段產生邏輯，只差稽核字串——避免兩份「產生密鑰」的實作分岔。

## Cycle 2：參數驗證與秘密的產生（3 個測試）

- 測試：九種不合法的 `(count, features)`（`0`／`-1`／字串／超過上限／小數／空陣列／空字串元素／非陣列／重複元素）與空 `actor` 一律拒絕，且 `keys` 與 `audit` **都沒有新列**；預設密鑰以 `crypto.getRandomValues` 產生，20 把不重複且都是 32 個十六進位字元。
- 實作：`requireCount`／`requireFeatures`／`requireActor`／`defaultSecret`。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/admin.test.mjs` | 0 | `17 passed` |

- **先驗證、後寫入**：所有驗證都在任何 `INSERT` 之前，因此「參數錯」不會留下半批密鑰或一筆誤導的稽核（稽核只記真的發生過的事）。

## Cycle 3：清單、遮蔽與篩選（2 個測試）

- 測試：`listKeys` 預設**遮蔽**密鑰（`abcd…wxyz`、不得含完整值），`includeSecret: true` 才回完整值；預設由新到舊、附每把密鑰的 `starts`／`renewals`；依 `status` 篩選、依 `key_id` 或 `secret` 子字串搜尋；不合法 `status`／`limit`（`0`／`201`／小數）拒絕。
- 實作：`listKeys`、`db.findKeys`、`maskSecret`。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/admin.test.mjs` | 0 | `17 passed` |

- **遮蔽是預設**：清單是給人看的（也可能被截圖），完整密鑰只在「剛產生」與「明確要求」時出現。搜尋仍然可以比對 secret（後台需要「用密鑰找 key_id」這個動作），但輸出維持遮蔽。

## Cycle 4：撤銷、恢復與延長（6 個測試）

- 測試：撤銷 → `status='revoked'`，並把**兩條綁定線索**（`keys.machine` 與 `devices` 的指紋，測試刻意用兩個不同指紋）都放進 `blacklist`，留一筆 `revoke_key` 稽核；再撤銷一次不會多出黑名單列但仍然留稽核；沒有綁定機器時不亂加黑名單；對不存在的 key_id 的三種操作都回 `unknown_key` 且不寫稽核；恢復 → 回到 `active`（啟用過）／`issued`（未啟用過），並移除同一把密鑰的黑名單列；延長 → 三種情境（沒有到期日、未到期、已過期）都**不會縮短**，五種不合法 `days` 與空 `actor` 拒絕。
- 實作：`revokeKey`／`restoreKey`／`extendKey`、`db.addToBlacklist`／`removeBlacklistForKey`／`updateKeyStatus`／`updateKeyExpiry`。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/admin.test.mjs` | 0 | `17 passed` |

- **撤銷與恢復互為反操作**：撤銷把指紋放進黑名單（TASK-033 的 `renew` 因此會 403 revoked），恢復把它移除（同一台機器可以重新申請）。這是 AC-063「黑名單自動拒絕」得以成立的前提。
- **延長不縮短**：已過期的密鑰若從「過去的到期日」往後加，加完可能還在過去（等於沒延長），因此基準取「現在」與「原到期日」的較晚者。

## Cycle 5：統計與稽核（3 個測試）

- 測試：3 筆 `start` ＋ 2 筆 `timer`（同一把）＋ 1 筆 `start`（另一把，且超過 30 天）→ 全域 `starts == 4`（**timer 不算**）、`renewals == 6`、`active_last_30_days == 1`；逐把密鑰的 `starts` 分別為 3 與 1（**不同 key_id 不互相加總**）；`keys` 的五個計數把「已過期」與「已撤銷」分開；`auditLog` 自己也會驗證 `actor`／`action`，並如實寫入 `created_at` 與 `details`。
- 實作：`stats`、`auditLog`、`db.countStarts`／`countStartsForKey`／`countRenewalsSince`／`countKeysByStatus`／`countExpiredKeys`／`countDevices`／`countRenewalsTotal`。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/admin.test.mjs` | 0 | `17 passed` |

- **`trigger='start'` 是唯一被算成「開啟次數」的觸發**：`timer` 是 24 小時定時回報，算進去會讓「使用者開過幾次軟體」嚴重高估（報告第 6.7 節的設計重點）。變異 `D03`（拿掉 `WHERE trigger='start'`）被 `starts` 的斷言抓到。

## Cycle 6：公開重新申請（8 個測試）

- 測試：過期者申請 → 200、新 `EDIAAD-2026-0002`、密鑰格式正確、狀態 `issued`、稽核 `action="reapply"`（`actor` 含指紋），而且**立刻用 TASK-033 的 `handleActivate` 啟用成功**；黑名單指紋 → 403＋訊息含「黑名單」、**不新增密鑰、不寫稽核**；已撤銷但沒有黑名單紀錄（資料被手動改過）→ 403＋「撤銷」、不新增；授權仍在有效期內 → 409 且訊息附到期日、不新增；完全沒有紀錄 → 404、不新增；`findExpiredKey` 只認已過期者、取最近到期的一把、未過期時回 `null`；六種不合法請求（GET／壞 JSON／陣列主體／缺指紋／非十六進位／大寫十六進位）各自回對應狀態、可讀 JSON、不含堆疊；`machine` 可當 `fingerprint` 的別名；`features` 欄位壞掉時用預設功能（不讓重新申請變 500）。
- 實作：`reapply.js`、`db.findKeyForFingerprint`／`findExpiredKeyForFingerprint`。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/reapply.test.mjs` | 0 | `ℹ pass 11 / fail 0` |

- **順序就是安全性**：先查黑名單 → 再確認真的有紀錄 → 再確認真的過期 → 最後才產生新密鑰。每一條拒絕路徑都在 `createKeys` 之前返回，因此**不可能**對黑名單或未過期的指紋發出任何密鑰（測試對每一種拒絕都斷言 `keys` 沒有新增、`audit` 沒有新列）。
- **「新密鑰可用」不是宣稱**：測試直接把新密鑰餵給 `handleActivate`，走完整的簽章與落地流程。
- **新密鑰沒有任何授權**：重新申請只換密鑰，租約仍由啟用流程簽發（重新申請頁不需要簽章私鑰，也不需要 D1 以外的資源）。

## Cycle 7：重新申請頁與路由（2 個測試）

- 測試：`GET /reapply` → 200 HTML（含 `<form>`、`name="fingerprint"`、`/reapply`、沒有外部資源）；經由 `handleRequest` 的 `GET`／`POST /reapply` 都通，`PUT /reapply` → 405；路由表恰為四個端點。
- 實作：`reapplyPage()`／`handleReapplyPage`、`router.js` 的兩個新路由。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/router.test.mjs test/reapply.test.mjs` | 0 | `4 passed`／`11 passed` |

- **路由表的測試被抓到變更是預期行為**：TASK-033 的 `router.test.mjs` 斷言「恰兩個端點」的用意就是「端點變動必須被看見」；本張依 AC-063 新增兩個，因此一併更新該斷言（跨 Task 的測試變更，見 Review 的 A-7）。

## Red → Green 的實際順序

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Red | `node --test test/admin.test.mjs test/reapply.test.mjs` | 1 | 兩個測試檔 `ERR_MODULE_NOT_FOUND`（實作尚不存在） |
| Green 1 | 同上 | 1 | `25 passed / 3 failed`（測試自己的三處錯誤，見「如實記載」第 1～3 點） |
| Green 2 | `node --test` | 1 | `78 passed / 1 failed`（撤銷測試的幂等斷言要改成兩個指紋） |
| Green 3 | `node --test` | 0 | `ℹ tests 79 / pass 79 / fail 0` |
| Green 4（凍結版） | `node --test` | 0 | `ℹ tests 82 / pass 82 / fail 0`（補強三個存活者的斷言後） |

## 變異測試（兩階段：先殺存活者，再跑凍結版）

- 工具：`/tmp/mutate_task035.py`（整行／整段替換、`count(frm) == 1` 才套用、每輪逾時 180 秒、跑完立即還原並比對 sha256、`flock` 鎖單一行程、`SIGTERM`／`SIGINT`／`atexit` 會還原；Node 的收集失敗也算「抓到」）。
- 矩陣：**40 個變異**（`admin.js` 21、`db.js` 7、`reapply.js` 10、`router.js` 2），涵蓋批次上限與型別、features 的重複與空值、遮蔽、清單篩選與 limit 上限、撤銷的兩條指紋線索與狀態／稽核、恢復的黑名單移除與狀態、延長的三種基準與上限、統計的四個數字（starts／renewals／active_30d／expired）、稽核的參數驗證、序號來源與 secretFactory 注入、七句 SQL（搜尋、序號排序、start 條件、過期比較、黑名單 upsert、黑名單刪除、features 序列化），以及重新申請的四條拒絕路徑、回應欄位、頁面與路由。
- **第一階段抓到 3 個真實存活者，全部補強測試後擊殺**：
  1. `A07`（撤銷時不看 `keys.machine`）——存活是因為測試裡的 `keys.machine` 與裝置列**是同一個指紋**，裝置迴圈就足以放進黑名單。已補「只有機器欄位、沒有裝置列」的案例。
  2. `R02`（不檢查 `status='revoked'`）——存活是因為撤銷過的密鑰同時也在黑名單裡，黑名單檢查先攔下來。已補「已撤銷但沒有黑名單紀錄（資料被手動改過）」的案例。
  3. `R07`（沒有預設 features）——存活是因為種子資料的 `features` 都是合法 JSON，`?? DEFAULT_REAPPLY_FEATURES` 從沒被走到。已補「features 欄位壞掉時用預設功能」的案例（同時證明不會變成 500）。
- **最終凍結版結果：40／40 全數偵測到（0 存活、0 無效）**；逐輪輸出形如 `ℹ pass 15 / fail 1`。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `node --test`（工作目錄 `ocaievo/cloudflare/`） | 0 | `ℹ tests 82 / pass 82 / fail 0`（80 個測試案例：admin 17／reapply 11／router 4／其餘為 TASK-033～034 的 48 個） |
| `.venv/bin/python -m pytest -q`（工作目錄 `ocaievo/`） | 0 | `971 passed, 2 warnings in 153.03s` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |
| 凍結版檔案樹 | — | sha256 `45876364bc01a9749bb4597dcbd6f98453525f31b72ac3b2710a0d5dc4ff78f5`（119 個檔案） |

## 如實記載的實作／測試錯誤

1. **測試的假密鑰每次呼叫都重新編號**：`makeKeys` 裡的序號計數器在函式內，第二次呼叫又產生同一組密鑰 → `keys.secret` 的 UNIQUE 約束當場擋下（這是**產品正確、測試寫錯**）。已改為把 `key_id` 傳進 `secretFactory`（`factory(index, keyId)`），密鑰與 key_id 一一對應且不依賴測試順序。
2. **測試自己的算術錯誤**：統計測試插入了 6 筆 renewals 卻斷言 5 筆（3 start ＋ 2 timer ＋ 另一把的 1 start）。已更正為 6，並把「同一把的 5 筆」另外斷言。
3. **`seedKey` 對同一個指紋插入第二筆裝置**：`devices.fingerprint` 是主鍵，第二把密鑰（重新申請後的情境）會撞鍵。已改為 `ON CONFLICT(fingerprint) DO UPDATE`（真實情境也是這樣：裝置列指向最新的密鑰）。
4. **撤銷測試的幂等斷言少算了指紋**：加入第二個裝置指紋後，黑名單應有 2 列而不是 1 列。已更正。
5. **一個未被使用的中間版本函式**：`db.getKeyByMachine` 在改用 `findKeyForFingerprint`（同時看 `keys.machine` 與 `devices`）之後就沒有呼叫端，已移除（`getDevice`／`countRenewals` 雖然目前沒有呼叫端，但屬 TASK-033 明列的 D1 介面，保留）。

## 未執行或受阻

1. **真實 D1 未驗證**：沒有 Cloudflare 帳號／`database_id`，**沒有任何 `wrangler d1 execute` 被執行**；真實 migration（`schema.sql` 在 D1 上的執行結果）、D1 對這些查詢的相容性（`ON CONFLICT`、`LIKE`、`COUNT(DISTINCT)`、字串比較）與後台 UI 都未驗證，由 TASK-037 的 DELIVERY 明列。
2. **後台沒有 HTTP 端點**：本張只交付純函式（`admin.js`），沒有 `/admin/*` 路由，也沒有登入／權限模型（`actor` 由呼叫端注入，測試以字串模擬）。真實後台需要另外的認證機制（Cloudflare Access 或後台頁面），屬部署階段。
3. **重新申請頁沒有防濫用**：任何人都可以用任意指紋呼叫 `POST /reapply`（只會對「已過期且未在黑名單」的指紋發新密鑰，但仍可被列舉嘗試）。上線前應加速率限制（TASK-033 的 A-6 同一項）。
4. **重新申請的新密鑰不會通知使用者**：頁面直接顯示密鑰（設計如此），沒有 Email 或外部通知（本張明訂不做）。
5. **統計的「活躍使用者」是近似值**：`active_last_30_days` 以 renewals 的 distinct key_id 計算，且依賴伺服器時間（注入的 `now`）；真實的時區與時鐘偏移未驗證。
