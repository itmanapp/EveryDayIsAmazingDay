# TASK-024 測試紀錄

- task_id：TASK-024
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-web-match sha256:92a48f6f6039b811521ef6b55d0a6491742e0679922f311fa5f8a14c104f241b
- alternative_reason：**部分替代**——表單操作與結果表格的外觀無法在無瀏覽器自動化的環境驗證；本張以「Node 載入真實 `match.js` 驗證純函式（表單轉型、列格式化、樣本數文字）」＋「後端與 CLI 報表逐值相同」作為替代，Chrome（Wayland）的人工檢查仍**未執行**（見「未執行或受阻」）。
- Task／Spec 版本：TASK-024 / SPEC-001 v0.4
- 測試邊界：（1）`POST /api/match` 的 JSON、狀態碼與「與 CLI `match` 報表**同一份**」；（2）與核心 `scan_similar`／`forward_stats` 逐值一致；（3）`match.js` 的純函式以 Node 載入真實檔案驗證；（4）靜態頁面接線。全部離線（假來源注入，無網路）。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-023 的交付物，全套 **709 passed**（本張完成後為 **753 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `eb91266c080c526e71d396a1137cae89ced033f976520e1b874f3aa301c915d6`（63 個檔案）。
- TDD 不適用的理由與替代驗證（若有）：見「未執行或受阻」第 1 點。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/match.py` | `d3f3e4ba` | 新增：`run_match`（掃描 → 統計 → 五鍵報表）與 `iso`；`DEFAULT_TOP`／`DEFAULT_HORIZON`／`DEFAULT_STEP`／`DEFAULT_OVERLAP` 的單一來源 |
| `ediaad/cli.py` | `23e8152c` | 修改：`_match_report`／`_validate_match_args`／`_iso` 移除，改呼叫 `match.run_match`；argparse 預設改用共用常數（移除 `pandas`／`scan_similar`／`forward_stats` 匯入） |
| `ediaad/web/routes.py` | `3d45347f` | 修改：`POST /api/match`、`MATCH_BODY_KEYS`、`_body_int`（含 `minimum`）／`_body_number`／`_body_time`／`_filter_by_time` |
| `ediaad/web/static/match.js` | `f621f0ff` | 新增：`buildMatchBody`／`matchRows`／`describeOutlook`／`describeResult`／`describeError`／`attachMatchForm` |
| `ediaad/web/static/match_page.html` | `b82a1fe2` | 新增：表單、結果表格、統計區、狀態與錯誤區 |
| `ediaad/web/static/index.html` | `3298b747` | 修改：「分析頁面」加入歷史回看連結 |
| `ediaad/web/static/style.css` | `6ed28647` | 修改：表格與統計樣式 |
| `tests/test_web_match.py` | `2a90048e` | 新增：43 個測試（含 9 個 Node 純函式斷言與 1 個假來源注入） |
| `tests/test_cli_match_monitor.py` | `32d7c053` | 修改：新增「省略參數時的預設值」1 個測試（22 個） |

## Cycle 1：`POST /api/match` 與共用流程（AC-046，真實 Red → Green）

- 測試（29 個）：完全相同者 `matches[0]["score"] == 1.0` 且 `len(matches) <= top`；範例本身（範圍內最後 `window` 根）必在 1.0 那一群；**整份報表與 CLI `match` 逐值相同**（同一組輸入：API 的 JSON 與 CLI 寫出的 `report.json` 以 dict 相等比較，含五個頂層鍵）；分數非遞增且同分以起始索引升冪；同一輸入兩次回應位元相同；`matches` 與直接呼叫 `scan_similar` 的索引／分數／時間界線逐值相同；`top`／`step`／`overlap`／`horizon` 真的傳到核心（與同一組參數的核心呼叫相同）；表單的數字字串可被接受且結果與數字相同；`outlook.samples` 以「結束索引 + horizon < 序列長度」獨立重算（四個 horizon 值），且樣本 > 0 時五個統計值與 `forward_stats` 逐值相同；`samples == 0` 時其餘欄位為 `null`；`start`／`end` 篩選序列（閉區間：界線上的 K 線必須被納入；不帶時區一律視為 UTC）；`data_source` 來自來源回報的 `attrs`（以假來源注入，且 id 與標示刻意不同）；省略參數時套用文件上的預設值；`limit` 生效；不合法輸入各回 400 並指出欄位名（`window` 0／負數／非整數／小數／超過序列長度、`top`、`horizon`、`step`、`overlap` 的界、`start > end`、無法解析的時間、缺 `symbol`／`interval`／`window`、未知欄位、`limit` 超上限、未知來源、主體非物件／沒有主體）；所有錯誤都不含 `Traceback`。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_web_match.py -q` | 1 | `27 failed, 2 passed in 18.58s`：端點不存在（404） | 尚未有端點／2026-09-24 |
| Green | 同上 | 0 | `29 passed in 18.85s` | snap-2026-09-24-ocaievo-web-match／2026-09-24 |

- 實作：`ediaad/match.py` 的 `run_match`（把 TASK-011 原本寫在 `cli._match_report` 的流程抽出來，CLI 與網頁**共用同一份**）；`routes.match`（薄轉接：驗證 → 取序列 → 時間篩選 → 切範例 → `run_match`）。
- **「與 CLI 同構」是可證的，不是宣稱**：`run_match` 是唯一產生報表的地方，測試再以同一組輸入比較兩邊的完整 dict。CLI 的既有 21 個測試在抽取後**未修改即全數通過**（`report` 內容與 exit code 語意不變），這是「沒有複製第二份流程、也沒有改動 CLI 契約」的直接證據。
- **`window` 的語意被測試逼出一個真實缺陷**：第一版把 `window` 交給核心檢查，但核心只收到「範例」（`len(sample)`），而 `window=0` 在網頁層會讓 `frame.iloc[-0:]` 等於**整份序列**——使用者的參數被安靜改寫成 240。已改為在網頁層驗證 `window >= 1`（`_body_int(..., minimum=1)`），並在註解說明為什麼這不是與核心重複的檢查。
- **時間範圍是閉區間且不帶時區視為 UTC**：兩個邊界都有效（`>=`／`<=`），naive 時間以 `tz_localize("UTC")` 解讀（序列契約是 UTC）。兩者都有專門測試，且測試刻意讓界線落在特定 K 線上，讓「多用一根／少用一根」與「時區解讀錯誤」都無法僥倖通過。
- **F-002／F-003 的既有語意在這裡沒有退化**：`samples == 0` 時五個統計欄位是 `null`（不是 0），前端顯示「無樣本」；`horizon < 1` 由共用流程擋下（`forward_stats` 對 0 會回一組看似正常但無意義的統計——每個片段報酬恰好 0）。
- **如實記載的測試錯誤**：第一版的第一個測試用 `assert lost := [...]`（`SyntaxError`，需要括號）；`top=5` 時「範例自己」不一定進得了排行（週期性背景會產生多個 1.0，依索引升冪排序，範例是最後一個）→ 該斷言改用 `top=60`，而「`matches[0].score == 1.0`」仍以預設 `top` 驗證。`test_match_is_deterministic` 在 Red 階段因為兩份 404 錯誤主體相同而「通過」→ 已補 `status == 200` 斷言，避免它以錯誤的形式綠燈。

## Cycle 2：前端歷史回看頁（AC-046，真實 Red → Green）

- 測試（14 個）：`/static/match.js` 與 `/static/match_page.html` 以正確的 `Content-Type` 提供且含各自端點／標記；首頁連到回看頁；**前端不得重實作引擎**（`match.js` 不得出現 `scan_similar(`／`forward_stats(`／`rank(`／`Math.exp`）；以 Node 載入真實檔案驗證：表單值轉成正確型別的主體（留空欄位不送，由後端套預設）、七種不合法值都丟出**指出欄位名**的錯誤（含 `window` 缺漏）、列格式化（分數固定四位小數）、統計文字（樣本數、機率與報酬百分比；`samples == 0` 時**只有一行**「樣本數：0（無樣本，無法提供…）」且不得出現 `%`）、摘要文字與錯誤訊息（後端訊息原樣呈現）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `3 failed, 30 passed, 5 errors in 21.78s`：兩個靜態檔 404、首頁未接線、Node 讀不到檔案 | 同上／2026-09-24 |
| Green | 同上 | 0 | `38 passed in 21.81s` | 同上／2026-09-24 |

- 實作：`match.js`（純函式 ＋ `attachMatchForm` 黏著層，載入時不碰 DOM，因此可在 Node 裡載入）；`match_page.html`（表單、表格、統計、狀態與錯誤區，全部以文字表達）；`index.html` 的「分析頁面」；`style.css`。
- **與 TASK-022／TASK-023 同一種可測性手法**：可判斷的部分（轉型、格式化、樣本數文字）都是純函式並以 Node 驗證；留在瀏覽器裡的只有送出表單與把結果畫進表格。

## 變異測試（兩階段：先殺存活者，再跑凍結版）

- 工具：`/tmp/mutate_task024.py`（整行替換、`count(frm) == 1` 才套用、每輪逾時 180 秒、跑完立即還原並比對 sha256、`flock` 確保單一行程）。
- 矩陣：**39 個變異**（`match.py` 12、`routes.py` 15、`cli.py` 2、`match.js` 10），涵蓋 `horizon` 下限、`window` 的來源與下限、報表五個鍵的每個欄位（含 `data_source` 與三個統計值）、`iso` 的格式、`window >= 1`／數值界／整數解析、時間界線的兩個方向、`start > end`、`window > len(frame)`、範例取尾端還是頭端、來源解析、時區解讀、未知欄位、CLI 的參數傳遞與預設值、前端轉型／界／格式化／樣本數文字。
- **第一階段抓到 1 個真實存活者並補強測試擊殺**：`R10`（`data_source = source_id`）存活——我注入的假來源 `id` 恰好等於它回報的 `data_source`（都是 `fake-cache`），於是「抄 id」與「讀 attrs」不可區分。已把假來源的 `id` 改為 `fake-source`、標示維持 `fake-cache`，並斷言兩者不同（`M05` 硬寫 `"csv"` 也一併被抓到）。
- 另外兩處**在跑之前**就補強，避免製造假存活者：`tz_localize("Asia/Taipei")` 若只驗 naive `start` 不會被發現（範例取自尾端，起點偏移不影響結果）→ 測試改用 naive **`end`** 並讓它必須等於特定 K 線；`_fetch_series(app, DEFAULT_SOURCE_ID, …)`（忽略來源解析）→ 由假來源測試涵蓋。兩者都已加入矩陣（`R14`／`R15`）。
- **判讀為等價、因此未列入矩陣的一處**：`_filter_by_time` 與範例的 `reset_index(drop=True)` 在目前的下游不可觀測——`scan_similar` 用 `times.iloc[start]`、`forward_stats` 用 `to_numpy()`、`features.extract_matrix` 用 `series.iloc[...]`，全部是位置存取（已以 grep 確認無 `.loc`）。保留它們是為了讓「回報索引對應篩選後序列」的不變量在型別層面成立；把它拿掉是等價變異，不是測試缺口。
- **最終凍結版結果：39／39 全數偵測到（0 存活、0 無效）**，逐輪輸出形如 `41 passed, 2 failed`（43 個測試）。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `.venv/bin/python -m pytest tests/test_cli_match_monitor.py -q`（抽取後、未改測試） | 0 | `21 passed in 17.80s`（CLI 契約不變） |
| `.venv/bin/python -m pytest tests/test_cli_match_monitor.py tests/test_web_match.py -q` | 0 | `65 passed in 44.39s` |
| `.venv/bin/python -m pytest -q` | 0 | `753 passed, 2 warnings in 111.75s` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |

## 未執行或受阻

1. **Chrome（Wayland）人工檢查未執行**（無瀏覽器自動化）：表單操作、結果表格外觀與「樣本數」是否清楚可見。替代驗證：後端契約以真實 HTTP 請求自動驗證（含 `samples == 0` → `null`），前端以 Node 驗證純函式（含「無樣本」文字只有一行且不含 `%`），頁面接線以內容斷言。仍待交付前在真實瀏覽器完成一次。
2. **`attachMatchForm` 的實際 DOM 流程未自動測試**（需要瀏覽器或 DOM 模擬器；本專案不引入新依賴）。
3. **`style.css` 的視覺效果無自動證據**（無畫面快照機制）。
