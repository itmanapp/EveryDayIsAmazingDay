# TASK-029 Code Review

- task_id：TASK-029
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-ed25519 sha256:a6503eb5e87fa310bb305ed3a9f96d10deedeb7d320ad8a8a58020bf765178f6
- Task／Spec 版本：TASK-029 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含向量的事前交叉核對、兩個偽造負例與工具缺陷的處理）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `0c378a8ba64fa1a99b86a10b6489a1ce19e50accfaf157dcb530f21b8e8a9e38`（81 個檔案）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `a6503eb5e87fa310bb305ed3a9f96d10deedeb7d320ad8a8a58020bf765178f6`（82 個檔案）；本張修改 `ediaad/license.py` `4ba247f6…`、新增 `tests/test_license_ed25519.py` `1c8343ae…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：上述兩個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`ediaad/errors.py`（沿用既有 `ConfigError`，未修改）；系統的 `cryptography` 只用於**編寫測試時**交叉核對向量，不在 `.venv`、不在 requirements、不在程式碼中 import
- 程式規範來源：`docs/workflow/SPEC.md` AC-054、第 5 節原則 1（計算不碰 I/O）與模組表 `ediaad/license.py` 的 `ed25519_verify`、第 6 節安全；`docs/workflow/adr/ADR-002.md`（純 Python Ed25519、不引入 `cryptography`、不得自行發明曲線運算、需有向量測試與 Review）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.4 節；`docs/workflow/PROJECT.md`（系統 `cryptography` 41.0.7 **不使用**）；RFC 8032 第 5.1／7.1 節；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-054 | `ediaad/license.py`（`ed25519_verify` 與內部群運算）；`tests/test_license_ed25519.py` 22 個案例 | 符合 | A-1～A-5（advisory） |

逐條核對：

- **AC-054「RFC 8032 官方測試向量全部通過」**：第 7.1 節的五組（TEST 1、2、3、1024、SHA(abc)）全部回 `True`（參數化），且**每一組都先由系統的獨立實作交叉核對過**（見 TDD 的「證據的來源」）。符合。
- **AC-054「對被改動的訊息／簽章／公鑰回 `False` 且不拋出例外」**：三種篡改各翻一個位元、訊息尾端多一個 byte、40 組隨機輸入與 20 組雜訊簽章都只回 `False` 或 `True`，沒有例外；另有交叉負例（同一公鑰配另一組向量的訊息與簽章）。符合。
- **AC-054「實作為純 Python」**：只用 `hashlib` 與任意精度整數；子程序 import 本模組不拉進 `socket`／`ssl`／`http`／`cryptography`／`requests`；`find_spec("cryptography") is None`。符合。
- **AC-054「`requirements.txt`／`requirements-dev.txt` 不含 `cryptography`」**：以 `grep -c` 直接證明（兩檔皆 0）。符合。
- **AC-054「模組可被 import 而不觸碰檔案、網路或時鐘」**：模組層只有常數與函式定義（`_D`／`_I`／`_BASE` 是純算術）；子程序檢查沒有任何 I/O 模組被拉進。符合。
- **本張不做的部分**：沒有簽章與私鑰、沒有 `Lease` 整合、沒有 CLI、沒有第三方依賴；`LICENSE_PUBLIC_KEY` 以 fail-closed 佔位值提供（TASK-033 才填入真值），且測試證明用它在任何輸入上都驗不過。符合。

## 品質 Review

- **官方向量先被外部實作核對，才寫進測試**：這是本張最重要的一道防線。向量是常數，抄錯一個字元就會變成「測試與實作一起錯」——而且錯誤會被包裝成「官方測試通過」。實際發生：`TEST SHA(abc)` 的簽章第一版抄錯，由交叉核對發現；因為 Ed25519 簽章是決定性的，用同一把 secret key 重算即得正確值。**系統的 `cryptography` 只在編寫測試時使用**（`.venv` 內仍是 `None`、requirements 不含它），因此沒有違反 ADR-002。
- **嚴格性是安全邊界，不是裝飾**：`S >= L`（可延展簽章）、非正規點編碼、小階點／identity 三條規則各有具體測試，且都以**真實偽造**為負例：`A = identity` ＋ `R = identity` ＋ `S = 0` 會滿足群等式；更強的是 `A = identity` 時 `[k]A` 恆為 identity，攻擊者取 `R = [S]B`（`S = 1`、`R` = 基底點）就對**任意訊息**滿足群等式。少了小階點檢查，任何人都能偽造簽章——這條測試是變異 `E14`／`E20` 的偵測點。
- **點相等必須比兩個座標**：只比 X 會把 `P` 與「同 X、Y 相反」的點視為相等（變異 `E13` 一開始存活）。這在群等式檢查上是實質弱化，已補「identity vs `(0, -1)`」的比較測試。這是本張最有價值的一個發現。
- **公開 API 測不到的安全規則，就在解碼層測**：`y >= p` 與「`x = 0` 帶 sign bit」需要「`y < 19` 的真實金鑰」才能從公開 API 構造，因此新增三個內部規則測試（解碼正規性、點相等、小階點判定）並在測試 docstring 說明**為什麼**要測內部函式。對安全敏感的密碼學原語而言，這比留下測不到的規則更誠實。
- **不簽章、不持私鑰**：驗章與簽章分離（簽章在 Worker 以 WebCrypto 執行），客戶端只有內嵌公鑰；`LICENSE_PUBLIC_KEY` 目前是全零佔位並**fail closed**（全零解出來是小階點 → 一律拒絕），因此「還沒產生金鑰的組建」不可能接受任何租約。
- **效能**：一次驗章（含 1023 bytes 訊息）實測 **3.8 ms**，遠低於報告第 6.4 節的關注點與測試的 1 秒門檻；純 Python 的 double-and-add 足夠（驗章只需兩次純量乘法）。
- **變異測試的強度**：24 個變異中 22 個被抓到，2 個等價（`E17` 未化簡的 `_BASE_Y` 被模運算吸收；`E21` 在無共因子等式下不可觀測，**刻意保留**作為縱深防禦）。第一階段另有 6 個真實存活者，全部以補強測試擊殺（兩個偽造負例、內部規則測試、更換 `_decompress` 的長度輸入）。
- **工具缺陷（假的 DETECTED）**：`.pyc` 標頭只記 mtime 到秒，而 `E20`／`E21` 的變異等長 → 同一秒內 Python 誤用上一個變異的 bytecode，讓 `E21` 假性「被偵測到」。已改為 `PYTHONDONTWRITEBYTECODE=1` 並**回頭重跑 TASK-024～028 的矩陣**（結果全部不變）。**假的 DETECTED 與假的 SURVIVED 一樣危險**，這條已寫進 TDD。
- **測試品質**：向量離線內嵌、惡意輸入以固定種子產生（可重現）、`bytes-like` 與錯誤型別都有覆蓋、`cryptography` 的存在性以兩個獨立方式檢查（`find_spec` ＋ requirements）。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 內嵌公鑰 | advisory（**需在 TASK-033 完成**） | `LICENSE_PUBLIC_KEY` 目前是全零佔位（fail closed）；TASK-033 產生 Worker 金鑰後必須替換，否則所有租約都會驗不過 | TASK-033 應把公鑰寫入 `license.py`（或改由 `catalog`／設定注入），並保留「未設定即拒絕」的行為；替換後必須新增一個「用真公鑰驗一個真租約」的整合測試 | 待辦（TASK-033；佔位行為已有測試） |
| A-2 | 內部函式的測試 | advisory | 本張有三個測試直接呼叫私有函式（`_recover_x`／`_decompress`／`_point_equal`／`_is_small_order`），與「只測公開邊界」的慣例不同 | 這是刻意的：這些規則無法從公開 API 構造輸入（需要 `y < 19` 的真實金鑰）。已在測試 docstring 與 TDD 說明理由；若日後改成可注入的解碼器，可改回公開邊界測試 | 已記錄（理由在測試內） |
| A-3 | 無共因子等式的取捨 | advisory | 本張採**無共因子**群等式（`[S]B == R + [k]A`）＋小階點檢查，而非共因子版本（`[8][S]B == [8]R + [8][k]A`）；兩者都符合 RFC 8032，但行為在罕見輸入上不同 | 無共因子版本較嚴（拒絕更多輸入），且與 libsodium 的「strict」模式一致；若日後要批次驗證（共因子版本較快），必須保留 R 的小階點檢查——這正是 `E21` 那個「目前不可觀測」的分支的價值 | 已記錄（`E21` 的判讀） |
| A-4 | 效能 | advisory | 純 Python double-and-add 每次驗章約 3.8 ms（單執行緒）；租約驗證只在啟動／續期時發生，因此足夠 | 若未來要在同一程序驗大量租約，可改 4-bit window 或預計算表；目前不需要 | 已記錄（實測值） |
| A-5 | 流程與工具 | advisory（非程式） | （a）第一輪全量變異出現**假的 DETECTED**（`.pyc` 只記 mtime 到秒，同秒同尺寸的變異會誤用上一個 bytecode）；（b）矩陣進行中計算檔案樹雜湊會讀到中間狀態（`flock` 只保護矩陣彼此） | 已修：子程序加 `PYTHONDONTWRITEBYTECODE=1`、重跑 TASK-024～028 確認結果不變；樹雜湊只在矩陣結束且逐檔 sha256 回到記載值之後計算。兩點都寫進 TDD | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-054 的五項宣稱逐條符合；品質 Review 無 blocking。
- 依變異檢查補強測試 6 處（解碼正規性、`x = 0` 的 sign bit、`_decompress` 的長度輸入、點相等的兩個座標、小階點判定、通用偽造負例）。
- 修正工具 1 處（`PYTHONDONTWRITEBYTECODE=1`）並回頭重跑 TASK-024～028 的矩陣（結果不變）。
- 重審：重跑單檔（22 passed）與全套（**836 passed**）、AC-054 的兩個直接檢查（`find_spec` → `None`、requirements 不含 `cryptography`）、兩個流程驗證器（exit 0），並在凍結版重跑變異矩陣（**22／24 偵測到，2 個等價**）；重讀 `license.py` 的驗章路徑複查正規性檢查、群等式、錯誤處理與 fail-closed 佔位。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-054 的五項宣稱逐條符合）
- 品質 Review：passed（無 blocking；A-1 需 TASK-033 完成，A-2～A-5 已記錄）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-033 替換公鑰）、A-2（刻意的內部規則測試）、A-3（無共因子等式的取捨）、A-4（目前不需要最佳化）、A-5（已記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：`LICENSE_PUBLIC_KEY` 仍是佔位值（fail closed）；尚未與 `Lease` 整合（TASK-030）；沒有共因子／批次驗證；沒有對真實 Worker 簽出的租約做過端到端驗章（TASK-033 之後）
