# TASK-031 Code Review

- task_id：TASK-031
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-license-renew sha256:e37eec7cf2cd17238cb489a9e0d338c078cbed1482f59624ed60f3514131314a
- Task／Spec 版本：TASK-031 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 403 導流、撤銷標記的設計與互相掩蓋的兩個契約檢查）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `582e6e88aff091027e99d12341796947843b885e0eae420c8fda413362adf2b2`（85 個檔案）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `e37eec7cf2cd17238cb489a9e0d338c078cbed1482f59624ed60f3514131314a`（87 個檔案）；本張修改 `ediaad/license.py` `711aaf94…`、`ediaad/paths.py` `cf51cea1…`；新增 `tests/test_license_renew.py` `2fd123b9…`、`tests/test_license_features.py` `816f852f…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：上述四個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`ediaad/license.py` 的 TASK-028～030 既有 API 除 `check_lease` 新增 `revoked_path` 與撤銷檢查外未動；`tests/_ed25519_fixture.py` 沿用（未修改）；Worker 端 `handleRenew` 不在本張（TASK-033）
- 程式規範來源：`docs/workflow/SPEC.md` AC-056／AC-057、第 5 節租約格式（`features`）與「授權狀態轉移」（未啟用 → 已啟用 → 已過期 → 已撤銷）、外部依賴表（續期失敗不影響有效期內使用、逾期停止服務）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.4 節（三個觸發點、撤銷與導流、**後端必須拒絕已過期租約的 `renew`（回 403）**、重新申請頁對已撤銷指紋自動拒絕）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-056 | `ediaad/license.py`（`renew`／`lease_status`／撤銷標記／`check_lease` 的撤銷檢查）；`tests/test_license_renew.py` 10 個案例 | 符合 | A-1～A-5（advisory） |
| AC-057 | `ediaad/license.py`（`has_feature`／`features` 分級）；`tests/test_license_features.py` 9 個案例 | 符合 | A-3～A-5 |

逐條核對：

- **AC-056「續期成功後重算 30 天」**：`renew` 成功時伺服器回的租約必須是「同一把密鑰、同一台機器、長度恰為 30 天、簽章有效、到期時間比原本更晚」，五項全過才原子覆寫；測試斷言 `expires_at == now + 30 天`、`issued_at == now`、本地檔案等於回傳值且不留 `.tmp`。符合。
- **AC-056「每次呼叫都帶 `trigger`，只接受 `start`／`timer`／`manual`」**：`RENEW_TRIGGERS` 是常數（與 TASK-033 的 schema 對齊），三個值逐一驗證；未知 trigger → `ConfigError` 且**不發出請求**。符合。
- **AC-056「逾期未連線超過 30 天 → 停止服務並顯示重新申請訊息」**：`lease_status` 回 `expired` ＋ `reapply=True` ＋「請重新申請新密鑰（不會自動續期）」；到期邊界（等於到期時刻仍有效）有雙向斷言。停止服務的實際動作屬 TASK-025／TASK-036（本模組只回結構化結果）。符合（本張範圍內）。
- **AC-056「撤銷後下次驗證即停止，狀態為 `revoked`」**：`renew` 收到 403 且回應指出 `revoked` → 落地撤銷標記；`lease_status` 回 `revoked`；**同一把密鑰的 `check_lease` 也停止**（即使租約還沒到期）。符合。
- **AC-056「後端對已過期租約的 `renew` 必須回 403；客戶端收到 403 時不得以本地時間或舊租約續用」**：客戶端 403 → `ConfigError` 且**完全不動本地租約**；測試斷言「失敗後 `lease.json` 仍等於舊租約」＋「接著判為過期並附重新申請訊息」。**後端那一半（回 403）屬 TASK-033，尚未實作**（見 A-1）。符合（客戶端）。
- **AC-057「`features == ["start"]` 時更新功能停用但服務仍可用」**：`has_feature` 精確比對；測試斷言 `["start"]` 的租約 `check_lease` 仍 `ok=True` 且 `has_feature(..., "update") is False`（TASK-032 會據此傳 `enabled=False`）。符合。
- **AC-057「網頁可輸入新密鑰更換，成功後以新租約為準」**：以新密鑰 `activate` 覆寫租約檔後，`load_lease` 為新租約、`lease_status` 為 `active`、且**舊 `key_id` 的撤銷標記不影響新密鑰**（撤銷只認同一把 `key_id`）。網頁表單本身屬 TASK-025／AC-066。符合（本張範圍內）。

## 品質 Review

- **403 是導流的閘門，不是一般錯誤**：SPEC 明訂後端對已過期租約的 `renew` 回 403，因此客戶端的 403 處理決定了「導流能不能被繞過」。實作把 403 與其他 4xx 分開：403 → `ConfigError` ＋（若指出撤銷）落地標記，**且完全不動本地租約**；測試直接斷言「失敗後本地到期日不變」＋「接著 `lease_status` 判為過期／撤銷」。變異 `R05`／`R06` 證明這兩條分支都被測到。
- **429 與其他 4xx 分開**：429 是暫時狀態（客戶端沒有錯、可重試）→ `SourceError`（exit 1）；其餘 4xx → `ConfigError`（exit 2）。錯誤分層與 CLI 的 exit code 語意一致（變異 `R13`）。
- **撤銷標記的設計**：放在**租約旁邊**（`<lease_dir>/revoked.json`，原子、`0600`），只認同一把 `key_id`——這讓「更換密鑰」自然生效（舊標記不影響新密鑰），也讓測試天然隔離（不需要碰真實家目錄）。標記檔損毀／型別不對視為「沒有標記」：不該為了一個可重建的本地狀態讓服務起不來（與 TASK-030 對 `high_water` 的同一取捨）。
- **`check_lease` 的撤銷檢查是必要的擴充**：AC-056 要求「撤銷後下次驗證即停止」，因此啟動驗證必須看標記；TASK-030 的既有測試不受影響（沒有標記時行為完全相同），已用全套回歸確認。
- **互相掩蓋的兩條契約檢查（本張最有價值的發現）**：第一輪變異測試中「續期後的租約長度」與「到期時間必須延後」兩條檢查**各自被對方掩蓋**——原本的不合格清單裡，每一筆都同時違反兩條，因此拿掉任一條都還能被另一條接住，兩條檢查都形同未被測試。已把案例改成**各自只違反一項**（`now + 60 天` 只違反長度；`issued_at = 過期前 60 天、expires_at = 過期前 30 天` 只違反延長），兩條檢查就各自可觀測（`R09`／`R11` 隨後都被抓到）。這正是「多條驗證互相掩蓋」的典型陷阱。
- **回應契約共有五項**（密鑰、機器、長度、簽章、必須延後），全部落地前檢查；任何一項不符都不改寫本地租約（測試逐一斷言）。
- **`lease_status` 是結構化結果**：本模組不印訊息、不寫網頁，`state`／`message`／`expires_at`／`days_remaining`／`reapply` 交給授權頁（TASK-025）與 CLI（TASK-036）轉譯——符合「計算層不做呈現」的既有分層。
- **變異測試的強度**：21 個變異在凍結版全數被抓到。第一階段抓到 2 個互相掩蓋的存活者並以重新設計的案例擊殺；工具本身也以摘要區塊確認為正常結束（不是崩潰而沒有輸出）。
- **測試品質**：假 HTTP 可指定狀態碼／body／例外；時間注入；每個失敗路徑都同時斷言「錯誤型別」與「本地租約未被改寫」。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | **後端 403 斷言（跨 Task，重要）** | advisory（**需在 TASK-033 實作**） | 本張只驗證「客戶端收到 403 的行為」；後端 `handleRenew` 必須對**已過期**租約回 403（AC-060／TASK-033），否則使用者可以用舊租約一直續期，導流被繞過 | TASK-033 必須在 `handleRenew` 內檢查 `expires_at`：已過期 → 403（可附 `status: "expired"`）；已撤銷 → 403 且附 `status: "revoked"`；並以 `node --test` 固定這兩條 | 待辦（已記於 `STATE.md` 待決事項與本表） |
| A-2 | 觸發點的驅動 | advisory | 「每次開啟」與「每 24 小時」的觸發需要有人呼叫 `renew`；本張只交付函式與觸發來源列舉 | TASK-025 的服務排程（或 TASK-036 的 CLI）應在啟動時以 `trigger="start"`、每 24 小時以 `trigger="timer"` 呼叫，並在失敗時只記 warning（不影響有效期內使用） | 待辦（TASK-025／TASK-036） |
| A-3 | 功能分級的實際效果 | advisory | 本張只提供 `has_feature`；「缺少 `update` 時不發出更新請求」由 TASK-032 的 `check_update(enabled=...)` 消費 | TASK-032 應以 `has_feature(lease, "update")` 作為 `enabled` 的來源，並在 `enabled=False` 時**完全不發出請求** | 待辦（TASK-032） |
| A-4 | 撤銷標記的殘留 | advisory | 撤銷標記不會自動清除：若使用者換新密鑰，舊標記仍留在檔案裡（不影響新密鑰，但會累積） | 目前只有一個 `key_id` 的標記檔（換密鑰會覆寫）；若日後要記錄多把被撤銷的密鑰，需改成清單並定案保留策略——屬交付後事項 | 已記錄 |
| A-5 | 呈現層 | advisory | `LeaseStatus` 的呈現（授權頁 AC-066 的三態、剩餘天數、重新申請連結）尚未實作 | TASK-025 應以 `lease_status` 為唯一來源呈現，不要在前端自行計算剩餘天數或狀態 | 待辦（TASK-025） |
| A-6 | 流程記載 | advisory（非程式） | 兩個測試檔共用同一次 collection error（Cycle 1／Cycle 2 沒有各自獨立的 Red）；第一輪有 2 個變異因為「兩條檢查互相掩蓋」而存活 | 已如實記載：Cycle 2 的 Red 與 Cycle 1 同一次；互相掩蓋的案例重新設計成各自只違反一項，兩條檢查隨後都可觀測 | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-056／AC-057 逐條符合（後端 403 斷言列為 A-1）；品質 Review 無 blocking。
- 實作調整 1 處：429 從「4xx → `ConfigError`」改為 `SourceError`（暫時狀態、可重試，與 exit code 語意一致）。
- 依變異檢查重新設計測試 1 組（把「不合格續期回應」拆成各自只違反一項，解除兩條契約檢查的互相掩蓋）。
- 擴充 `check_lease`（新增 `revoked_path` 與撤銷檢查）並以全套回歸確認 TASK-030 的既有行為不變。
- 重審：重跑兩個測試檔（19 passed）與全套（**888 passed**）、兩個流程驗證器（exit 0），並在凍結版重跑變異矩陣（**21／21 偵測到**，工具以摘要區塊確認正常結束）；重讀 `renew`／`lease_status` 複查狀態碼分層、403 導流、撤銷標記與回應契約。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-056 的五項、AC-057 的三項宣稱逐條符合；後端 403 斷言列為待辦）
- 品質 Review：passed（無 blocking；A-1 需 TASK-033 實作，A-2／A-3／A-5 是後續 Task 的責任，A-4／A-6 已記錄）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-033 的後端 403）、A-2（TASK-025／036 驅動觸發點）、A-3（TASK-032 消費分級）、A-4（交付後事項）、A-5（TASK-025 呈現）、A-6（已記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：後端 403 尚未實作（A-1）；觸發點尚未被排程驅動（A-2）；授權頁與重新申請頁尚未呈現狀態；`LICENSE_PUBLIC_KEY` 仍是 fail-closed 佔位（TASK-033）；未對真實 Worker 做端到端續期
