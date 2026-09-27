# TASK-012 測試紀錄

- task_id：TASK-012
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-markets-base sha256:588008ed025e518da487ea5d061788435f206d44297ee71a1d2fa174410610ea
- alternative_reason：無（介面、registry 與自訂來源皆可用公開函式加假來源完整驗證）
- Task／Spec 版本：TASK-012 / SPEC-001 v0.4
- 測試邊界：只匯入 `ediaad.markets.base`／`ediaad.markets.custom` 的公開名稱與 `ediaad.monitor.load_config`；不檢視私有字典或模組內部變數。registry 的隔離以公開的 `register`／`unregister` 完成。自訂來源的資料以 `tmp_path` 合成 CSV，完全離線。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-011 的交付物，全套 **208 passed**（本張完成後為 248 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案（本張新增）

| 檔案 | sha256（前 8 碼） |
| --- | --- |
| `ediaad/markets/__init__.py` | `fa74df62` |
| `ediaad/markets/base.py` | `2d048d7e` |
| `ediaad/markets/custom.py` | `80a548f7` |
| `tests/test_markets_base.py` | `8c26d2b9` |

## 本張修改的既有檔案

| 檔案 | sha256（前 8 碼） | 修改內容 |
| --- | --- | --- |
| `ediaad/monitor.py` | `6259c366` | 移除全域 `ALLOWED_INTERVALS`；`Instrument` 改由 `markets.base` 匯入；`instruments[*]` 新增選填 `source_id`；週期驗證改查 `get_source(source_id).supported_intervals` |
| `ediaad/cli.py` | `979418c2` | `_local_cache_fetch` 改委派 `CsvSource`（移除重複的路徑拼接與解析）；順手移除未使用的 `ALLOWED_INTERVALS` 匯入 |
| `tests/test_monitor.py` | `3e521d8b` | 移除全域常數的匯入與 `test_supported_intervals_match_the_spec`（依 AC-030 廢除）；順手移除未使用的 `numpy`／`RunResult` 匯入 |
| `tests/test_scan.py` | `54294fae` | 順手移除未使用的 `numpy` 匯入（TASK-005 遺留的死碼，見 Review A-3） |
| `tests/test_cli_match_monitor.py` | `c54292f2` | 來源失敗的訊息斷言改為「指出缺少的快取檔名」；順手移除未使用的 `sys` 匯入 |

## Cycle 1：`Source` 協定與 registry（AC-030 前半，真實 Red → Green）

- 測試：csv 來源已註冊且具備六項成員；`all_sources()` 以 id 排序列出全部來源；`get_source` 回傳同一個註冊物件；查詢未註冊 id 的訊息含查詢 id 與可用 id；重複 id 需 `replace=True`；`register` 擋下缺 `fetch` 的來源；`unregister` 對未知 id 報錯；各來源各自宣告週期；`INTERVAL_ORDER` 只是排序而非白名單；`Instrument` 四欄位與預設值，共 11 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_markets_base.py -q` | 2 | `ModuleNotFoundError: No module named 'ediaad.markets'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `11 passed in 0.29s` | snap-2026-09-24-ocaievo-markets-base／2026-09-24 |

- 最小實作：`Instrument`（frozen，`symbol`／`interval`／`source_id`／`display_name`）、`Source`（`runtime_checkable` Protocol，六項成員）、registry（`_SOURCES` ＋ `register`／`unregister`／`get_source`／`all_sources`）、`INTERVAL_ORDER`（僅排序用）與 `DEFAULT_SOURCE_ID`；`markets/__init__.py` 匯入即註冊內建來源；`markets/custom.py` 的 `CsvSource` 先以 `NotImplementedError` 佔位，讓 Cycle 2 有真實 Red。
- **如實記載的測試錯誤**：`test_register_rejects_a_duplicate_id_unless_replacement_is_explicit` 第一版以 `FakeDailySource.__new__(FakeDailySource)` 當成「重複 id」的輸入，但它其實尚未註冊，因此不只斷言失敗，還把假來源留在 registry 裡，造成另一個測試的 fixture 註冊失敗（1 failed, 1 error）。**是我的測試寫錯，不是實作錯**；已改為以 `id = "csv"` 的子類別測重複，並在 `finally` 還原真正的 `CsvSource`。

## Cycle 2：自訂 CSV 來源（AC-037，真實 Red → Green）

- 測試：`fetch` 的結果與 `load_csv` 逐欄相同（`assert_frame_equal`）；缺檔丟 `SourceError` 且訊息含預期檔名；未指定目錄丟 `ConfigError`；可用 `root=` 逐次指定目錄；**五種壞輸入（缺欄位、空檔案、非數值、時間無法解析、重複時間戳）的 `DataFormatError` 訊息與 `load_csv` 逐字相同**；`search` 對空查詢／`limit < 1` 回空清單、對輸入回傳單筆 `Instrument`、遵守 `limit`，共 12 個（其中 5 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `12 failed`：全部為 `NotImplementedError`（`search`／`fetch`），既有 11 個仍綠 | 同上／2026-09-24 |
| Green | 同上 | 0 | `23 passed in 0.34s` | 同上／2026-09-24 |

- 實作：`CsvSource.search`（去空白；空字串或 `limit < 1` 回 `[]`；否則回單筆，`interval` 為空字串——CSV 檔本身沒有預設週期）與 `CsvSource.fetch`（`<root>/<symbol>_<interval>.csv`；目錄未指定 → `ConfigError`；檔案不存在 → `SourceError`；解析交給 `load_csv`）。
- **AC-037 的關鍵斷言是「逐字相同」**：`assert str(through_source.value) == str(direct.value)`，直接證明來源沒有第二套解析（報告 F-001 的教訓），而不只是「也會丟錯」。

## Cycle 3：設定驗證改依來源查詢週期（AC-030 後半，真實 Red → Green）

- 測試：`monitor` 不再有 `ALLOWED_INTERVALS`；`monitor.Instrument is markets.base.Instrument`；帶 `source_id` 的設定依該來源驗證並回填 `source_id`；**同一個 `1h` 被日線假來源拒收、被 csv 接受**（證明不是全域清單）；未知 `source_id` 的訊息含索引、查詢 id 與可用 id；未指定或空字串的 `source_id` 落到預設來源，共 8 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `8 failed`：`source_id` 被當成未知鍵、`Instrument` 不帶來源、`ALLOWED_INTERVALS` 仍存在 | 同上／2026-09-24 |
| Green | 同上 | 0 | `31 passed in 0.37s` | 同上／2026-09-24 |

- 實作：`monitor.py` 匯入 `Instrument`／`get_source`／`DEFAULT_SOURCE_ID`、移除全域常數與 `Instrument` 定義、`_INSTRUMENT_KEYS` 加入 `source_id`（另立 `_INSTRUMENT_REQUIRED_KEYS` 讓它以選填處理）；驗證流程為「解析 source_id（空 → 預設）→ `get_source` → 檢查 `interval in source.supported_intervals`」，訊息含 `instruments[i].interval`、來源 id 與該來源的可用週期。
- **實作中的一次自傷（已修）**：移除 `Instrument` 類別時，我的取代字串從 `class Instrument:` 開始，留下了它上方的 `@dataclass(frozen=True)`，使 `Watchlist` 疊了兩個裝飾器而丟出 `TypeError: Cannot overwrite attribute __setattr__`。測試立即失敗並暴露問題，已刪除多餘的裝飾器；`tests/test_markets_base.py` 的 8 個失敗在此之後才變成真正的綠燈。教訓：刪除裝飾過的類別時，取代範圍必須涵蓋裝飾器。

## Cycle 4：CLI 的來源轉接改委派（重構，既有覆蓋）

- `cli._local_cache_fetch` 原本自行拼接 `<cache_dir>/<symbol>_<interval>.csv`、自行判斷檔案存在、自行呼叫 `load_csv`；本張改為委派 `CsvSource`，讓「從 CSV 檔取得序列」只有一條實作路徑（F-001 的教訓）。TASK-013 會把這個轉接換成「快取 → 交易所 → 過期快取」的完整來源鏈。
- 無新增測試（行為契約不變），以 TASK-011 的端到端測試作為回歸證據：

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Green（既有覆蓋） | `.venv/bin/python -m pytest tests/test_cli_match_monitor.py -q` | 0 | `21 passed` | 同上／2026-09-24 |

- **兩處既有斷言依本張調整**：TASK-011 的 `test_monitor_exits_one_when_the_source_is_unavailable` 與 `test_local_cache_fetch_raises_source_error_when_the_cache_is_missing` 原本斷言訊息含字串「找不到本地快取」；改走 `CsvSource` 後訊息為該來源的「找不到 CSV 檔：<路徑>」。已把斷言改為「訊息必須指出缺少的快取檔（`BTCUSDT_1h.csv`）」——**改的是斷言的對象（具體檔名）而非放寬標準**，類型（`SourceError`）與 exit code（1）的斷言完全不變。

## Cycle 5（補測）：registry 結構驗證與 `source_id` 型別

- `register` 的 `_validate` 有 9 條防禦分支（id／display_name／supported_intervals×3／needs_api_key／search／fetch），Cycle 1 只覆蓋了 `fetch` 一條。已補參數化測試逐條驗證錯誤訊息指名出錯成員，並斷言**驗證失敗的來源不會進入 registry**。
- 另補 `load_config` 對非字串 `source_id` 的 `ConfigError`。
- 測試數 31 → 41。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Green | `.venv/bin/python -m pytest tests/test_markets_base.py -q` | 0 | `41 passed in 0.43s` | 同上／2026-09-24 |

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1c | `get_source` 未註冊時改丟 `SourceError`（錯誤型別分層） | 被抓到：`test_get_source_reports_the_queried_id_and_the_available_ids` |
| M1b | `get_source` 的錯誤訊息不再列出可用 id | 被抓到：同上 |
| M2 | `register` 不檢查重複 id | 被抓到：`test_register_rejects_a_duplicate_id_unless_replacement_is_explicit` |
| M3 | `all_sources` 反向排序 | 被抓到：`test_all_sources_lists_every_registered_source_sorted_by_id` |
| M4 | `register` 不檢查 `fetch` 可呼叫 | 被抓到：`test_register_rejects_an_incomplete_source` |
| M5 | `load_config` 不套用預設來源（空 `source_id` 直接查 registry） | 被抓到：`test_an_instrument_with_an_empty_source_falls_back_to_the_default` |
| M6 | 週期驗證改回全域 `INTERVAL_ORDER`（重現全域白名單） | 被抓到：`test_load_config_rejects_an_interval_the_named_source_does_not_support`、`test_the_same_interval_is_accepted_by_a_source_that_declares_it` |
| M7 | `CsvSource.fetch` 繞過 `load_csv`（改 `pd.read_csv`） | 被抓到：`test_csv_fetch_returns_exactly_what_load_csv_returns` 與 5 個「逐字相同」案例 |
| M8 | `search` 忽略 `limit` 下界 | 被抓到：`test_csv_search_respects_the_limit` |
| M9 | `fetch` 忽略逐次指定的 `root=` | 被抓到：`test_csv_fetch_accepts_a_per_call_directory` |

工具紀律：變異字串一律「以換行開頭、整行比對」並要求 `count(frm) == 1` 才執行。每次變異後立即還原，並比對檔案 sha256。還原後 `ediaad/markets/base.py` `2d048d7e`、`ediaad/markets/custom.py` `80a548f7`、`ediaad/monitor.py` `6259c366` 與變異前一致，全套 `248 passed`。

**等效變異的處理（M1）**：第一版 M1 只把 `SourceError` 加進 import，未改動丟出的型別，因此「存活」——這是**等效變異**（行為完全相同），不是測試缺口。已改為真正改動 `raise` 型別的 M1c（被抓到），並保留 M1b 證明「列出可用 id」這半個訊息有被斷言。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_markets_base.py -q` | 0（`41 passed in 0.43s`） | snap-2026-09-24-ocaievo-markets-base |
| 相關回歸（序列契約＋監控＋CLI＋來源） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_data.py tests/test_monitor.py tests/test_cli_match_monitor.py tests/test_markets_base.py -q` | 0（`103 passed in 17.10s`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`248 passed in 17.63s`） | 同上 |
| 未使用匯入掃描 | `ocaievo/`：`python3 /tmp/unused_imports.py ediaad`（AST 粗檢，忽略 `__future__`） | 0（無發現） | 同上 |
| 變異後還原驗證 | 同本張單檔與全套 | 0，三個受變異檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 已知邊界（記錄）：
  - 本張只註冊 `csv` 一個來源；AC-030 提到的四個來源齊備由 TASK-013／TASK-014／TASK-016 補齊，整體斷言留待 TASK-037。
  - `INTERVAL_ORDER` 是**排序**常數，不是驗證白名單；csv 來源宣告它全部，因為使用者提供的檔案本來就能是任何週期（檔名即週期）。真正的週期把關發生在來源層。
  - `Instrument.interval` 在 `search` 的結果中為空字串（自訂 CSV 沒有預設週期）；`load_config` 產生的 `Instrument.interval` 一律非空。
  - `DEFAULT_SOURCE_ID = "csv"` 是本張新增的契約（SPEC 未明訂）：設定未寫 `source_id` 時使用唯一不需金鑰的來源。已於 Review 標為需追認的設計決定（A-1）。
  - `unregister` 與 `register(..., replace=True)` 是 SPEC 模組表未列出的公開函式，為測試隔離與 TASK-013／016 註冊來源所需（Review A-2）。
  - `CsvSource` 只讀快取／使用者檔案，不含快取時效與交易所回退（TASK-013）。
- 未涵蓋：Binance／TWSE／Twelve Data 來源（TASK-013／014／016）、catalog 與更新（TASK-017）、交易日曆與除權息還原（TASK-015）、SQLite（TASK-018）。

## 對既有 Task 證據的影響（如實記載）

本張修改了 TASK-005／010／011 的測試檔（死碼匯入、依 AC-030 移除全域常數斷言、訊息斷言改為檔名），因此那三張 Task 紀錄中的逐檔 sha256 已不再指向最新內容。這是規格演化下的正常結果（AC-030 明確要求廢除 TASK-010 建立的全域常數），本張的 Review 已記錄每一處調整。各張 Task 的 `checked_version` 代表**當時**的驗證狀態，不回填。
