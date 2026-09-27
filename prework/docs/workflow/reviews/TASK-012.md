# TASK-012 Code Review

- task_id：TASK-012
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-markets-base sha256:588008ed025e518da487ea5d061788435f206d44297ee71a1d2fa174410610ea
- Task／Spec 版本：TASK-012 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 registry 驗證補測與 M1 等效變異的判讀）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `588008ed025e518da487ea5d061788435f206d44297ee71a1d2fa174410610ea`；本張新增 `ediaad/markets/__init__.py` `fa74df62…`、`ediaad/markets/base.py` `2d048d7e…`、`ediaad/markets/custom.py` `80a548f7…`、`tests/test_markets_base.py` `8c26d2b9…`；修改 `ediaad/monitor.py` `6259c366…`、`ediaad/cli.py` `979418c2…`、`tests/test_monitor.py` `3e521d8b…`、`tests/test_scan.py` `54294fae…`、`tests/test_cli_match_monitor.py` `c54292f2…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的已提交、未提交、新增檔案：上述九個檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`data`／`features`／`similarity`／`scan`／`outlook`／`patterns` 為 TASK-002～009 交付物，本張只**呼叫**未修改（`ediaad/patterns.py` 等雜湊未變）
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-030／AC-037、第 5 節模組表（`ediaad/markets/base.py`、`ediaad/monitor.py` 的 `Instrument`）、第 5 節原則 1（依賴方向）、「資料契約」的 `Instrument`（symbol、interval、source_id、display_name）、「輸入／輸出、驗證與錯誤格式」、「相容性／遷移」（不重建 `ediaad/sources/`）、第 7 節測試策略第 10 列；`docs/architecture/ENGINEERING-REPORT.md` 第 7.1 節（`Source` 介面與廢除全域 `ALLOWED_INTERVALS`）、第 7.2 節（`markets/` 目錄清單）；`docs/workflow/adr/ADR-001.md`；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-030（介面與 registry 機制） | `ediaad/markets/base.py`、`ediaad/markets/custom.py`、`ediaad/monitor.py`；`tests/test_markets_base.py` 33 個案例 | 符合 | A-1、A-2（設計決定待追認） |
| AC-037 | `ediaad/markets/custom.py`（`CsvSource.fetch`）；同檔 12 個案例 | 符合 | — |

逐條核對：

- **AC-030**：`Source` 具備 `id`、`display_name`、`supported_intervals`、`needs_api_key`、`search`、`fetch` 六項（逐項 `hasattr` ＋ 型別斷言）；`all_sources()` 列出已註冊來源並以 id 排序；`get_source` 未註冊時的訊息含查詢 id 與可用 id；**全域 `ALLOWED_INTERVALS` 已廢除**（`assert not hasattr(monitor, "ALLOWED_INTERVALS")`）；設定驗證改查 `get_source(source_id).supported_intervals`，訊息同時指出索引、來源與該來源的可用週期；同一個 `1h` 對 csv 有效、對只支援日線的假來源無效，證明「依來源查詢」而非全域白名單。四個來源的實作與整體斷言屬 TASK-013／014／016／037（本張的邊界已明訂），符合。
- **AC-037**：`CsvSource.fetch` 回傳的 DataFrame 與 `load_csv` 以 `assert_frame_equal` 逐欄相同；五種壞輸入的 `DataFormatError` 訊息與 `load_csv` **逐字相同**；缺檔為 `SourceError`、未指定目錄為 `ConfigError`。符合。

## 品質 Review

- **單一解析路徑（本張最重要的品質決策）**：`CsvSource.fetch` 直接呼叫 `data.load_csv`，`cli._local_cache_fetch` 又改為委派 `CsvSource`，因此「從 CSV 取得序列」全專案只有一條實作。這正是報告 F-001（同一份資料經不同路徑產生不同結構）的結構性防線，而且用「錯誤訊息逐字相同」這種強斷言釘住——若有人日後在來源層另寫一套 `pd.read_csv`，M7 變異證明測試會失敗。
- **依賴方向**：`markets/base` 只依賴 `errors` 與 `pandas`（無 I/O、無網路、無輸出），`monitor` → `markets` 方向正確（SPEC 第 5 節原則 1：`… → errors／data／markets`）。`markets/__init__` 匯入 `custom` 即完成註冊，而 `base` 不反向匯入任何來源，因此沒有循環匯入。
- **`Instrument` 的單一定義**：SPEC 第 5 節同時在 `markets/base.py` 與 `monitor.py` 兩列列出 `Instrument`。本張把它定義在較低層的 `markets/base.py`，`monitor` 以匯入 re-export，並用 `monitor.Instrument is markets.base.Instrument` 的同一性斷言把「只有一個定義」固定下來——兩列清單都成立，且不會出現兩個長得像但不同的型別。
- **錯誤分層**：來源查詢失敗是設定問題（`ConfigError` → exit 2），來源取得失敗是執行期問題（`SourceError` → exit 1）；`get_source` 的訊息一定含查詢 id 與可用 id（M1b 證明這半個訊息有被斷言，M1c 證明型別也有）。
- **registry 的入場驗證**：`register` 在放進 registry **之前**驗證六項成員（`_validate`），因此 registry 內不可能存在半殘來源；九條防禦分支全部有參數化測試指名錯誤成員，並斷言失敗的來源不會進入 registry。這是「設定錯誤越早擋越好」的落實。
- **測試隔離**：registry 是模組層可變狀態，測試以公開的 `register`／`unregister` 成對使用，並在 `finally` 還原；`replace=True` 的測試結尾把真正的 `CsvSource` 註冊回去。沒有測試會因執行順序而失敗（全套連跑兩次結果相同）。
- **變異檢查（10 個變異全數被抓到，另 1 個為等效變異）**：M6 特別值得一提——把週期驗證改回全域 `INTERVAL_ORDER` 會同時打破「日線來源拒收 `1h`」與「csv 接受 `1h`」兩個測試，也就是說 AC-030 的實質要求（不是換個常數名稱，而是真的問來源）被測試守住。
- **既有死碼的清理**：AST 掃描發現 4 處未使用的匯入（`cli.py` 的 `ALLOWED_INTERVALS`、`test_monitor.py` 的 `numpy`／`RunResult`、`test_scan.py` 的 `numpy`、`test_cli_match_monitor.py` 的 `sys`），已全部移除。`cli.py` 的那個匯入本身是 TASK-011 的死碼，正好在本張（廢除該常數）一併消失。
- **測試品質**：AC-030 的關鍵語意以「同一輸入在不同來源有不同結果」的反差斷言固定，而非只驗證錯誤訊息；AC-037 以逐欄相等與逐字相同的錯誤訊息驗證委派，而非只驗證「有丟錯」。未發現問題。
- **可讀性**：`base.py` 的模組 docstring 明確寫出「`INTERVAL_ORDER` 只是排序，不是白名單」，避免後人誤用；`custom.py` 說明空的 `interval` 語意。未發現問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 規格補充 | advisory（需 Spec 追認） | `ediaad/monitor.py`＋`markets/base.py`：`DEFAULT_SOURCE_ID = "csv"`（設定未寫 `source_id` 時使用 csv）是 SPEC 未明訂的新契約 | 於 SPEC 第 5 節「輸入／輸出、驗證與錯誤格式」補一句「`instruments[*].source_id` 選填，未給時使用預設來源 `csv`」；TASK-017 引進 catalog 後應改為由 catalog 決定 | 待追認（本張已以測試固定行為：`test_an_instrument_without_a_source_uses_the_default_source`） |
| A-2 | 介面補充 | advisory | `markets/base.py` 新增 `unregister` 與 `register(..., replace=True)`，SPEC 模組表只列 `register`／`get_source`／`all_sources` | 兩者為測試隔離與 TASK-013／014／016 註冊來源所需；建議在 SPEC 模組表補列 | 待追認（已於 TDD 紀錄載明） |
| A-3 | 既有死碼 | advisory（已修） | `tests/test_scan.py`（TASK-005 交付物）有未使用的 `numpy` 匯入；同類問題另見 `cli.py`／`test_monitor.py`／`test_cli_match_monitor.py` | 已全部移除；後續 Task 若再新增檔案，建議在 Review 時順帶跑一次未使用匯入掃描 | **已修正**：全套 `248 passed`；掃描 `ediaad/` 無發現 |
| A-4 | 週期語意 | advisory | csv 來源宣告 `INTERVAL_ORDER` 全部週期（因為檔名即週期），因此設定中 `interval="1w"` 對 csv 一律合法，即使使用者的檔案其實是日線 | 來源無法得知檔案內容的週期；真正的把關在使用者檔案與 `load_csv` 的時間解析。若日後要改為「檢查實際時間間隔」，需先定義容差規則並變更 Spec | 延後（無現時需求，已記錄） |
| A-5 | 流程紀律 | advisory（非程式） | Cycle 1 的測試第一版寫錯輸入（把未註冊的假來源當成重複 id），造成 1 failed ＋ 1 error；Cycle 3 移除 `Instrument` 類別時殘留裝飾器造成 `TypeError` | 兩者皆由測試立即暴露並修正；教訓已記入 TDD 紀錄（刪除裝飾過的類別時，取代範圍須涵蓋裝飾器） | **已記載**：TDD 紀錄 Cycle 1／Cycle 3 兩節如實記錄 |

## 修正與重審

- 第 1 輪：Spec Review 兩個 AC 符合（AC-030 的四來源齊備屬後續 Task，依本張邊界不計）；品質 Review 無 blocking，A-3 已修正。
- 補測：`_validate` 的 9 條分支與非字串 `source_id`（測試數 31 → 41）；補測後對最終測試檔重跑 10 個變異，全數被抓到。
- 重審：重跑單檔（41 passed）、相關回歸（103 passed）與全套（248 passed）；重讀 `base.py`／`custom.py`／`monitor.py` 的驗證段落，複查「週期只問來源」與「解析只有一條路徑」兩個核心要求。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-030 的介面與 registry 機制、AC-037 逐條符合）
- 品質 Review：passed（無 blocking；A-3 已修正，A-1／A-2／A-4 為待追認或延後的 advisory）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1／A-2（需 Spec 補充，行為已由測試固定）、A-4（需先定義規則並變更 Spec）、A-5（流程記載，非程式）
- 能否標為 done：**可以**
- 限制與未驗證事項：只有 `csv` 一個來源已註冊（其餘三個來源為 TASK-013／014／016）；`Instrument.display_name` 在設定路徑仍為空（由 TASK-017 的 catalog 補）；`CsvSource` 不含快取時效與交易所回退
