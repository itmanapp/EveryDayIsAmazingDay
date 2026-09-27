# TASK-017 Code Review

- task_id：TASK-017
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-catalog sha256:bd49d41006475ccf8e0d8313fb8f9a425f0f9cc036bac8ceaa34dac371302428
- Task／Spec 版本：TASK-017 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含狀態容器介面與 `_combine` 的設計追認、變異字串過期的處理）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `bd49d41006475ccf8e0d8313fb8f9a425f0f9cc036bac8ceaa34dac371302428`；本張新增 `ediaad/markets/catalog.py` `0b2aa3ad…`、`tests/test_markets_catalog.py` `ab2cdbf4…`；修改 `ediaad/markets/__init__.py` `da15bd6e…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的已提交、未提交、新增檔案：上述三個檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`base`／`custom`／`crypto`／`twse`／`us`／`adjust`／`calendar`（TASK-012～016 交付物）本張只新增匯出，未修改其邏輯（`base.py` `526d04ed…`、`us.py` `df80b096…` 等均未變）
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-038、第 5 節模組表與資料契約（`Catalog` 的 `catalog_version`／`sources`／`instruments`）、產物位置（`$EDIAAD_HOME/catalog.json`）、「外部依賴與失敗處理」（更新服務失敗靜默、用快取）、第 6 節品質需求（可靠性：設定與 catalog 以原子寫入避免半寫狀態）、第 8 節 Q-011；`docs/architecture/ENGINEERING-REPORT.md` 第 7.2 節、第 6.5 節（manifest 的 `catalog_version`／`catalog_url` 與六條約束）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-038 | `ediaad/markets/catalog.py`（`Catalog`／`load_catalog`／`save_catalog`／`catalog_version`／`update_catalog`）；`tests/test_markets_catalog.py` 44 個案例 | 符合 | A-1、A-2、A-3（advisory） |

逐條核對：

- **AC-038「版本較新時下載並原子取代本地快取」**：`test_a_newer_remote_version_is_downloaded_and_replaces_the_local_file` 斷言狀態 `updated`、請求 1 次、`catalog_version(path)` 變成新版、目錄內只有 `catalog.json`（不留暫存檔）；原子性由 `save_catalog` 的「同目錄暫存檔 ＋ `os.replace`」承擔，並以「目錄不可寫時原檔位元不變且仍可載入」證明失敗不會留下半寫狀態。符合。
- **AC-038「版本相同不重複下載」**：manifest 提供版本時請求次數為 **0** 且本地檔位元不變；manifest 未提供版本時則下載一次比對，若相同**仍不重寫**本地檔。兩種情境都有斷言（變異 M1／M3 分別證明這兩條路徑有被守住）。符合。
- **AC-038「下載失敗時保留原檔並記錄狀態」**：三種傳輸失敗 ＋ 五種內容不合法 ＋ 目錄不可寫，共九種失敗情境都斷言 `status == "failed"`、**位元不變**、原檔仍可 `load_catalog`、不留暫存檔，並在訊息與狀態容器留下說明。符合。
- **AC-038「`Catalog` 含 `catalog_version`、`sources`、`instruments` 三項」**：三項都有，且 `save_catalog` 寫出的 JSON 只有這三個頂層鍵（有斷言）。符合。
- **AC-038「`load_catalog`／`save_catalog` 可往返還原同一份內容」**：`restored == original` 的完整相等斷言（含 `Instrument` 的 `source_id`／`display_name`）。符合。

## 品質 Review

- **原子寫入與「失敗不留痕」是本張的可靠性核心**：`save_catalog` 以同目錄暫存檔 ＋ `os.replace` 寫入，失敗時清除暫存檔；`update_catalog` 的所有失敗路徑都**先驗證再取代**，因此本地檔永遠處於「要嘛舊版完整、要嘛新版完整」的狀態。這對應 SPEC 第 6 節「設定與 catalog 以原子寫入避免半寫狀態」。九種失敗情境全部以位元組比對斷言（變異 M10／M17 證明）。
- **「版本相同不請求」需要 manifest 的版本，這是設計而非取巧**：報告第 6.5 節的 manifest 同時提供 `catalog_version` 與 `catalog_url`，因此呼叫端能在下載前判斷。`update_catalog` 的 `remote_version` 選填參數把這個能力顯式化：給了就不請求，沒給才下載比對（此時 `requests == 1` 是預期的，並在 TDD 紀錄說明）。若把 `remote_version` 拿掉，AC-038 的「版本相同不重複下載」就只能在「下載後才知道相同」的意義上成立——那不符合更新檢查「不得阻塞主要流程」的精神。
- **失敗回報狀態而非丟例外**：更新檢查是背景維護，依「外部依賴與失敗處理」表的「失敗靜默、用快取」，它不能讓服務失敗。因此 `update_catalog` 的所有遠端與寫入失敗都轉成 `UpdateResult(status="failed")`，並可寫進呼叫端提供的狀態容器。唯一的例外是**呼叫端自己給錯 manifest 版本格式**（`DataFormatError`）——那是程式錯誤，應該立刻知道，而且不會發出請求（有斷言）。
- **`instruments` 重用 `markets.base.Instrument`**：catalog 因此成為「哪個商品該問哪個來源」的權威對照——`source_id` 就在商品上。這一點直接連到 TASK-013 以來反覆記錄的跨 Task 缺口（見 A-1）：解它所需要的資料結構現在已經存在。
- **嚴格解析、明確錯誤**：`load_catalog` 擋未知鍵（頂層與每個商品／來源），與 `monitor.load_config` 的既有風格一致——伺服器端 payload 的欄位打錯會立刻被發現，而不是被靜默忽略。缺檔與內容不合法都用 `DataFormatError`，與 `data.load_csv` 的既有慣例一致（本機檔案問題 → exit 2）。
- **`Catalog.__post_init__` 就驗證版本格式**：`YYYY-MM-DD` 的驗證放在建構時，因此不可能存在一個版本格式錯誤的 `Catalog` 實例；`update_catalog` 與 `_is_newer` 因此可以放心用 `dt.date.fromisoformat` 比較（比較規則因此是「日期先後」而不是字串順序——`2026-10-01` 與 `2026-9-1` 的差異被格式驗證排除）。變異 M12 證明格式驗證有被測試。
- **由狀態空間檢查發現的缺口（非變異檢查）**：原本「本地檔損毀」與「下載失敗」同時發生時，訊息只提到下載失敗。已補 `_combine` 讓兩者都出現，並補測試。這是本張唯一在 Review 階段新增的實作調整。
- **工具陷阱的處理（如實記載）**：修改訊息字串後，M5／M6 的變異字串變成 `count == 0`，腳本把它們列為 `SURVIVORS`。我沒有接受這個結論，而是回查輸出確認是 `[SKIP]`（字串已不符），刷新字串後兩者都被抓到。**變異工具把「沒套用」與「沒偵測到」列在同一個欄位是它自己的缺陷**，我已经在每次執行時逐行檢視輸出，而不是只看 SUMMARY。
- **測試品質**：所有失敗路徑都同時斷言「狀態」「位元不變」「原檔仍可載入」「不留暫存檔」四件事；`state` 容器同時驗證「被更新」與「其他鍵不被清掉」；版本比較的邊界（相同／較新／較舊）在三條不同意義的路徑上都有案例（manifest 相同、manifest 較舊、下載後相同、下載後較舊）。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 缺口（沿用 TASK-013 A-1／014 A-3／015 A-1／016 A-1） | advisory（**需在後續 Task 處理**） | `Catalog`／`load_catalog`／`update_catalog` 目前**沒有呼叫端**；`monitor.load_config` 仍不知道商品的來源，`cli._local_cache_fetch` 固定用 csv。catalog 是解這條缺口的權威對照，但接線尚未發生 | 把「catalog → 商品來源對照 ＋ 來源分派 ＋ 市場別預設 ＋ 日曆套用 ＋ 除權息還原 ＋ 金鑰狀態 ＋ catalog 狀態」一起編入 TASK-025（或 TASK-037 整合項），並更新其「預計觸及的檔案」 | 待辦（已記於 `STATE.md` 待決事項） |
| A-2 | 介面補充 | advisory（需追認） | `update_catalog(..., state=None)` 的狀態容器形狀（`state["catalog"] = {status, version, message}`）是 SPEC 未定義的新契約；`UpdateResult` 與五種 `status` 值亦然 | 於 SPEC 第 5 節補上 `UpdateResult` 與狀態容器的形狀；TASK-025／032 應以它為顯示與排程的依據 | 待追認（行為已由測試固定） |
| A-3 | 逾時與排程 | advisory | 本張是同步函式，逾時只由預設客戶端的 `HTTP_TIMEOUT = 5.0` 承擔；六條架構約束（不阻塞啟動與輪詢、去抖動、可完全關閉）不在本張 | TASK-032 以本張的 `update_catalog` 為基礎實作排程與約束，並加上「不阻塞」的測試 | 待辦（TASK-032） |
| A-4 | 未驗證的真實 manifest | advisory | 真實更新服務未對接（Q-011 假設無 Cloudflare 帳號），manifest 欄位名依報告第 6.5 節 | TASK-034 建立端點後，以真實 manifest 做一次端到端驗證 | 待辦（TASK-034） |
| A-5 | 流程紀律 | advisory（非程式） | `update_catalog` 在 Cycle 1 就一次寫成，Cycle 2 無真實 Red（已用 stub 綁定證據補強）；變異字串因後續修改而過期，一度被誤列為存活 | 已全部在 TDD 紀錄如實記載。下一張起若同一模組含多個獨立行為，先在 Cycle 1 把未測函式留成 stub | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-038 逐條符合；品質 Review 無 blocking。
- 由狀態空間檢查新增 1 處實作調整（`_combine`：本地損毀與下載失敗同時發生時兩者都報告）與對應測試。
- 移除 2 個未使用的匯入（`field`／`SourceError`），並在最終版檔案上重跑變異矩陣（18／18 全數被抓到）。
- 重審：重跑單檔（44 passed）、相關回歸（105 passed）與全套（519 passed）；重讀 `catalog.py` 複查版本比較的三條路徑、失敗時的四項保證、原子寫入與狀態容器。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-038 的四項宣稱逐條符合）
- 品質 Review：passed（無 blocking；A-1 需在後續 Task 落實，A-2 需追認，其餘為延後或已記錄）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-025／037 的整合範圍）、A-2（需 Spec 補充）、A-3（TASK-032）、A-4（TASK-034）、A-5（流程記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：不做排程與六條架構約束；不做端點；未與真實更新服務對接；`UpdateResult`／狀態容器為本張定義的介面；catalog 尚無消費端
