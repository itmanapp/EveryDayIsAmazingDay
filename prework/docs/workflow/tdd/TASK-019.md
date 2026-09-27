# TASK-019 測試紀錄

- task_id：TASK-019
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-config sha256:b2aa45bd91ccaacf93b71337c5abafa7c0838fac62bbe858aec14e00b4f328b7
- alternative_reason：無（原子寫入與損毀保護以真實檔案系統與位元組比對驗證；SPEC 第 7 節明定 `ediaad.config` 不能只對 mock 宣稱通過）
- Task／Spec 版本：TASK-019 / SPEC-001 v0.4
- 測試邊界：對 `tmp_path` 下的**真實**設定檔呼叫 `load_settings`／`save_settings_atomic`／`validate_settings`，以檔案位元組、目錄內容、`mtime` 與例外型別為觀察邊界；不檢視私有的暫存檔命名常數。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-018 的交付物，全套 **552 passed**（本張完成後為 585 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/config.py` | `c2a0196a` | 新增：`DEFAULT_SETTINGS`、`validate_settings`、`load_settings`、`save_settings_atomic` |
| `tests/test_config.py` | `5c79157e` | 新增：33 個測試 |

## 本張定義的設定鍵集（SPEC 未明訂，如實記載）

文件只說 `config.py` 負責「設定解析＋驗證＋原子寫入」與 `$EDIAAD_HOME/settings.json` 的存在，**沒有列出鍵集**。本張依報告中實際需要被網頁編輯的旋鈕定義七個鍵，每個都對應一個已存在的需求：

| 鍵 | 預設 | 對應 |
| --- | --- | --- |
| `market` | `"crypto"` | AC-035 的市場別規律預設（TASK-015 的 `default_spec_for`） |
| `pattern_id` | `"range_fakeout_reversion"` | TASK-007 的規律識別名 |
| `pattern_spec` | `null` | G4 規律參數面板（`null` ＝ 用市場別預設） |
| `poll_interval_seconds` | `60` | G3 調整輪詢間隔 |
| `horizon` | `5` | 後續走勢統計視窗（TASK-006） |
| `cache_max_age_seconds` | `900` | 報告第 4.6 節的快取有效期（TASK-013 的 `max_age`） |
| `update_enabled` | `true` | 報告第 6.5 節第 6 條「可完全關閉」 |

已列為 Review 的 A-1（需 Spec 追認）；TASK-023／025 若需要其他鍵，應一併更新此表與 Spec。

## Cycle 1：預設值、讀取與原子寫入（AC-040，真實 Red → Green）

- 測試：`save` → `load` 往返；寫入後**目錄不留暫存檔**；自動建立父目錄；覆寫既有內容；`DEFAULT_SETTINGS` 的鍵集固定且 `load_settings` 對不存在的檔案回傳**預設值的副本**（不是同一個物件）；缺鍵由預設值補齊且檔案有給的值優先；`save(DEFAULT_SETTINGS)` 後 `load` 等於 `DEFAULT_SETTINGS`；四種損毀檔（非 JSON、空檔案、頂層為陣列、頂層為字串）各自 `ConfigError`（訊息含檔名）且**原檔位元組不變、無暫存檔殘留**，共 11 個（其中 4 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_config.py -q` | 1 | `11 failed`：`ModuleNotFoundError: No module named 'ediaad.config'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `11 passed in 0.46s` | snap-2026-09-24-ocaievo-config／2026-09-24 |

- 實作：`DEFAULT_SETTINGS`、`_require_int`／`_require_bool`／`_require_text`、`validate_settings`、`load_settings`（缺檔 → 預設值；損毀 → `ConfigError` 且不改動原檔）、`save_settings_atomic`（`tempfile.mkstemp` 產生**唯一**暫存檔 → 寫入 → `flush` ＋ `fsync` → `os.replace`；失敗時清除暫存檔）。
- **驗證一定在碰觸檔案之前**：`validate_settings` 是第一行，因此不合法的設定永遠不會覆蓋既有檔案（有專門測試，變異 M4 抓到）。

## Cycle 2：驗證、失敗保護與並發（**部分既有覆蓋**，另以還原實作取得 Red）

- 測試：未知鍵（存與讀各一次）；**12 種非法值**各自 `ConfigError` 且訊息含鍵名（輪詢間隔是字串／0／布林、`horizon` 為 0、快取有效期為負、`update_enabled` 非布林、未知市場別、空市場別、空規律 ID、規格不是物件、規格身分不一致、規格參數不合法）；**非法儲存不得碰觸既有檔案**（位元組不變、無暫存檔）；`json.dump` 注入 `OSError` 時原檔不變且清除暫存檔；合法 `pattern_spec` 往返；**載入不寫任何東西**（位元組與 `mtime` 都不變）；同一份設定兩次寫出位元相同；不同**鍵插入順序**也位元相同；兩次寫入的暫存檔名互異（以 spy 攔 `os.replace` 觀察來源檔名）；**四個執行緒各寫五次**不得失敗、不得留暫存檔、最終內容必須是某一份完整設定，共 22 個（其中 12 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red（還原實作） | 把 `validate_settings` 的逐鍵驗證與未知鍵檢查還原為最小版後跑本張單檔 | 1 | `13 failed, 18 passed`：12 個非法值案例 ＋「非法儲存不得碰檔案」；「未知鍵」與 Cycle 1 的 11 個案例仍綠 | 同上／2026-09-24 |
| Green | 同上 | 0 | `31 passed in 0.65s` | 同上／2026-09-24 |

- **如實記載**：本張的 `validate_settings` 與讀寫函式在同一次操作中一起寫成，因此 Cycle 2 的測試首次執行時**大部分已經會過**（既有覆蓋）。為了留下綁定證據，我把逐鍵驗證暫時還原為最小版並記錄了失敗清單（上面那一列），再還原實作。這是本專案反覆出現的順序瑕疵（TASK-013／015／017 同型），Review A-5 再次記錄。
- **兩處測試夾具錯誤（不是實作錯）**：`pattern_spec` 依 TASK-007 是**嚴格還原**（缺欄位即擋），因此我原本用 `{"pattern_id": "other", "range_bars_min": 5}` 這種殘缺規格測「身分不一致」時，實際得到的是「規格缺少欄位」；另外「位元可重現」測試把規格的 `pattern_id` 設為 `p` 卻沒有一併設定 `pattern_id`，被身分一致性檢查擋下。兩者都已改成由 `NAMED_PATTERNS` 取完整規格——**實作正確，是我的夾具不完整**。

## Cycle 3（補測）：兩個邊界與一個等效變異

- 補 `cache_max_age_seconds = 0` 是合法值（＝不快取／一律過期）與「不同鍵插入順序輸出位元相同」兩個測試。
- **M17（移除 `sort_keys=True`）第一輪存活**，追查後確認是**等效變異**：`validate_settings` 一律以 `DEFAULT_SETTINGS` 為底合併（未知鍵更早已被擋下），因此輸出鍵序**永遠**是 `DEFAULT_SETTINGS` 的宣告順序，`sort_keys` 對目前的 schema 是多餘參數（而且會把鍵排成字母序、失去邏輯分組）。**與 TASK-013 的 M16 同型：移除冗餘碼而不是補測試。** 已移除該參數、在 `validate_settings` 的 docstring 寫明鍵序保證，並把 M17 改寫成真正的變異（讓輸入鍵序滲進輸出）以確認可被偵測。
- 測試數 31 → 33。

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 非原子寫入（`copy`，留下暫存檔） | 被抓到 |
| M3 | 暫存檔名固定（並發會互撞） | 被抓到 |
| M4 | 寫入前不驗證 | 被抓到 |
| M5 | 缺檔時丟錯而非回預設 | 被抓到 |
| M6 | 不用預設值補齊 | 被抓到 |
| M7 | 損毀 JSON 靜默回預設 | 被抓到 |
| M8 | 不檢查頂層是物件 | 被抓到 |
| M9 | 不驗證市場別 | 被抓到 |
| M10 | 不檢查規格身分一致 | 被抓到 |
| M11 | 失敗時不外洩可讀錯誤 | 被抓到 |
| M12 | 失敗時不清暫存檔 | 被抓到 |
| M13 | 不建立父目錄 | 被抓到 |
| M14 | 缺檔時回傳共用預設物件 | 被抓到 |
| M15 | 快取有效期下限改成 1 | 被抓到（補了「0 合法」的測試） |
| M16 | 不檢查 `update_enabled` 型別 | 被抓到 |
| M17 | 合併時把輸入鍵序帶進輸出 | 被抓到（原版 `sort_keys` 為等效變異，已移除冗餘參數） |
| M18 | `horizon` 下限改成 0 | 被抓到 |
| M19 | 不驗證 `pattern_spec` | 被抓到 |

工具紀律：整行比對、`count(frm) == 1` 才執行、每次變異後立即還原並比對檔案 sha256。矩陣在**最終版檔案**上重跑過（另把 `validate_settings` 納入公開介面之後），18／18 全數被抓到；還原後 `ediaad/config.py` `c2a0196a` 與變異前一致，單檔 `33 passed`。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_config.py -q` | 0（`33 passed in 0.81s`） | snap-2026-09-24-ocaievo-config |
| 相關回歸（監控，本張不改它） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_monitor.py -q` | 0（`24 passed in 0.38s`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`585 passed in 23.91s`） | 同上 |
| 未使用匯入掃描 | `ocaievo/`：AST 粗檢 `ediaad/` | 0（無發現） | 同上 |
| 變異後還原驗證 | 同本張單檔 | 0（`33 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 已知邊界（記錄）：
  - **設定檔尚無呼叫端**：`load_settings`／`save_settings_atomic` 目前沒有被 `cli`／網頁使用（TASK-020 的端點與 TASK-025 的設定頁才是消費者）。`$EDIAAD_HOME/settings.json` 的**路徑組合**也還沒有人負責——`default_home()`／`keys_path()` 目前住在 `markets/us.py`（TASK-016），當 TASK-025 同時需要 `keys_path` 與 `settings_path` 時，`$EDIAAD_HOME` 的解析應該集中到一個中立模組（見 Review A-2）。這是 TASK-013 以來那條跨 Task 缺口的一部分。
  - **不改變 `monitor.load_config` 對 `watchlist.json` 的既有鍵集與錯誤語意**（TASK-019 的邊界）：本張的 `settings.json` 與 `watchlist.json` 是兩個獨立的檔案，沒有任何一方讀另一方。
  - **不寫入或讀取 `keys.json`**（TASK-016 的範圍）；**不實作設定版本遷移**：舊版 `settings.json` 若含未知鍵會被擋下（`ConfigError`），而不是自動升級欄位——這是刻意的（寧可讓使用者看到明確錯誤，也不要靜默丟棄未知欄位）。
  - 損毀的設定檔**不覆蓋、也不自動以預設值修復**：使用者必須自行處理（或刪檔重來），否則下一次儲存就會永久失去原內容。
  - `save_settings_atomic` 對**同一路徑**的並發寫入有測試（四個執行緒、真實檔案系統），但**跨程序**的並發寫入未測（同一台機器上的兩個 `ediaad` 程序同時寫設定檔；`os.replace` 仍保證不會半寫，但「最後寫入者勝」是預期行為）。
- 未涵蓋：設定端點與儲存按鈕（TASK-020／025）、規律參數面板（TASK-023）、更新開關的實際作用（TASK-032）、`$EDIAAD_HOME` 解析的集中化（見 Review A-2）。
