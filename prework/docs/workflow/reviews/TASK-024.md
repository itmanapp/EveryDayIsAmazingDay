# TASK-024 Code Review

- task_id：TASK-024
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-web-match sha256:92a48f6f6039b811521ef6b55d0a6491742e0679922f311fa5f8a14c104f241b
- Task／Spec 版本：TASK-024 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含流程抽取的契約比對、`window` 缺陷修正與變異存活者的處理）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `eb91266c080c526e71d396a1137cae89ced033f976520e1b874f3aa301c915d6`（63 個檔案）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `92a48f6f6039b811521ef6b55d0a6491742e0679922f311fa5f8a14c104f241b`（67 個檔案）；本張新增 `ediaad/match.py` `d3f3e4ba…`、`ediaad/web/static/match.js` `f621f0ff…`、`match_page.html` `b82a1fe2…`、`tests/test_web_match.py` `2a90048e…`；修改 `ediaad/cli.py` `23e8152c…`、`ediaad/web/routes.py` `3d45347f…`、`ediaad/web/static/index.html` `3298b747…`、`ediaad/web/static/style.css` `6ed28647…`、`tests/test_cli_match_monitor.py` `32d7c053…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：上述九個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`scan.py`／`outlook.py`／`similarity.py`／`features.py`／`patterns.py`／`data.py`／`markets/*`／`app.py`／`server.py`／`sse_hub.py` 本張只呼叫未修改
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-046、第 5 節 `similarity.rank`／`scan.ScanMatch`／`outlook.OutlookStats` 與 HTTP 錯誤格式、第 5 節依賴方向（`cli`／`web` 為同層，不得互相依賴）、第 6 節可及性；`docs/workflow/tasks/TASK-024.md`（含「若不存在則抽出共用流程，不得複製第二份」）；`docs/architecture/ENGINEERING-REPORT.md` 第 3.2 節 G8、第 4.5 節資料流 A；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-046 | `ediaad/match.py`（`run_match`）、`ediaad/web/routes.py`（`match`）、`ediaad/web/static/match.js`／`match_page.html`；`tests/test_web_match.py` 43 個案例＋`tests/test_cli_match_monitor.py` 的預設值案例 | 符合 | A-1～A-7（advisory） |

逐條核對：

- **AC-046「以表單方式得到 `match` 的結果」**：`POST /api/match` 以表單欄位（`symbol`、`interval`、`window`、`top`、`horizon`、`step`、`overlap`、`start`／`end`）跑完一次歷史回看；回傳的就是 CLI 那份五鍵報表（`sample`／`params`／`data_source`／`matches`／`outlook`），並以「同一組輸入下 API 與 CLI 報表 dict 相等」證明。符合。
- **AC-046「相似片段排行」**：`matches` 與直接呼叫 `scan_similar` 的索引／分數／時間界線逐值相同；分數非遞增、同分以起始索引升冪（並以位元相同的重跑結果固定穩定性）；`len(matches) <= top`。符合。
- **AC-046「後續統計」**：`outlook` 五欄與 `forward_stats` 逐值相同；`samples` 另以「結束索引 + horizon < 序列長度」獨立重算（四個 horizon 值）。符合。
- **AC-046「標示樣本數；`samples == 0` 顯示『無樣本』而非 0%」**：後端 `samples == 0` 時其餘欄位為 `null`；前端 `describeOutlook` 對 `samples == 0` 只輸出「樣本數：0（無樣本，無法提供上漲機率與報酬統計）」，測試斷言該輸出只有一行且**不含 `%`**。符合。

## 品質 Review

- **共用流程是可證的（本張最重要的結構決定）**：`run_match` 是唯一產生報表的地方，CLI 與網頁都只是「讀資料 → 呼叫它 → 呈現」。抽取後 CLI 的 21 個既有測試**未修改即全數通過**，而新測試再以整份 dict 比對兩邊輸出。這比「兩份程式碼看起來一樣」強得多，也直接兌現 TASK-024 的「不得複製第二份流程」。
- **依賴方向正確**：共用流程放在新的 `ediaad/match.py`（`cli`／`web` → `match` → `scan`／`outlook`），而不是讓 `web` 匯入 `cli`（那會讓網頁層拉進 argparse 與 stdout）或把 `outlook` 塞進 `scan`（SPEC 明訂 `outlook` 不匯入 `scan`，反向同樣會耦合）。
- **預設值只有一份**：`DEFAULT_TOP`／`DEFAULT_HORIZON`／`DEFAULT_STEP`／`DEFAULT_OVERLAP` 由 `match.py` 提供，CLI 的 argparse 與網頁端點都用它；兩邊各有一個測試釘住文件上的預設值（10／20／1／0.5）。變異 `C02`（把 CLI 預設改成 99）與 `M09`（把報表裡的 `overlap` 硬寫 0.5）都被抓到。
- **`window` 的語意在網頁層被明確化（測試逼出的真實缺陷）**：核心的 `window < 1` 檢查看的是「範例長度」，而網頁層若把 `window=0` 交給 `frame.iloc[-0:]` 會得到**整份序列**——使用者的參數被安靜改寫。已在 `_body_int` 加上 `minimum` 並在註解說明「這是核心看不到的參數，所以不是重複檢查」。變異 `R12`／`R08`／`R09` 分別證明下限、長度檢查與「取尾端而非頭端」都有測試。
- **時間範圍的語意完整**：閉區間（`>=`／`<=`，界線上的 K 線必須納入）＋ naive 一律視為 UTC（序列契約是 UTC）。測試刻意讓界線落在特定 K 線上，因此「多用一根／少用一根」與「時區解讀錯誤」都無法僥倖通過（`R05`／`R06`／`R04`／`R15` 全數被抓到）。
- **F-002／F-003 沒有退化**：`samples == 0` → `null`（不是 0）；`horizon < 1` 由共用流程擋下（`forward_stats` 對 0 會回一組看似正常、其實每個片段報酬都是 0 的統計）。變異 `M07`（`up_probability` 寫成 0.0）與 `M01`（拿掉 `horizon` 下限）都被抓到。
- **網頁層仍是薄轉接且不重實作**：`routes.match` 只做驗證、取序列、時間篩選、切範例；`match.js` 只做轉型與呈現（測試禁止出現 `scan_similar(`／`forward_stats(`／`rank(`）。`data_source` 來自來源回報的 `attrs`（以假來源注入驗證），不是把 `source_id` 抄一次——這正是系統狀態頁要用的三態（`cache`／`binance`／`cache-stale`）的接縫。
- **不引入新依賴**：後端只用標準庫與既有核心；前端不用框架；`node` 只在測試期使用（`skipif`）。假來源注入沿用既有的 `markets.base.register`／`unregister`，並在 `finally` 移除，不污染其他測試。
- **可及性**：每個控制項都有 `label`、表格有 `caption` 與 `th scope="col"`、狀態用 `aria-live`、錯誤用 `role="alert"`、統計以文字呈現（並註明「這是歷史統計，不是預測」）。符合 SPEC 第 6 節。
- **變異測試的強度**：39 個變異在凍結版全數被抓到。第一階段抓到 1 個真實存活者（`data_source = source_id`，因為假來源的 id 與標示相同而不可區分）並以「id 與標示刻意不同」補強；另有 2 處在跑之前就預判並補強（naive `end` 的時區、忽略來源解析），避免製造假存活者。
- **測試品質**：後端以真實 HTTP 請求觀察 JSON；與 CLI 的比較是整份報表而非抽樣欄位；與核心的比較是逐值；前端以 Node 執行真實檔案；所有資料為合成且離線。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 缺口（沿用 TASK-013 A-1～TASK-023 A-1） | advisory（**需在後續 Task 處理**） | 服務仍不會自己跑監控（`run_once` 沒人呼叫、`Store` 寫入端未接、沒有 `GET/POST /api/watchlist`）；另外非 CSV 來源仍拿不到 `cache_dir`（`_fetch_series` 只把 `app.cache_dir` 傳給 `CsvSource`），因此 `source=binance` 目前不會用到快取 | TASK-025 應完成監控執行緒、`Store` 讀寫、監控清單端點與系統狀態頁，並把各來源的 `cache_dir`／`max_age` 接上（系統狀態頁要顯示 `cache`／`binance`／`cache-stale`，這條接線是前提） | 待辦（已記於 `STATE.md` 待決事項；本張以假來源注入驗證 `attrs` → `data_source` 的管路，不需網路） |
| A-2 | 與 Task 文件的欄位名稱落差 | advisory（需追認） | TASK-024.md 寫「`matches`（排行，含 index／score／feature_distance）」，但 `similarity.Match` 才有 `feature_distance`，`scan.ScanMatch`（TASK-005 的凍結契約）只有 `start_index`／`end_index`／`score`／`time_start`／`time_end`；CLI 報表用的也是後者 | 本張以 **CLI／`ScanMatch` 契約為準**（任務同時要求「與 CLI 同構」且「不得改動 CLI 輸出契約」）。若確實要 `feature_distance`，需在 TASK-005 的 `ScanMatch` 增加欄位並更新 SPEC 第 5 節，屬規格變更 | 已決定並記錄（未動 TASK-005；`matches` 與 CLI 逐值相同） |
| A-3 | SPEC 第 5 節模組表 | advisory（需追認） | 本張新增 `ediaad/match.py`（CLI 與網頁的共用流程），SPEC 模組表尚未列它；先前 TASK-020 的 `ediaad/paths.py` 也在同一張待追認清單上 | 建議在下次 SPEC 修訂（或 TASK-037 的整體驗收）一併補列這兩個模組，維持「模組表 ↔ 實作」一致 | 待追認（已記於 `STATE.md` 待決事項） |
| A-4 | 範例的來源 | advisory | 網頁端點的範例固定是「時間範圍內最後 `window` 根」，不像 CLI 可以另外給一個範例檔；表單欄位（TASK-024.md 列出商品、週期、時間範圍、`window`、`top`、`horizon`）沒有範例區間 | 目前符合任務列出的表單範圍；若要「指定任意範例區間」，需要新的 AC 與表單欄位（`sample_start`／`sample_end`），不應在沒有需求時先加 | 已記錄（有意如此） |
| A-5 | 範例自己必然第一名 | advisory | 因為範例取自序列尾端、而掃描涵蓋整份序列，範例視窗與自己完全相同（分數 1.0）必然入榜；這是任務測試計畫明訂的預期（「完全相同者分數 1.0」） | 這是「回看」而非「預測」的合理行為；若日後要「排除範例本身」，需新增參數與 AC | 已記錄（測試以此為固定點） |
| A-6 | 真實瀏覽器檢查 | advisory（**未執行**） | SPEC 第 7 節要求人工檢查；本環境沒有瀏覽器。表單操作、表格外觀與「樣本數」是否清楚可見仍未目視 | 交付前在 Chrome（Wayland）打開 `/static/match_page.html` 走一次（含 `samples == 0` 的情境） | 待辦（替代驗證已記錄於 TDD） |
| A-7 | 流程記載 | advisory（非程式） | Cycle 1 的第一個測試在 Red 階段以「兩份 404 主體相同」而意外通過；另有一處 `assert lost := …` 語法錯誤與一處測試插入位置錯誤（落在 `@pytest.mark.parametrize` 與函式之間造成 collection error） | 已全部修正並如實記載（determinism 測試補 `status == 200`；語法改寫；測試移到裝飾器之前） | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-046 的四項宣稱逐條符合；品質 Review 無 blocking。
- 依測試回饋修正實作 1 處：`window` 在網頁層必須 `>= 1`（否則 `window=0` 會被安靜解讀成整份序列）。
- 依變異檢查補強測試 1 處（假來源的 `id` 與 `data_source` 標示必須不同）、預判補強 2 處（naive `end` 的 UTC 解讀、來源解析不可被繞過）。
- 移除 `cli.py` 的 `_match_report`／`_validate_match_args`／`_iso` 與隨之失效的匯入（`pandas`／`scan_similar`／`forward_stats`），確保「只有一份流程」。
- 重審：重跑單檔（43 passed）、CLI 契約（22 passed）、兩檔合跑（65 passed）與全套（**753 passed**）、兩個流程驗證器（exit 0），並在凍結版重跑變異矩陣（**39／39 偵測到，0 存活**）；重讀 `match.py`／`routes.match`／`match.js` 複查報表欄位、時間界線、`window` 語意、錯誤訊息與 `data_source` 管路。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-046 的四項宣稱逐條符合）
- 品質 Review：passed（無 blocking；A-1 需在後續 Task 落實，A-2／A-3 需追認，A-4～A-6 已記錄或待人工檢查，A-7 為流程記載）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-025）、A-2（需 SPEC／TASK-005 變更才可能提供 `feature_distance`）、A-3（Spec 補模組表）、A-4／A-5（需新 AC 才擴充）、A-6（交付前人工檢查）、A-7（已記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：真實瀏覽器的表單操作與表格外觀未驗證（已有後端契約、核心逐值比對與純函式證據）；`attachMatchForm` 的 DOM 流程未自動測試；`style.css` 視覺無自動證據；範例固定為範圍內最後 `window` 根且必然以 1.0 入榜；非 CSV 來源的 `cache_dir` 尚未接上（A-1）
