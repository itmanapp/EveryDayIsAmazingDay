# TASK-016 測試紀錄

- task_id：TASK-016
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-twelve-data sha256:30b5307030468ea3069ac561af5d466cc17c7828ec1bcb14b04ef88295790c68
- alternative_reason：無（無金鑰與有金鑰兩種情境皆可用 `tmp_path` 與假 HTTP 客戶端完整驗證；真實金鑰與額度依 SPEC 第 8 節 Q-013 為 deferred）
- Task／Spec 版本：TASK-016 / SPEC-001 v0.4
- 測試邊界：`get_source("twelvedata").fetch`／`search` 的例外與回傳值、`load_api_key`／`save_api_key`／`default_home` 對 `$EDIAAD_HOME/keys.json` 的檔案效果（權限位與內容），以及日誌與其他檔案的內容掃描。HTTP 一律注入假客戶端，`EDIAAD_HOME` 以 `tmp_path` 取代，全程離線。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-015 的交付物，全套 **411 passed**（本張完成後為 475 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/markets/us.py` | `df80b096` | 新增：`TWELVE_DATA_URL`、`INTERVAL_MAP`、`default_home`、`keys_path`、`load_api_key`、`save_api_key`、`TwelveDataSource` |
| `ediaad/markets/__init__.py` | `d0f3e5ad` | 修改：匯入 `us` 以完成註冊（四個來源齊備） |
| `tests/test_markets_twelvedata.py` | `b0d4db8a` | 新增：64 個測試 |

## Cycle 1：金鑰的讀取、寫入與隔離（AC-036，真實 Red → Green）

- 測試：無金鑰時 `fetch` 的 `SourceError` 同時含申請網址、完整 `keys.json` 路徑與來源名稱；`load_api_key` 讀回金鑰；`save_api_key` 建立 `0600` 的檔案且**保留其他來源的鍵**、不留暫存檔、拒絕空／非字串金鑰、**不覆寫損毀的檔案**（位元組不變）；六種壞金鑰檔（缺檔、損毀 JSON、無 `twelvedata` 鍵、空字串、空白、非字串、不是物件）各自可讀錯誤；`default_home` 依 `EDIAAD_HOME`、空白值回退 `~/.local/share/ediaad`、`HOME` 被改寫時即時生效；**客戶端例外含金鑰時訊息經遮蔽且 `__cause__` 為 `None`**；日誌不含金鑰，共 18 個（其中 6 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_markets_twelvedata.py -q` | 1 | `16 failed`：`ModuleNotFoundError: No module named 'ediaad.markets.us'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `16 passed in 0.34s` | snap-2026-09-24-ocaievo-twelve-data／2026-09-24 |

- 最小實作（**刻意只做金鑰層與無金鑰路徑**，讓 Cycle 2 有真實 Red）：`default_home`／`keys_path`／`_redact`／`_missing_key_error`／`load_api_key`／`save_api_key`（`os.open(..., 0o600)` ＋ `os.replace` 原子寫入）／`_get_json`（例外遮蔽），`fetch` 只做到讀金鑰與組 URL（解析為 `NotImplementedError`），`search` 為 `NotImplementedError`。
- **金鑰外洩的三個實際管道都處理了**：
  1. **錯誤訊息**：客戶端例外常帶著完整 URL（含 `apikey=`），因此所有對外訊息都過 `_redact`（先換掉已知金鑰，再以正則遮蔽任何 `apikey=...`）。
  2. **`__cause__`**：若原始訊息含金鑰，改為**不鏈結**原例外——否則未來的 traceback 會把金鑰印出來。測試直接斷言 `excinfo.value.__cause__ is None`（變異 M19 證明此斷言有效）。
  3. **檔案**：`save_api_key` 只寫 `<home>/keys.json`，並保留同檔其他鍵、拒絕覆寫損毀檔；測試走完一次完整流程後掃描 `home` 與 `watchlist.json`，斷言除了 `keys.json` 之外沒有任何檔案含金鑰。

## Cycle 2：有金鑰時的取得與解析（AC-036，真實 Red → Green）

- 測試：回傳值符合 Series 契約（欄位順序、`datetime64[ns, UTC]`、五個 `float64`）；**由新到舊的 `values` 轉成升冪**；URL 帶 `symbol=`（大寫正規化）／`interval=`／`outputsize=`／`apikey=`；八個週期各自對應到 Twelve Data 的參數名；宣告的 `supported_intervals` 與映射表完全一致且 `needs_api_key is True`；`401` 與 `429` 回應各自保留來源的可讀說明且不含金鑰；八種畸形回應 → 可讀 `SourceError`；七種非法參數 → `ConfigError` 且**發生在讀金鑰之前**；回應比 `limit` 長時取最近 N 根；缺 `volume` 時補 0；完整流程後除 `keys.json` 外無檔案含金鑰，共 27 個（其中 15 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `24 failed`：解析路徑的 `NotImplementedError`（參數驗證類已綠） | 同上／2026-09-24 |
| Green | 同上 | 0 | `48 passed in 0.44s` | 同上／2026-09-24 |

- 實作：`_to_float`（去千分位、錯誤可讀）、`_parse_time_series`（物件檢核 → `status == "ok"` 檢核並保留來源訊息 → 非空 `values` → 逐列檢核必要欄位與型別 → 交由 `data.from_rows` 排序與驗證 → 超過 `limit` 取最近 N 根）、`fetch` 串接。
- **不需要自己反轉順序**：`values` 是由新到舊，而 `data.from_rows` 的 `_build_series` 已經保證「依時間升冪排序」，因此本模組不重複實作排序（同一份資料只有一條結構化路徑，報告 F-001 的教訓）。
- **缺 `volume` 補 0**：Twelve Data 對指數或外匯不提供成交量，但序列契約要求 `volume` 欄位，因此補 0 而不是丟錯（有測試）。
- **參數驗證先於讀金鑰**：呼叫端給錯週期時不該先被抱怨「缺金鑰」，否則使用者會被指向錯誤的方向（有測試）。
- 修正一處訊息：不支援週期的訊息原本只寫「週期」，測試以參數名 `interval` 比對而失敗 → 訊息改為「不支援 interval …」，同時指出參數名與可用週期。

## Cycle 3：商品搜尋（AC-036，真實 Red → Green）

- 測試：無金鑰時 `search` 丟出含申請說明的 `SourceError`；有金鑰時回傳含代號與顯示名稱的 `Instrument` 清單；請求打到 `symbol_search` 端點並帶 `symbol=`／`apikey=`；**空查詢或 `limit < 1` 不讀金鑰也不發請求**；`limit` 生效；`401` 回應可讀且不含金鑰；四種畸形回應；跳過沒有代號的項目並在缺名稱時回退為代號；客戶端例外含金鑰時經遮蔽且日誌不含金鑰，共 11 個（其中 4 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `12 failed`：`NotImplementedError` | 同上／2026-09-24 |
| Green | 同上 | 0 | `60 passed in 0.51s` | 同上／2026-09-24 |

- 實作：`_parse_symbol_search`（物件與 `status` 檢核 → `data` 必須是陣列 → 逐項檢核、跳過無代號者、`instrument_name` 為空時回退代號 → `limit` 截斷）、`search`（空查詢早退 → 讀金鑰 → 請求 → 解析）。

## Cycle 4（補測）：把兩個存活變異變成可偵測

- **M6（不遮蔽已知金鑰）第一輪存活**：原因是我的兩個遮蔽測試都讓金鑰以 `apikey=KEY` 形式出現，光靠 `apikey=` 的正則就足以遮蔽，known-secret 替換形同多餘。但那個替換涵蓋的正則涵蓋不到——客戶端或中介層可能用其他寫法提到金鑰（例如「rejected credentials `<key>`」）。已補一個**不含 `apikey=` 前綴**的測試，M6 立刻被抓到。
- 另一個補測是「`apikey=` 出現的不是我們已知的金鑰」（例如來源端回了一個輪替過的值）：`_redact` 不依賴已知值，因此測試斷言 `apikey=***` 且原值不出現（變異 M7 證明）。
- 測試數 60 → 64。

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 金鑰檔權限改 `0644` | 被抓到 |
| M2 | 寫入時不保留其他來源的金鑰 | 被抓到 |
| M3 | 損毀的金鑰檔直接覆寫 | 被抓到 |
| M4 | 不驗證金鑰內容 | 被抓到 |
| M5 | 非原子寫入（改用 `copy`，留下暫存檔） | 被抓到 |
| M6 | 不遮蔽已知金鑰 | **首次存活 → 補「非 `apikey=` 形式」測試後被抓到** |
| M7 | 不遮蔽 `apikey=` 片段 | 被抓到 |
| M8 | 缺金鑰改丟 `ConfigError` | 被抓到 |
| M9 | 缺金鑰時回空字串 | 被抓到 |
| M10 | 忽略 `status` 錯誤照樣解析 | 被抓到 |
| M11 | 不截斷到 `limit` | 被抓到 |
| M12 | 缺 `volume` 時丟錯 | 被抓到 |
| M13 | 週期映射錯誤（`1d` → `1d`） | 被抓到 |
| M14 | 商品代號不正規化 | 被抓到 |
| M15 | `search` 忽略 `limit` | 被抓到 |
| M16 | 空查詢先讀金鑰才回空清單 | 被抓到 |
| M17 | `search` 不跳過沒有代號的項目 | 被抓到 |
| M18 | 顯示名稱不回退到代號 | 被抓到 |
| M19 | 例外一律鏈結（`__cause__` 外洩） | 被抓到 |
| M20 | 缺金鑰訊息不含申請網址 | 被抓到 |
| M21 | 缺金鑰訊息不含路徑 | 被抓到 |

工具紀律：整行比對、`count(frm) == 1` 才執行、每次變異後立即還原並比對檔案 sha256。矩陣在**最終版檔案**上重跑過（把 `Path.home()` 改為即時求值、並補 `HOME` 測試之後），21／21 全數被抓到；還原後 `ediaad/markets/us.py` `df80b096` 與變異前一致，單檔 `64 passed`。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_markets_twelvedata.py -q` | 0（`64 passed in 0.52s`） | snap-2026-09-24-ocaievo-twelve-data |
| 相關回歸（來源 registry＋監控） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_markets_base.py tests/test_monitor.py -q` | 0（`65 passed in 0.49s`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`475 passed in 19.33s`） | 同上 |
| 整檔 Red（移除實作） | `ocaievo/`：暫時移除 `us.py`（並取消註冊）後跑本張單檔 | 1（`64 failed`：測試檔在函式內匯入，因此每個測試各自失敗） | 同上 |
| 未使用匯入掃描 | `ocaievo/`：AST 粗檢 `ediaad/` | 0（無發現） | 同上 |
| `keys.json` 進版控防護 | 專案根：`grep -n "keys.json" .gitignore` | `10:keys.json` | 同上 |
| 變異後還原驗證 | 同本張單檔與相關回歸 | 0，檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 已知邊界（記錄）：
  - **真實金鑰與額度未驗證**（SPEC 第 8 節 Q-013 為 deferred）：`401`／`429` 的行為以合成回應驗證，不是真實端點。`PROJECT.md` 已記錄 2026-09-24 實測「無金鑰回 `401` 並附申請說明」。
  - `INTERVAL_MAP` 的八個值（含 `4h`）依 Twelve Data 的公開文件撰寫，**未以真實金鑰逐一驗證**；若某週期其實不支援，使用者會拿到來源端的可讀錯誤（不是靜默錯誤資料）。
  - `save_api_key` 的原子性以「同目錄暫存檔 ＋ `os.replace` ＋ 失敗時清除暫存檔」實作，並以「不留暫存檔」測試守住；「寫入過程絕不暴露半寫內容」屬構造上的保證。
  - 金鑰檔案損毀時 `save_api_key` 選擇**中止**（不覆寫）；代價是使用者必須手動修檔，好處是不會毀掉同檔其他來源的金鑰。
  - `TwelveDataSource` 沒有快取（AC-036 未要求）；`<cache_dir>` 快取與來源鏈仍待整合。
  - **本張的來源仍無呼叫端**：`cli._local_cache_fetch` 固定使用 csv 來源，`monitor.load_config` 不知道 `source_id` → 來源的對應；`default_home`／`keys_path` 也尚未被 TASK-019（設定）或 TASK-025（系統狀態頁）使用。這是 TASK-013 A-1 跨 Task 缺口的同一條線（見 Review A-1）。
- 未涵蓋：catalog（TASK-017）、SQLite（TASK-018）、設定與原子寫入（TASK-019）、網頁（TASK-020 之後）、來源分派（TASK-025）。
