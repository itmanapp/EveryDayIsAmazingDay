# TASK-010 Code Review

- task_id：TASK-010
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-monitor sha256:9916447ac2b5ee5952ec372e470005f4dde834718a905474213e0c26bc3cf376
- Task／Spec 版本：TASK-010 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 `run_forever` 的 blocking 修正）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `9916447ac2b5ee5952ec372e470005f4dde834718a905474213e0c26bc3cf376`；本張交付的兩個檔案——`ediaad/monitor.py` `72df2ba238c5c2f74eb4343f66082e85b207a5df07daae79147a8d77a2cf338e`、`tests/test_monitor.py` `256999916e5bbf70156d4f92a84763917d37160c59e224df1a80ec40daa9eebe`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對；本張新增 `ediaad/monitor.py` 與 `tests/test_monitor.py`，未修改其他模組
- 納入的已提交、未提交、新增檔案：`ediaad/monitor.py`、`tests/test_monitor.py`＋ 本張 TDD／Review 紀錄
- 排除的既有修改及理由：`outlook`／`patterns`／`scan` 等屬 TASK-002～009 交付物，本張只**呼叫**未修改
- 程式規範來源：`docs/workflow/SPEC.md` 第 5 節（`monitor.py` 責任與公開 API、原則 2「外部效果可注入」、原則 3「錯誤分層」）、第 4 節 AC-022～AC-026、報告第 3.1 節 F10～F12、第 4.1 節原則 2／3、第 5.9 節（提醒去重）、第 8.3 節 F-002／F-003、`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-022 | `ediaad/monitor.py`（`load_config`、`Instrument`／`Watchlist`）；`tests/test_monitor.py` 9 個案例 | 符合 | — |
| AC-023 | `ediaad/monitor.py`（`event_times`、`run_once` 去重、`AlertState`）；同檔 3 個案例 | 符合 | B-2（`run_forever`，已修正） |
| AC-024 | `ediaad/monitor.py`（`run_once` 的 `except (EdiaadError, KeyError, IndexError)` 與 `pending` 兩段式）；同檔 3 個案例 | 符合 | — |
| AC-025 | `ediaad/monitor.py`（`minimum_bars` 檢查）；同檔 4 個案例 | 符合 | — |
| AC-026 | `ediaad/monitor.py`（`format_alert`、`append_event`）；同檔 5 個案例 | 符合 | — |

逐條核對：

- **AC-022**：合法設定回傳 `Watchlist`；五種壞設定（缺鍵、未知鍵、型別錯、`instruments` 為空、週期不合法）各自 `ConfigError` 且訊息含出錯鍵名或 `instruments[0].interval`；`pattern_spec` 與頂層 `pattern_id` 不一致時 `ConfigError`；`pattern_spec` 經 `from_json` 嚴格還原（缺／多／型別錯皆擋）。符合。
- **AC-023**：三輪的 `alerted` 為 `[1, 0, 1]`；去重鍵以 `state.seen` 的實際內容斷言為 `(symbol, interval, pattern_id, 事件開始時間 ISO)`。符合。
- **AC-024**：單一商品 `SourceError` → 另一商品仍 `emit`、`warnings == 1`、`processed + warnings == 商品數`；畸形資料框架（缺 `close` 的 `KeyError`）同樣只記 warning；`ValueError` 向上拋出。符合。
- **AC-025**：長度不足 → `skipped == 1` + 「資料不足」warning 且不呼叫 `detect`；長度足夠但無命中 → `processed == 1`、`skipped == 0`；長度**恰好**為 `range_bars_min + 1` → 必須被評估。符合。
- **AC-026**：`format_alert` 為單行、欄位順序與報告 F12 一致（以完整字串相等斷言）、無樣本時 `history_up_prob=-`；`append_event` 三次附加後三行皆可解析、九欄位齊全、第一行逐字不變、父目錄自動建立。符合。

## 品質 Review

- **B-2（blocking，已修正）——`run_forever` 每輪建立新的去重狀態**：`run_forever` 原本把 `state=state` 傳給 `run_once`，而未指定 `state` 時該值為 `None`，於是**每一輪都建立新的 `AlertState`**，同一事件每輪都會重新提醒——去重形同無效。這是監控迴圈最核心的保證，屬 blocking。
  **修正**：迴圈開始前建立（或沿用呼叫端提供的）`shared_state`，整輪共用。
  **值得記錄**：`run_once` 的所有測試都自行傳入共用的 `state`，因此完全看不到這個缺陷；是**額外補寫的 `run_forever` 測試**（注入 `should_stop`／`sleep` 觀察兩輪行為）才抓到。這說明「公開 API 中的每個入口都要有自己的測試」，即使它只是薄薄一層。
- **`pending` 兩段式設計（本張最重要的品質決策）**：把「評估」與「輸出」分開，讓
  1. 失敗的商品既不算 `processed` 也不算 `alerted`，維持 `processed + warnings == 商品數`；
  2. `state.mark_alerted` 只在真正要輸出時呼叫，不會出現「評估途中失敗卻已被標記為提醒過」而永久漏報的情形。
  這是 F-003（「無法得到結果」與「沒有結果」必須區分）在監控層的落實。
- **錯誤分層**：只攔截 `(EdiaadError, KeyError, IndexError)`；`ValueError`／`OSError` 等程式或環境錯誤向上拋出（有測試，且變異 M4 證明測試有效）。訊息前綴帶商品與週期，便於系統狀態頁呈現（TASK-025）。
- **去重鍵與時鐘**：鍵用**事件開始時間**（不是索引），符合報告第 5.9 節；`detected_at` 由注入的 `now` 產生（預設 `pd.Timestamp.now(tz="UTC")`），讓事件檔內容在測試中完全可重現。
- **模組責任與依賴**：只依賴 `errors`／`outlook`／`patterns` 與 pandas；未匯入 `cli`／`web`／`store`；除了 `append_event` 寫入事件檔（這是它的職責）之外不做其他 I/O。符合 SPEC 第 5 節原則 1 與依賴方向。
- **測試品質**：五個 AC 各有正例、反例與邊界（長度邊界、恰好時限、欄位順序、附加不覆寫）；`emit`／`warn` 以 `Recorder` 收集後斷言內容而非只數次數；變異 M1～M6 全部被抓到。未發現問題。
- **命名與可讀性**：模組 docstring 開頭就寫明三條設計原則與 F-003 的教訓；`pending` 的變數名與註解說明兩段式的原因。未發現問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| B-2 | 正確性 | **blocking** | `ediaad/monitor.py` `run_forever`：未共用 `AlertState`，每輪都新建 → 同一事件每輪重複提醒。觸發情境：任何使用 `run_forever` 的常駐監控 | 迴圈外建立 `shared_state` 並傳入每一輪 | **已修正並驗證**：`72df2ba2…`；辨識測試 `test_run_forever_loops_until_should_stop`；全套 `187 passed` |
| A-1 | 簽名補充 | advisory | `run_once`／`run_forever` 新增選用參數 `now`（注入時鐘），未列在 TASK-010 的介面描述中 | 事件檔的 `detected_at` 需要時鐘，且 SPEC 第 5 節原則 2 要求外部效果可注入；預設值維持 `pd.Timestamp.now(tz="UTC")`，不改變未注入時的行為 | 已實作並於 TDD 紀錄標明 |
| A-2 | 契約完整性 | advisory（待補） | `Instrument` 目前只有 `symbol`／`interval`；SPEC 第 5 節另列 `source_id`／`display_name` | TASK-012 引入多來源 registry 時補上；報告 F10 的設定範例亦只含 symbol／interval | 待辦（已記於 TDD 紀錄） |
| A-3 | 全域常數 | advisory | `ALLOWED_INTERVALS` 目前是模組常數，與報告第 7.1 節「廢除全域常數、改依來源查詢」相衝 | TASK-012 改為 `get_source(source_id).supported_intervals`，設定驗證改查 registry | 待辦（TASK-012 的 AC-030） |
| A-4 | 去重持久性 | advisory（已知限制） | `AlertState` 只在記憶體，程式重啟後同一事件會再提醒一次 | 報告第 8.2 節已列為已知限制；TASK-018 改為 SQLite 落地 | 待辦（交付報告將再列） |
| A-5 | 訊息內容 | advisory | `warn` 的失敗訊息含例外型別與內容，未結構化 | 目前供人類閱讀；TASK-025 的系統狀態頁需要結構化資料時再擴充 | 延後（無現時需求） |

## 修正與重審

- 第 1 輪：Spec Review 符合；品質 Review 找到 B-2（blocking，`run_forever` 的去重狀態）並修正。
- 另修正一個**測試**錯誤：`test_run_once_payload_carries_all_nine_event_fields` 原本斷言 `history_samples == 0`，實際為 1（事件位於序列中段）。已修正斷言而非放寬實作。
- 重審：重跑單檔（25 passed）、相關回歸（統計＋偵測＋監控 66 passed）與全套（187 passed）；重讀 `monitor.py` 複查驗證順序、`pending` 兩段式、例外範圍與輸出格式。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-022～AC-026 逐條符合）
- 品質 Review：passed（B-2 已修正並重驗；無其他 blocking）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-2／A-3（TASK-012 的多來源重構）、A-4（報告已揭露的 v0.2 限制）、A-5（無現時需求）
- 能否標為 done：**可以**
- 限制與未驗證事項：`AlertState` 僅記憶體內；`Instrument` 尚未含來源欄位；`ALLOWED_INTERVALS` 仍為全域常數
