# TASK-028 Code Review

- task_id：TASK-028
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-license-model sha256:0c378a8ba64fa1a99b86a10b6489a1ce19e50accfaf157dcb530f21b8e8a9e38
- Task／Spec 版本：TASK-028 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 `signing_payload` 的跨 Task 契約與變異存活者的處理）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `337e645a8137bd0ddf8c44ae382e8891875274629574f62361c76d1dc7b31749`（79 個檔案）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `0c378a8ba64fa1a99b86a10b6489a1ce19e50accfaf157dcb530f21b8e8a9e38`（81 個檔案）；本張新增 `ediaad/license.py` `461510ff…`、`tests/test_license_fingerprint.py` `0b2c9922…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：上述兩個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：無（本張未修改任何既有檔案；`ediaad/license.py` 在 SPEC 第 5 節模組表中已列，本張是它的第一個實作）
- 程式規範來源：`docs/workflow/SPEC.md` AC-055、第 5 節 `ediaad/license.py`（`Lease`／`machine_fingerprint`／`verify_lease`）與「租約格式」JSON（簽章涵蓋除 `sig` 外所有欄位）、「資料生命週期、權限與狀態轉移」、第 6 節安全；`docs/architecture/ENGINEERING-REPORT.md` 第 6.4 節租約格式與時鐘篡改防護、第 2.12 節；`docs/workflow/PROJECT.md` 環境實測（`/etc/machine-id` 可讀、33 bytes 含換行）；`docs/workflow/CONTEXT.md` 的「機器指紋」與「租約」；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-055 | `ediaad/license.py`（`machine_fingerprint`／`Lease`／`verify_lease`）；`tests/test_license_fingerprint.py` 16 個案例 | 符合 | A-1～A-5（advisory） |

逐條核對：

- **AC-055「可讀的 `/etc/machine-id` → 得到 sha256 前 16 碼的穩定字串」**：`machine_fingerprint` 去空白後取 `sha256(...).hexdigest()[:16]`；測試斷言值等於 `sha256(b"abc123").hexdigest()[:16]`、長度 16、完整匹配 `[0-9a-f]{16}`，並斷言 `DEFAULT_MACHINE_ID_PATH == "/etc/machine-id"`。符合。
- **AC-055「同一機器重算相同」**：同一程序重複計算、四種空白寫法、以及**另起一個 Python 子程序**重算都得到相同值。符合。
- **AC-055「租約指紋不符時驗證失敗」**：`verify_lease` 在 `lease.machine != 目前指紋` 時回 `False`，且**不呼叫** `verify_sig`（測試斷言驗章器沒有被呼叫）。符合。
- **AC-055 的錯誤處理**：讀取失敗（注入的 reader 丟 `OSError`）、內容為空、只有空白都丟出 `ConfigError` 且訊息包含來源路徑；**不回傳空字串或固定常數**（有測試，且變異 `L02`／`L07` 證明）。符合。
- **租約格式（SPEC 第 5 節）**：`to_json` 的鍵集合等於七個欄位、鍵序 `sort_keys=True`、`from_json` 嚴格還原且往返相等；`signing_payload` 涵蓋除 `sig` 以外的所有欄位（逐一改動都改變 bytes、改 `sig` 不改變）。符合。
- **本張不做的部分**：Ed25519 驗章（TASK-029）、啟用／續期流程（TASK-030／031）、租約落地與時鐘防護（TASK-030）、功能分級（TASK-031）都沒有實作；`verify_lease` 在沒有驗章器時丟出 `ConfigError` 並在訊息指名 TASK-029，**不假裝通過**。符合。

## 品質 Review

- **`signing_payload` 是跨 Task 的契約，必須只有一份**：SPEC 說「簽章涵蓋除 `sig` 外的所有欄位」但沒指定序列化方式。若 TASK-029（驗章）與 TASK-030（簽發）各自實作一次，簽章範圍會分岔，而且**兩邊的測試都會過**（各自 round-trip）——這種缺陷只會在真實金鑰上線時才炸開。本張把它定義成公開函式並以**逐字 bytes** 釘住正規形式（`sort_keys=True`、`separators=(",", ":")`、`ensure_ascii=False`、UTF-8），兩張 Task 都必須用它。
- **「還沒驗章」不等於「驗章失敗」**：`verify_sig` 未注入時丟出 `ConfigError`（訊息指名 TASK-029）。回 `False` 會被讀成「簽章無效」，那是不同的意思——與 F-003（「資料不足」vs「沒有命中」）同一個原則，也是本專案反覆強調的錯誤語意紀律。
- **指紋失敗必須吵**：回空字串或固定常數會讓所有機器看起來一樣，等於沒有綁定；三種失敗（讀不到、空、只有空白）都丟出 `ConfigError` 並附來源路徑。
- **指紋不進證據**：真實 `/etc/machine-id` 只驗形狀，測試與文件都不記錄指紋值——避免把機器資訊寫進專案。
- **嚴格還原與 frozen 沿用既有慣例**：`Lease.from_json` 的缺欄位／未知欄位／型別錯誤都丟 `ConfigError`（與 `PatternSpec.from_json` 同一套訊息風格），`Lease` 是 frozen dataclass；`features` 在 `__post_init__` 正規化為 tuple（JSON 只有陣列，不統一會讓 tuple 建構的往返不相等——這是寫測試時發現並修掉的）。
- **純標準庫**：只用 `hashlib`／`json`／`dataclasses`／`datetime`／`pathlib`，沒有引入 `cryptography`（SPEC 第 6 節與 AC-054 的要求；Ed25519 由 TASK-029 以純 Python 實作）。
- **可測性**：`read_text` 與 `verify_sig` 兩個注入點讓本張完全離線且不依賴真實機器狀態（真實檔案只做形狀檢查）；跨程序穩定性以真的子程序驗證（不是只在同一程序內比對）。
- **變異測試的強度**：20 個變異在凍結版全數被抓到。第一階段抓到 1 個真實存活者（`L13`：`from_json` 的物件型別檢查被「缺少欄位」守門掩蓋）並補「鍵剛好齊全的 tuple」案例擊殺；另 3 處在跑之前就先補強（預設來源常數、非字串但格式錯誤的 ISO 時間、`signing_payload` 的逐字 bytes）。
- **測試品質**：指紋以注入 reader ＋ `tmp_path` 假檔驗證（含預設 reader 與跨程序），租約以 JSON 往返與嚴格還原驗證，`verify_lease` 以注入的驗章器單獨驗證指紋閘門。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 契約（**重要**） | advisory（需追認） | `signing_payload` 的正規形式（鍵序、分隔符、編碼）是本張定義的；SPEC 第 5 節只說「簽章涵蓋除 `sig` 外的所有欄位」 | TASK-029（驗章）與 TASK-030（簽發）**必須**呼叫 `license.signing_payload`，不得自行序列化；建議在 SPEC 第 5 節的租約段落補一句「被簽章內容的序列化方式由 `signing_payload` 定義」 | 已寫入 `license.py` docstring 與本表；測試逐字釘住 bytes |
| A-2 | `sig` 的編碼 | advisory | `Lease.sig` 只要求是字串（十六進位或 base64 都可）；空字串也允許（驗章由 TASK-029 負責，空簽章必然驗不過） | TASK-029 應在驗章時明確處理「空／非十六進位」的簽章並給可讀錯誤；若 SPEC 要固定編碼（十六進位），需在該 Task 追認 | 待辦（TASK-029） |
| A-3 | `machine` 的嚴格度 | advisory | `machine` 必須是 16 碼小寫十六進位（與 `machine_fingerprint` 的輸出格式一致）；這比 SPEC 的文字更嚴 | 這是刻意的：租約的 `machine` 只能來自 `machine_fingerprint()`；若日後要支援其他指紋來源，需先改 SPEC | 已記錄（測試涵蓋） |
| A-4 | 時鐘與到期 | advisory | 本張**不檢查** `expires_at` 是否已過（時鐘篡改防護與到期停止屬 TASK-030／AC-053、AC-058）；`verify_lease` 只回答「是不是這台機器 ＋ 簽章是否有效」 | TASK-030 應在 `verify_lease` 之上加到期與 `high_water` 檢查，不要把到期判斷塞進本函式（否則本張的測試語意會混在一起） | 待辦（TASK-030） |
| A-5 | 流程記載 | advisory（非程式） | 變異 `L13`（`from_json` 的物件型別檢查）第一輪存活：原本的測試輸入會先被「缺少欄位」擋下，看不出型別檢查的作用 | 已補「鍵剛好齊全的 tuple」案例並如實記載；另 3 處（預設來源常數、格式錯誤的 ISO 字串、逐字 bytes）在跑之前就先補強 | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-055 的三項宣稱與租約格式逐條符合；品質 Review 無 blocking。
- 依測試回饋修正實作 1 處：`features` 在 `__post_init__` 正規化為 tuple（讓 tuple 建構的 JSON 往返相等）。
- 依變異檢查補強測試 4 處（`L13` 的 tuple 案例、預設來源常數、格式錯誤的 ISO 字串、`signing_payload` 的逐字 bytes）。
- 重審：重跑單檔（16 passed）與全套（**814 passed**）、兩個流程驗證器（exit 0），並在凍結版重跑變異矩陣（**20／20 偵測到**）；重讀 `license.py` 複查指紋錯誤路徑、租約嚴格還原、簽章涵蓋範圍與 `verify_lease` 的三種結果語意。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-055 的三項宣稱與租約格式逐條符合）
- 品質 Review：passed（無 blocking；A-1 需 TASK-029／030 遵守，A-2／A-4 是後續 Task 的責任，A-3／A-5 已記錄）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（跨 Task 契約，已寫入 docstring）、A-2（TASK-029）、A-3（刻意的嚴格度）、A-4（TASK-030）、A-5（已記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：`verify_lease` 的簽章那一半在 TASK-029 前一律 `ConfigError`；不檢查到期（TASK-030）；租約不落地（TASK-030）；`features` 的功能分級未實作（TASK-031）
