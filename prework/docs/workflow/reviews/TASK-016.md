# TASK-016 Code Review

- task_id：TASK-016
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-twelve-data sha256:30b5307030468ea3069ac561af5d466cc17c7828ec1bcb14b04ef88295790c68
- Task／Spec 版本：TASK-016 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 M6 的判讀與三處測試強化）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `30b5307030468ea3069ac561af5d466cc17c7828ec1bcb14b04ef88295790c68`；本張新增 `ediaad/markets/us.py` `df80b096…`、`tests/test_markets_twelvedata.py` `b0d4db8a…`；修改 `ediaad/markets/__init__.py` `d0f3e5ad…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的已提交、未提交、新增檔案：上述三個檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`base`／`custom`／`crypto`／`twse`／`adjust`／`calendar`（TASK-012～015 交付物）本張只新增註冊匯入，未修改其邏輯（`base.py` `526d04ed…`、`crypto.py` `1b1cb639…`、`twse.py` `7b58e675…`、`adjust.py` `0e694cea…`、`calendar.py` `2eb5443a…` 均未變）
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-036、第 5 節模組表（`ediaad/markets/us.py`）、「資料生命週期、權限與狀態轉移」（`keys.json` `0600`、絕不出現在 `watchlist.json`／網頁輸出／日誌）、「外部依賴與失敗處理」（無金鑰或額度用盡回可讀錯誤、不影響其他商品）、第 6 節品質需求（安全：所有外部輸入都必須驗證）、第 8 節 Q-013；`docs/architecture/ENGINEERING-REPORT.md` 第 7.3 節（金鑰型來源的取捨、金鑰必須存在獨立檔案）；`docs/workflow/PROJECT.md`（`EDIAAD_HOME`／`TWELVEDATA_API_KEY`、Twelve Data 無金鑰回 `401`）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-036 | `ediaad/markets/us.py`（`load_api_key`／`save_api_key`／`_redact`、`fetch`／`search`）；`tests/test_markets_twelvedata.py` 64 個案例 | 符合 | A-1、A-2、A-3（advisory） |

逐條核對：

- **AC-036「無金鑰或沒有 `twelvedata` 金鑰時丟出可讀錯誤，訊息含申請說明與應填入的檔案路徑」**：`SourceError` 訊息同時含 `https://twelvedata.com/pricing`、`<home>/keys.json` 完整路徑與來源名稱；六種壞金鑰檔各自有測試（含 `__init__.py` 外的 `HOME` 情境）。符合。
- **AC-036「有金鑰時以注入的假 HTTP 客戶端取得資料並回傳符合 Series 契約的序列」**：契約的五個面向（欄位順序、`datetime64[ns, UTC]`、升冪、五個 `float64`、由新到舊的回應正確反轉）逐項有斷言；假客戶端只被呼叫一次（`http.count == 1`）。符合。
- **AC-036「金鑰只存在 `$EDIAAD_HOME/keys.json`」**：測試走完「存金鑰 → 寫 watchlist → fetch」全流程後，掃描 `home` 與 `tmp_path` 的所有檔案，斷言除 `keys.json` 外沒有任何檔案含金鑰。符合。
- **AC-036「以 `0600` 權限建立」**：`stat.S_IMODE(...) == 0o600`（不只是 `& 0o777`，還要求沒有 setuid／setgid 位）；另斷言 `save_api_key` 時保留同檔其他來源的鍵、不留暫存檔。符合。
- **AC-036「金鑰字串不出現在 `watchlist.json`、網頁輸出或日誌中」**：`watchlist.json` 以檔案內容斷言；日誌以 `caplog` 斷言；**網頁輸出**在 TASK-020 之前不存在，本張以「所有對外訊息（也就是網頁層唯一會序列化的東西）都經過 `_redact`」的方式涵蓋，並在 Review A-3 記錄待 TASK-020 加上端點層的斷言。符合（有範圍說明）。

## 品質 Review

- **金鑰外洩的三個管道都被處理（本張最重要的品質決定）**：
  1. **錯誤訊息**：客戶端例外常帶著完整 URL（`apikey=` 就在裡面），因此所有對外訊息都過 `_redact`——先替換已知金鑰，再以正則遮蔽任何 `apikey=...`。兩層都需要：正則涵蓋「不是我們已知的值」（例如來源端輪替後的值），known-secret 替換涵蓋「以其他寫法出現的金鑰」（例如「rejected credentials `<key>`」）。
  2. **`__cause__`**：若原始訊息含金鑰就**不鏈結**原例外，否則 traceback 會把金鑰印出來。測試直接斷言 `excinfo.value.__cause__ is None`（變異 M19 證明該斷言有效）。這是很容易漏掉的一層——`raise ... from error` 是本能寫法，而它正好是外洩管道。
  3. **檔案**：只寫 `keys.json`，並以全檔掃描斷言。
- **M6 的判讀（存活變異不是等效變異，是我的測試覆蓋不足）**：第一輪 M6（停用 known-secret 替換）存活，因為兩個遮蔽測試都讓金鑰以 `apikey=KEY` 形式出現，光靠正則就夠。但那個替換有正則涵蓋不到的場景，所以是我的測試沒覆蓋，不是實作冗餘。補一個「金鑰以非 `apikey=` 形式出現」的測試後立刻被抓到。**與 TASK-015 的 M9 對照**：那裡是「測試強度不足（`approx` 看不見 ULP）」，這裡是「測試場景不足（只有一種外洩形式）」——兩種都是先判讀、再補測試，而不是直接宣布等效。
- **金鑰檔的寫入語意偏保守且明確**：合併而非覆寫（同檔可能有其他來源的金鑰）；檔案損毀時**中止**而不是重建（寧可讓使用者手動修，也不要毀掉別人的金鑰）；`os.open(..., 0o600)` 從建立的第一刻就是正確權限（不是先建 0644 再 `chmod`，避免中間態）；`os.replace` 原子替換（變異 M1／M2／M3／M5 全部被抓到）。
- **`SourceError` 而不是 `ConfigError`（依 SPEC 的失敗處理表）**：無金鑰或額度用盡**不得影響其他商品**，因此它是單一商品的來源失敗，由監控迴圈的錯誤隔離接住（TASK-010 的 AC-024 已驗證該隔離）。這也讓 CLI 的 exit code 是 1（執行期失敗）而不是 2（輸入錯誤）——使用者並沒有打錯設定，是環境還沒設定好。已在 TDD 紀錄寫明理由。
- **參數驗證先於讀金鑰**：呼叫端給錯週期時不該先被抱怨「缺金鑰」，否則使用者會被指向錯誤的方向。有專門的測試（`test_config_errors_happen_before_reading_the_key`），變異 M16 的同類邏輯在 `search` 上也有一致的處理（空查詢不讀金鑰）。
- **不重複實作排序**：Twelve Data 的 `values` 是由新到舊，但 `data.from_rows` 的契約已經保證「依時間升冪排序」，因此本模組不自己反轉或排序（報告 F-001 的教訓：同一份資料只走一條結構化路徑）。這條契約由 TASK-002 的測試與本張的順序斷言共同守住。
- **依賴方向與可注入性**：`us.py` 只依賴標準庫（`json`／`os`／`re`／`urllib.request`）、`pandas`、`data`、`errors`、`markets.base`；HTTP 客戶端與 `EDIAAD_HOME` 皆可注入，64 個測試全部離線。
- **`default_home` 即時求值**：原本用模組層常數 `DEFAULT_HOME = Path.home() / …`（匯入時凍結）；改為函式內求值，讓 `HOME` 在測試或服務程序中變更時正確生效（有測試）。
- **測試品質**：每個錯誤路徑都斷言訊息裡有可辨識的內容；`401`／`429`／畸形／非法參數／壞金鑰檔各自參數化；安全性相關斷言（`0600`、`__cause__`、全檔掃描、`caplog`）都在同一組測試裡。未發現新的問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 缺口（沿用 TASK-013 A-1／014 A-3／015 A-1） | advisory（**需在後續 Task 處理**） | 本張的來源與 `default_home`／`keys_path` **都沒有呼叫端**：`cli._local_cache_fetch` 固定使用 csv，`monitor.load_config` 不知道 `source_id` → 來源的對應；TASK-019（設定）與 TASK-025（系統狀態頁）都還沒有金鑰狀態的存取入口 | 把「來源分派 ＋ 市場別預設 ＋ 日曆套用 ＋ 除權息還原 ＋ 金鑰狀態」一起編入 TASK-025（或 TASK-037 整合項），並更新其「預計觸及的檔案」 | 待辦（已記於 `STATE.md` 待決事項） |
| A-2 | 未驗證的映射 | advisory | `INTERVAL_MAP` 的八個值（含 `4h`）依 Twelve Data 公開文件撰寫，未以真實金鑰逐一驗證；若某週期其實不支援，使用者會拿到來源端的可讀錯誤 | Q-013 解除（有真實金鑰）後跑一次煙霧測試並記錄結果；或把 `supported_intervals` 縮到已驗證的子集 | 延後（Q-013 deferred） |
| A-3 | 網頁輸出 | advisory | AC-036 提到「不出現在網頁輸出」，但網頁層（TASK-020）還不存在；本張只保證**所有對外訊息**都經過 `_redact` | TASK-020 的錯誤回應與 TASK-025 的系統狀態頁應加上「回應主體不含金鑰」的端點層測試 | 待辦（TASK-020／025） |
| A-4 | 真實端點 | advisory | `401`／`429` 的行為以合成回應驗證，未打真實端點（無金鑰、Q-013 deferred） | 同 A-2：取得金鑰後一併做真實端點煙霧測試 | 延後（Q-013） |
| A-5 | 金鑰檔損毀的處理 | advisory | 損毀時 `save_api_key` 中止而非重建；代價是使用者必須手動修檔 | 保守選擇的理由（避免毀掉其他來源的金鑰）已記錄；若日後提供網頁設定介面，應在該介面提示「金鑰檔損毀，請先備份或修復」 | 已實作並記錄 |
| A-6 | 流程紀律 | advisory（非程式） | Cycle 1 的實作一次寫成（含紅綠分離良好）、`search` 訊息缺參數名、M6 需補測試場景 | 已全部在 TDD 紀錄如實記載 | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-036 逐條符合；品質 Review 無 blocking。
- 依變異檢查與測試回饋修正 3 處：不支援週期的訊息補上參數名 `interval`；`default_home` 改為即時求值（並補 `HOME` 測試）；補「非 `apikey=` 形式」與「未知 `apikey` 值」兩個遮蔽測試。
- 重審：重跑單檔（64 passed）、相關回歸（65 passed）與全套（475 passed）；重讀 `us.py` 複查遮蔽的三個管道、金鑰檔的權限與合併語意、錯誤分層、參數驗證順序與 `search` 的早退；變異矩陣在最終版檔案上 21／21 全數被抓到。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-036 逐條符合；「網頁輸出」以「對外訊息皆經遮蔽」涵蓋並記為 A-3）
- 品質 Review：passed（無 blocking；A-1 需在後續 Task 落實，其餘為延後或已記錄的 advisory）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-025／037 的整合範圍）、A-2／A-4（Q-013 需真實金鑰）、A-3（TASK-020／025）、A-5（已記錄的保守選擇）、A-6（流程記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：真實金鑰與額度未驗證；`4h` 等映射未逐一驗證；無快取；來源仍無呼叫端；網頁層的金鑰斷言待 TASK-020
