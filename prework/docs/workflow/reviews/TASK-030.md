# TASK-030 Code Review

- task_id：TASK-030
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-license-activate sha256:582e6e88aff091027e99d12341796947843b885e0eae420c8fda413362adf2b2
- Task／Spec 版本：TASK-030 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 `verify_lease` 契約衝突的處置、零網路斷言與水位防線的檢討）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `a6503eb5e87fa310bb305ed3a9f96d10deedeb7d320ad8a8a58020bf765178f6`（82 個檔案）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `582e6e88aff091027e99d12341796947843b885e0eae420c8fda413362adf2b2`（85 個檔案）；本張修改 `ediaad/license.py` `adfdfd94…`、`ediaad/paths.py` `f6f6ad3b…`；新增 `tests/test_license_activate.py` `bce0eb56…`、`tests/test_license_startup.py` `89d2408d…`、`tests/_ed25519_fixture.py` `7452398f…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：上述五個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`ediaad/license.py` 的 TASK-028／029 既有 API（`Lease`／`machine_fingerprint`／`verify_lease`／`ed25519_verify`／`signing_payload`）**未修改**；`ediaad/errors.py` 沿用既有 `ConfigError`／`SourceError`
- 程式規範來源：`docs/workflow/SPEC.md` AC-052／AC-053／AC-058、第 5 節租約 JSON 格式與資料生命週期（`$EDIAAD_HOME/lease.json`、`keys.json` 0600）、授權狀態、錯誤分層、第 5 節原則 2（外部效果可注入）、第 7 節測試策略；`docs/architecture/ENGINEERING-REPORT.md` 第 6.4 節（三個觸發點、時鐘篡改防護、租約格式）；`docs/workflow/adr/ADR-002.md`；`docs/workflow/PROJECT.md`（`EDIAAD_HOME`／`EDIAAD_LICENSE_URL`）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-052 | `ediaad/license.py`（`activate`／`save_lease`／`load_lease`）；`tests/test_license_activate.py` 15 個案例 | 符合 | A-1～A-6（advisory） |
| AC-053 | `ediaad/license.py`（`check_lease`）；`tests/test_license_startup.py` 的離線啟動案例 | 符合 | A-2、A-4～A-6 |
| AC-058 | `ediaad/license.py`（兩層時鐘判定與 `_refresh_online`／`_advance_high_water`）；`tests/test_license_startup.py` 的時鐘案例 | 符合 | A-3～A-6 |

逐條核對：

- **AC-052「送出密鑰與機器指紋後取得簽章租約（30 天）並落地」**：`activate` 恰好發出一次 `POST <url>/v1/activate`，payload 為 `{"key", "machine"}`；回應轉成 `Lease` 後檢查「屬於這台機器、長度恰為 30 天、簽章以伺服器公鑰驗證通過」，再原子落地；測試斷言回傳值與落地內容一致、`expires_at − issued_at == 30 天`、且以公鑰對 `signing_payload` 驗章為真。符合。
- **AC-052「租約欄位符合第 5 節格式」**：`Lease`（TASK-028）本身就是該格式且嚴格還原；本張只讀寫它，沒有新增欄位。符合。
- **AC-053「離線完成驗章、指紋比對、到期與時鐘檢查後啟動」**：`check_lease` 的順序是讀租約 → 指紋 → 簽章（`ed25519_verify`）→ 到期 → 兩層時鐘；每一種失敗都有專屬案例與可讀 `reason`。符合。
- **AC-053「整個啟動流程不發出任何網路請求」**：以「任何呼叫都丟 `AssertionError`」的假客戶端跑同一條路徑，斷言 `call_count == 0`；再以「任何呼叫都拋 `SourceError`」的客戶端證明離線可用。符合。
- **AC-058「兩層時鐘防護都生效、都不得以本地時間延長授權」**：第一層比對**簽章內**的 `issued_at`（`now < issued_at − 900` → `force_online`），第二層比對本地 `high_water`（`now < high_water − 900` → `force_online`）；兩者的邊界（恰好等於容忍值）都有測試；`force_online` 時若沒有可用的線上驗證 → `ok=False` 且訊息明說「不以本地時間延長授權」；線上驗證回來的租約仍要驗指紋與到期。符合。
- **本張不做的部分**：續期／到期停止導流／撤銷／功能分級（TASK-031）、曲線運算（TASK-029）、`Lease` 模型與指紋演算法（TASK-028）、Worker 端 `handleActivate`（TASK-033）、CLI（TASK-036）、監控與 Web 啟動（TASK-020）都沒有實作。符合。

## 品質 Review

- **契約衝突的處置（本張最重要的判斷）**：TASK-030.md 提議把 `verify_lease` 改成 `(lease, *, fingerprint, public_key, now, high_water, tolerance_seconds) -> LeaseVerdict`，但 TASK-028 已經交付並 Review 過 `verify_lease(lease, fingerprint=None, verify_sig=None) -> bool`（16 個測試）。同一個名字換成不同簽章會破壞已完成的公開契約，而且會讓「指紋＋簽章閘門」與「完整啟動判定」兩種語意混在一個名字裡。本張改以**新函式 `check_lease`** 實作完整判定，並**重用** `verify_lease` 當閘門（`verify_sig` 綁到 `ed25519_verify` ＋ `signing_payload` ＋ `sig_bytes`）——這正是 TASK-030.md 自己提醒的「避免同一結構被兩張 Task 重複定義而分岔」的具體落實。已列為追認項 A-1。
- **簽章涵蓋範圍只有一份**：`activate` 與 `check_lease` 都呼叫 TASK-028 的 `signing_payload`，沒有任何地方自行序列化被簽內容（兌現 TASK-028 的 A-1）。
- **零網路是斷言，不是承諾**：AC-053 的核心是「啟動不碰網路」，因此測試用「一呼叫就炸」的客戶端跑同一條路徑；`_refresh_online` 只在 `force_online` 時才被呼叫，且**沒有任何背景或隱含的網路呼叫**。
- **時鐘防護的兩個細節**：（a）邊界以「恰好等於容忍值不觸發」定義並雙向固定；（b）成功啟動只把水位**往前**推進——否則反覆小幅調鐘就能把第二層磨掉（變異 `A15` 的偵測點）。第二層仍是可被刪檔繞過的（報告已載明），因此實作把它當成「可選的加強」而不是「必須成功的寫入」。
- **錯誤分層與 exit code 語意一致**：4xx → `ConfigError`（exit 2）、5xx／連線失敗／落地失敗 → `SourceError`（exit 1）；**任何失敗都不落地租約**（測試逐一驗證 `lease.json` 不存在）。
- **原子落地與權限**：暫存檔 → `os.replace`，並在替換前 `chmod 0600`；唯讀目錄時既有租約不損毀、不留 `.tmp`。租約與水位都是本機憑證／狀態，只給擁有者讀寫。
- **時間全部注入**：`activate`／`check_lease` 不呼叫 `datetime.now()`（唯一例外是預設值 `_default_now` 本身），符合 SPEC 第 5 節原則 2；naive 時間一律視為 UTC（與 TASK-024 的同一慣例）。
- **測試夾具的可信度**：`_ed25519_fixture` 在 import 時斷言「由 RFC TEST 1 secret key 推導的公鑰等於向量值」，且只用**公開的**測試 secret key；夾具不進 `ediaad/`、不引入 `cryptography`（`.venv` 內仍是 `None`）。簽章只在測試中出現，正式環境的簽章在 Worker（TASK-033）。
- **變異測試的強度**：25 個變異在凍結版全數被抓到。第一階段抓到 1 個存活者（`sig_bytes` 的長度檢查被上層的長度檢查掩蓋）並以「錯誤訊息必須指出格式」的可觀測契約擊殺；另 4 處在跑之前就先補強（錯誤長度的合法十六進位簽章、水位不得往回寫、線上租約已過期、預設產物路徑）。
- **測試品質**：假 HTTP 可計數、可指定狀態碼與例外；時間以固定 `now` 注入；產物以 `tmp_path` 觀察；每個失敗路徑都同時斷言「錯誤型別」與「沒有落地」。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 與 Task 文件的 API 差異 | advisory（**需追認**） | TASK-030.md 指定 `verify_lease` 的新簽章；本張以新函式 `check_lease` 實作完整啟動判定，`verify_lease` 維持 TASK-028 的指紋＋簽章閘門 | 建議 SPEC 第 5 節的 `ediaad/license.py` API 欄位補上 `activate`／`check_lease`／`LeaseVerdict`／`save_lease`／`load_lease`／`load_high_water`／`save_high_water`／`sig_bytes`，並在 TASK-030.md 註明這個處置 | 已決定並記錄（TDD「Cycle 2」與本表） |
| A-2 | `LICENSE_PUBLIC_KEY` | advisory（**需在 TASK-033 完成**） | 仍是全零佔位（fail closed）：目前**任何**真實租約都驗不過 | TASK-033 產生 Worker 金鑰後替換，並新增「用真公鑰驗一個真租約」的整合測試 | 待辦（TASK-033；fail-closed 行為已有測試） |
| A-3 | 週期性線上驗證 | advisory | 本張只在**時鐘異常**時強制線上（AC-058）；報告第 6.4 節的第三個觸發點「每次開啟／每 24 小時線上驗證」屬續期（AC-056） | TASK-031 應在續期流程中實作該觸發點，並重用 `_refresh_online` 的驗證邏輯（不要另寫一套租約檢查） | 待辦（TASK-031） |
| A-4 | `high_water` 的已知限制 | advisory | 水位可被刪檔繞過（報告第 6.4 節已載明）；本張刻意讓「損毀」等同「沒有水位」、寫入失敗不阻止啟動 | 這是設計取捨：真防線是簽章內的 `issued_at`；若日後要更強，可把水位寫進 `Store`（SQLite）或與租約同一檔案並簽章保護——但那需要 SPEC 變更 | 已記錄（TDD 與程式註解） |
| A-5 | 線上刷新的範圍 | advisory | `_refresh_online` 只做「取得新租約 → 驗章／指紋／到期 → 落地」；不處理撤銷（伺服器回 403 時一律不放行，但沒有把租約標記為撤銷） | TASK-031 的撤銷處理應在此之上加狀態轉移（已撤銷 → 停止並導流） | 待辦（TASK-031） |
| A-6 | 流程記載 | advisory（非程式） | 兩個測試檔在同一次 collection error 下一起紅（Cycle 1／Cycle 2 共用一次 Red），因此 Cycle 2 沒有獨立的 Red；`sig_bytes` 的長度檢查第一輪被上層掩蓋而存活 | 已如實記載：Cycle 2 的 Red 與 Cycle 1 同一次（實作前兩個測試檔都無法收集）；存活者以「錯誤訊息可讀性」的可觀測契約擊殺，並在跑之前補強另外 4 處 | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-052／AC-053／AC-058 逐條符合；品質 Review 無 blocking。
- 契約衝突處置：以 `check_lease` 取代 TASK-030.md 提議的 `verify_lease` 新簽章（保留 TASK-028 的公開契約），並重用 `verify_lease` 作為指紋＋簽章閘門。
- 依變異檢查補強測試 5 處（錯誤長度的合法十六進位簽章、水位不得往回寫、線上租約已過期、預設產物路徑、簽章格式錯誤訊息）。
- 重審：重跑兩個測試檔（32 passed）與全套（**868 passed**）、兩個流程驗證器（exit 0），並在凍結版重跑變異矩陣（**25／25 偵測到**）；重讀 `activate`／`check_lease` 複查狀態碼分層、租約契約檢查、零網路路徑、兩層時鐘與水位推進。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-052 的兩項、AC-053 的兩項、AC-058 的一項宣稱逐條符合）
- 品質 Review：passed（無 blocking；A-1 需追認，A-2／A-3／A-5 是後續 Task 的責任，A-4／A-6 已記錄）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（Spec 與 Task 文件的 API 欄位）、A-2（TASK-033 替換公鑰）、A-3（TASK-031 的週期性線上驗證）、A-4（設計取捨，需 SPEC 變更才可能更強）、A-5（TASK-031 的撤銷狀態轉移）、A-6（已記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：尚未對真實 Worker 做端到端啟用（TASK-033）；`LICENSE_PUBLIC_KEY` 是佔位值；到期後的停止與導流、續期、撤銷、功能分級未實作（TASK-031）；`high_water` 可被刪檔繞過（已知限制）
