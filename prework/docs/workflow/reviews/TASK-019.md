# TASK-019 Code Review

- task_id：TASK-019
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-config sha256:b2aa45bd91ccaacf93b71337c5abafa7c0838fac62bbe858aec14e00b4f328b7
- Task／Spec 版本：TASK-019 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含設定鍵集的定義追認、`sort_keys` 等效變異的判讀與 `validate_settings` 的公開化）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `b2aa45bd91ccaacf93b71337c5abafa7c0838fac62bbe858aec14e00b4f328b7`；本張新增 `ediaad/config.py` `c2a0196a…`、`tests/test_config.py` `5c79157e…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的已提交、未提交、新增檔案：上述兩個檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：**`ediaad/monitor.py` 完全未修改**（TASK-019 的邊界要求「不改變 `load_config` 對 `watchlist.json` 的既有鍵集與錯誤語意」）；`ediaad/store.py`（TASK-018）與 `markets/*` 亦未修改
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-040、第 5 節模組表（`ediaad/config.py`）、「輸入／輸出、驗證與錯誤格式」（缺鍵、未知鍵、型別錯誤 → `ConfigError`，訊息指出鍵名或索引位置）、資料生命週期（`$EDIAAD_HOME/settings.json`）、第 6 節品質需求（可靠性：設定與 catalog 以原子寫入避免半寫狀態；可重現性：同一輸入必須得到位元相同的結果）、第 7 節測試策略（真實檔案系統、不以 mock 取代）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.1 節（`config.py` 職責）、第 6.3 節（網頁層只做參數解析與錯誤轉譯）、第 4.6 節（快取 `max_age`）、第 6.5 節第 6 條（可完全關閉）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-040 | `ediaad/config.py`（`save_settings_atomic`／`load_settings`／`validate_settings`／`DEFAULT_SETTINGS`）；`tests/test_config.py` 33 個案例 | 符合 | A-1、A-2、A-3、A-4、A-5（advisory） |

逐條核對：

- **AC-040「合法者以暫存檔＋rename 原子寫入」**：`save_settings_atomic` 以 `tempfile.mkstemp` 在同目錄產生唯一暫存檔、`flush` ＋ `fsync` 後 `os.replace`；測試斷言寫入後內容正確、**目錄不留暫存檔**、父目錄自動建立、可覆寫既有內容。原子性另以「取代前失敗 → 原檔位元不變且清掉暫存檔」與「四個執行緒並發寫入 → 最終是某一份完整設定」證明。符合。
- **AC-040「損毀設定不會覆蓋原檔」**：四種損毀檔（非 JSON、空檔案、頂層是陣列、頂層是字串）各自 `ConfigError`（訊息含檔名），且測試以 `read_bytes()` 前後相等斷言原檔未動；`load_settings` 不做任何寫入（位元組與 `mtime` 都不變，有測試）。符合。
- **AC-040「回報錯誤並保留原內容」**：錯誤訊息一律含**檔名與出錯鍵名**（`_require_int`／`_require_bool`／`_require_text` 都帶鍵名；損毀檔訊息帶路徑），符合 SPEC 第 5 節「訊息指出鍵名或索引位置」。符合。
- **「`DEFAULT_SETTINGS` 提供可用的預設鍵集，缺值時的行為明確定義」**：缺檔 → 預設值副本；檔案有值 → 該值優先、其餘補預設；`save(DEFAULT_SETTINGS)` 後 `load` 等於 `DEFAULT_SETTINGS`（三者一致，各有測試）。符合。

## 品質 Review

- **驗證先於寫入（本張最重要的可靠性決定）**：`validate_settings(settings)` 是 `save_settings_atomic` 的第一行，因此**不合法的設定永遠不會碰觸既有檔案**。這讓 AC-040 的「損毀不覆蓋」不只是 load 端的性質，而是整個模組的性質（有專門測試 `test_an_invalid_save_never_touches_the_existing_file`，變異 M4 抓到）。
- **原子寫入用 `mkstemp` 而不是固定名稱**：這同時滿足兩件事——「不留暫存檔」（成功時 `os.replace` 會把暫存檔變成目標檔）與「並發不互撞」（每次寫入拿到不同檔名，有 spy 測試斷言兩次來源檔名不同）。變異 M1／M3／M12 全部被抓到。
- **`fsync` 的取捨**：寫入後 `flush` ＋ `fsync` 才 `replace`，讓「已 replace」的內容真的落到磁碟（避免斷電後出現空檔）。代價是每次儲存多一次同步 I/O；設定檔是小檔案且不頻繁，值得。未以斷電測試驗證（無法在單元測試中模擬），屬構造上的保證。
- **鍵序的確定性（M17 的收穫）**：`validate_settings` 一律以 `DEFAULT_SETTINGS` 為底合併，而未知鍵在合併**之前**就被擋下，因此輸出鍵序永遠是宣告順序——`sort_keys=True` 對目前的 schema 是多餘的（等效變異 M17 存活就是證據）。已移除，並在 docstring 寫明「鍵序保證來自固定基底」；同時保留「不同鍵插入順序 → 位元相同」的測試，把這個性質變成有測試支撐的事實。**這是本張「變異檢查改變了實作」的一例。**
- **錯誤分層與檔案語意一致**：設定檔問題一律 `ConfigError`（exit 2 的輸入錯誤），與 `monitor.load_config`／`catalog.load_catalog` 的選擇一致；`load_catalog` 對缺檔丟錯，而 `load_settings` 對缺檔回預設值——差異是刻意的：`settings.json` 缺席是**首次啟動的正常狀態**，而 catalog 缺席由 `catalog_version` 單獨處理（TASK-017）。兩者都有測試與註解。
- **不靜默修復**：損毀的設定檔不會被自動以預設值覆蓋，未知鍵也不會被靜默丟棄（`ConfigError`）。理由：靜默修復會讓使用者在「下一次儲存」時永久失去原內容或未知欄位。這是與「不誤報優先」一致的保守選擇。
- **依賴方向**：`config.py` 依賴 `errors`、`patterns`（`from_json` 驗證 `pattern_spec`）與 `markets.calendar`（`MARKET_PATTERN_DEFAULTS` 驗證市場別）。依 SPEC 第 5 節的依賴線（`cli/app/web → monitor/store/config/… → patterns/… → errors/data/markets`），`config` 在 `markets` 之上，因此這個方向合法。
- **測試品質**：每個驗證分支都斷言「訊息含鍵名」；失敗路徑同時斷言「原檔位元不變」與「無暫存檔」；並發以真實執行緒 ＋ 真實檔案系統驗證；重現性以位元組比對驗證（含鍵序）。未發現新的問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 規格補充 | advisory（**需 Spec 追認**） | `settings.json` 的**七個鍵**是本張依報告需求定義的（SPEC 只說 `config.py` 負責解析／驗證／原子寫入，未列鍵集）；`cache_max_age_seconds` 與 `update_enabled` 的預設值（900／true）也是本張選定 | 於 SPEC 第 5 節補上 `settings.json` 的鍵集與型別表；TASK-023（參數面板）／TASK-025（設定頁）若需要其他鍵，應一併更新 Spec 與 `DEFAULT_SETTINGS` | 待追認（行為已由測試固定；TDD 紀錄有完整對照表） |
| A-2 | 跨 Task 缺口（沿用 TASK-013 A-1～018 A-1） | advisory（**需在後續 Task 處理**） | 設定檔**尚無呼叫端**，且 `$EDIAAD_HOME` 的路徑組合沒有人負責：`default_home()`／`keys_path()` 目前住在 `markets/us.py`（TASK-016），而 `settings.json` 也需要同樣的解析。TASK-025 會同時需要兩者 | 抽一個中立模組（例如 `ediaad/paths.py`）集中 `default_home()` 與各產物路徑（`keys_path`／`settings_path`／`db_path`／`catalog_path`），`markets/us.py` 改為從那裡匯入；並把 TASK-013 以來的接線缺口（來源分派／市場別預設／日曆／除權息／金鑰狀態／catalog 對照／store 接線／設定端點）一起編入 TASK-025 或 TASK-037 | 待辦（已記於 `STATE.md` 待決事項） |
| A-3 | 未測情境 | advisory | 並發寫入只測了**同一程序的四個執行緒**；跨程序（兩個 `ediaad` 程序同時寫設定檔）未測。`os.replace` 仍保證不半寫，但「最後寫入者勝」 | 若 TASK-025 的端點可能被多個分頁同時呼叫，補一個跨程序（`subprocess`）測試；目前風險低（單一使用者、單機） | 延後（無現時需求，已記錄） |
| A-4 | 公開介面補充 | advisory | `validate_settings` 不在 SPEC 的模組表（只列 `load_settings`／`save_settings_atomic`／`DEFAULT_SETTINGS`） | 保留並公開的理由：TASK-020 的端點需要「驗證但不寫入」（存檔前檢查請求內容）；建議在 SPEC 模組表補上 | 待追認（已納入 `__all__`） |
| A-5 | 流程紀律 | advisory（非程式） | `validate_settings` 與讀寫函式一次寫成，Cycle 2 多數測試首次即過（既有覆蓋）；以「還原為最小實作 → 13 failed／18 passed」補綁定證據。另兩處測試夾具用了殘缺的 `pattern_spec`（TASK-007 是嚴格還原）而被自己的驗證擋下 | 已全部在 TDD 紀錄如實記載。下一張若同一模組含多個獨立行為，先在 Cycle 1 把未測的驗證留成最小版 | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-040 逐條符合；品質 Review 無 blocking。
- 依 Review 與變異檢查修正 2 處：移除多餘的 `sort_keys=True`（等效變異 M17 的收穫，改以 docstring 說明鍵序保證）；把 `validate_settings` 納入公開介面（TASK-020 的端點需要）。
- 補 2 個邊界測試（`cache_max_age_seconds = 0` 合法、不同鍵插入順序位元相同）。
- 重審：重跑單檔（33 passed）、相關回歸（24 passed，確認 `monitor.py` 未受影響）與全套（585 passed）；重讀 `config.py` 複查驗證順序、合併語意、暫存檔生命週期與 fsync。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-040 的四項宣稱逐條符合）
- 品質 Review：passed（無 blocking；A-1／A-4 需 Spec 追認，A-2 需在後續 Task 落實，其餘為延後或已記錄）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（需 Spec 補充）、A-2（TASK-025／037 的整合範圍）、A-3（無現時需求）、A-4（需 Spec 補充）、A-5（流程記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：設定檔尚無呼叫端；`$EDIAAD_HOME` 解析未集中；跨程序並發寫入未測；不實作設定版本遷移（未知鍵一律擋下）；損毀檔不自動修復
