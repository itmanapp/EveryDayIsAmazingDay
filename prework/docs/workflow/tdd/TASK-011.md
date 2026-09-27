# TASK-011 測試紀錄

- task_id：TASK-011
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-cli-match-monitor sha256:3ef139627e2fd953dc1b3b8e1db07b538ca531f193fb3fcea9308e8d7eeedbce
- alternative_reason：無（本張為程式任務，所有外部效果可注入，能以 pytest 完全離線斷言）
- Task／Spec 版本：TASK-011 / SPEC-001 v0.4
- 測試邊界：`match`／`monitor` 皆以 `subprocess` 執行 `.venv/bin/python -m ediaad`，觀察 exit code、stdout／stderr 與輸出檔內容；另有四個「契約層」測試直接呼叫 `cli.main` 與 `cli._local_cache_fetch`（見 Cycle 5），因為端到端路徑會把來源失敗轉成 warning 計數，掩蓋 SPEC 第 5 節的例外映射。`monitor` 的來源以本機快取 CSV 提供，完全離線。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-010 的交付物，全套 **187 passed**（本張完成後為 208 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案（本張新增）

| 檔案 | sha256（前 8 碼） |
| --- | --- |
| `ediaad/cli.py` | `672ace72` |
| `ediaad/__main__.py` | `5a437844` |
| `tests/test_cli_match_monitor.py` | `f3e68536` |

## Cycle 1：`match` 報表契約（AC-027、AC-028，真實 Red → Green）

- 測試：`match` 寫出的報表恰好五個頂層鍵（`sample`／`params`／`data_source`／`matches`／`outlook`）、`outlook` 的五個欄位、標準輸出為單行摘要且必須出現五個鍵的代表值，共 3 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_cli_match_monitor.py -q` | 2 | `ModuleNotFoundError: No module named 'ediaad.cli'`（整檔 collection error） | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `3 passed` | snap-2026-09-24-ocaievo-cli-match-monitor／2026-09-24 |

- 最小實作：`build_parser`／`main`／`_run_match`／`_write_json_atomically`；視窗由 `len(sample)` 推導（樣本長度即視窗），報表以 `sort_keys=True`、`ensure_ascii=False` 原子寫入（先寫同目錄暫存檔再 `replace`，不可寫時不留半寫檔）。

## Cycle 2：輸入驗證與 exit code 分層（AC-028，真實 Red → Green）

- 測試：`--top 0`／`--horizon 0`／`--horizon -1`／`--step 0`／`--overlap 1.5` 各自 exit 2 且不留下報表；不存在的資料檔 exit 2；不存在的樣本檔 exit 2；報表目錄不可寫 exit 1 且不留任何暫存檔，共 7 個（4 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 2 | 同上（`ModuleNotFoundError`） | 同上／2026-09-24 |
| Green | 同上 | 0 | `9 passed` | 同上／2026-09-24 |

- 實作：`_validate_match_args`（`horizon ≥ 1`、`top ≥ 1`、`step ≥ 1`、`0 ≤ overlap ≤ 1`）、`main` 的例外映射（`DataFormatError`／`ConfigError` → 2、`SourceError` → 1、`KeyboardInterrupt` → 0）。

## Cycle 3：`monitor` 子命令（AC-022～AC-026 的 CLI 面，**無 Red**）

- 測試：`--once` 印出摘要並 exit 0、事件檔恰好一行；壞設定 exit 2；來源不可用 exit 1；常駐模式收到 SIGINT 後 exit 0、無 traceback、印出 `[STOP]`，共 4 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | — | — | **未取得**（見下） | — |
| Green | `.venv/bin/python -m pytest tests/test_cli_match_monitor.py -q` | 0 | `13 passed` | 同上／2026-09-24 |

- **如實記載的流程偏差**：本 Cycle 的 `_run_monitor` 實作與測試在同一次操作中完成，因此**沒有捕捉到 Red**。這是違反「先紅後綠」的流程瑕疵，不是實作瑕疵；補救方式是不以 Cycle 的 Red 作為本 Cycle 的辨識力證據，改以下列兩項外部證據替代：
  1. **整檔 Red**：移除 `ediaad/cli.py` 後 `tests/test_cli_match_monitor.py` 直接 collection error（`ModuleNotFoundError: No module named 'ediaad.cli'`），證明這 20 個測試確實綁在實作上，而非恆真斷言。
  2. **變異檢查**：Cycle 5 的 6 個變異全數被抓到（見下），其中 M4b 專打本 Cycle 的跨輪去重。
- 實作：`_run_monitor`（`--once` 走 `run_once`，`processed == 0 and warnings > 0` 時回傳 `EXIT_RUNTIME_ERROR`；常駐走 `run_forever` 並共用一份 `AlertState`）、`_local_cache_fetch`（讀 `<cache_dir>/<symbol>_<interval>.csv`，缺檔丟 `SourceError`）。

## Cycle 4：AC-029 的規模門檻與行為一致性（**無 Red**）

- 測試（2 個）：
  1. `test_match_at_ac_029_scale_meets_the_time_budget`：**依 AC-029 的刺激條件**取 10,000 根、樣本 60 根（視窗 60）、`--top 20 --horizon 10`，斷言耗時 < 60 秒；並斷言報表五鍵、`matches` 恰好 20 筆、分數皆在 `[0,1]` 且由高到低、每筆都是完整 60 根視窗、**任兩筆重疊比例 ≤ 0.5**（重疊抑制在規模下仍成立）、第一名是植入索引 50 且分數 `approx(1.0)`。
  2. `test_match_behaves_identically_on_a_larger_series`：同一份 12 根樣本分別對 200 根與 10,000 根跑 `--top 1`，斷言 `matches`／`outlook`／`sample` **逐欄完全相同**——這是 AC-029「結果與小資料集的行為一致」的強形式。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | — | — | **不適用**：AC-029 是既有實作的效能量測與不變性檢查，實作已完成，測試首次執行即通過 | — |
| Green | `.venv/bin/python -m pytest tests/test_cli_match_monitor.py -q -s` | 0 | `21 passed in 16.32s`；`[AC-029] 10,000 根、視窗 60、top 20 耗時 3.86 秒` | 同上／2026-09-24 |

- 為何無 Red：本 Cycle 驗的是「已實作行為在規模下的表現與不變性」，屬量測性質；辨識力由「20 筆命中的排序、視窗長度與兩兩重疊比例」及「大小資料集報表逐欄相同」承擔——若掃描視窗、重疊抑制、排序或正規化在規模下改變，這些斷言就會失敗（變異 M2 即以此被抓到）。
- **修正過程（如實記載）**：本 Cycle 第一版把刺激條件寫成視窗 12、top 1，與 AC-029 明訂的「視窗 60、top 20」不符（top 1 也讓 `matches` 與 `outlook` 的逐欄相等過於容易成立）。已改為 AC 明訂的參數，並把「逐欄一致」拆到 top 1 的另一個測試；夾具 `build_series_frame`／`prepare_match_inputs` 因此新增 `range_bars`／`name` 參數（預設值不變，既有測試不受影響）。

## Cycle 5（補測）：變異檢查暴露 4 個覆蓋缺口，全數補上

**首次變異檢查有 4 個存活者**，全部是測試覆蓋不足，而非實作缺陷（這正是變異檢查的用途）：

| 存活變異 | 為何存活（根因） | 補上的測試 |
| --- | --- | --- |
| `SourceError` → `EXIT_INPUT_ERROR`（錯誤分層） | 端到端 `monitor` 的 exit 1 來自 `_run_monitor` 的 `processed == 0 and warnings > 0` 計數器**直接 return**，不經過 `main` 的例外映射，所以映射表本身無人測 | `test_main_maps_errors_to_the_documented_exit_codes`（3 個參數化，以 monkeypatch 的 stub 直接觸發三種例外） |
| `_local_cache_fetch` 缺檔改丟 `ConfigError` | 同上：`run_once` 把 `fetch` 的例外收成 warning，端到端只看到「有 warning → 1」，看不出例外型別 | `test_local_cache_fetch_raises_source_error_when_the_cache_is_missing`（`pytest.raises(SourceError)`；三個例外皆為 `EdiaadError` 的直接子類，可精準區分） |
| `horizon` 門檻放寬為 `< 0` | 參數化只涵蓋 `--horizon -1`，**沒有 `--horizon 0`** | 新增 `pytest.param(["--horizon", "0"], id="horizon 為 0")` |
| 每輪重建 `AlertState` | 常駐測試只斷言 `[ALERT]` 出現、exit 0，**沒有斷言不重複** | 常駐測試改為等 2.5 秒（輪詢間隔 1 秒 → 至少 2 輪），並斷言 `[ALERT]` 行數與事件檔行數都**恰好為 1** |

**第五個缺口（由變異 M4a 揭露）**：`run_forever(state=...)` 的 `state` 參數從未被測——TASK-010 只覆蓋 `run_once(state=...)`（「忽略傳入 state」的變異因此存活）。補上：

- `test_run_forever_honours_a_caller_supplied_alert_state`：先以 `run_once` 讓傳入的 `state` 標記事件，再以同一 `state` 呼叫 `run_forever` 三輪（注入 `sleep`／`should_stop`），斷言事件仍只發一次。這是 TASK-011（第一個 `run_forever(state=...)` 的呼叫端）應負責釘住的契約。

補測後測試數 14 → 20；Cycle 4 改寫時把原本 1 個效能測試拆為 2 個（規模門檻／逐欄一致），最終為 **21 個**。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red（補測，非 Cycle 的紅） | `.venv/bin/python -m pytest tests/test_cli_match_monitor.py -q` 搭配逐項變異 | 1 | 6 個變異逐一 `pytest exit=1` | 同上／2026-09-24 |
| Green | 同上 | 0 | `21 passed in 16.74s` | 同上／2026-09-24 |

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | `main` 的 `except SourceError` 回傳 `EXIT_INPUT_ERROR`（1→2） | 被抓到：`test_main_maps_errors_to_the_documented_exit_codes[SourceError→1]` |
| M2 | `window = len(sample)` → `len(sample) + 1` | 被抓到：報表與摘要的視窗／命中索引斷言，以及 AC-029 的「每筆命中皆為 60 根視窗」與重疊比例斷言 |
| M3 | `_validate_match_args` 的 `horizon < 1` → `< 0` | 被抓到：`test_match_exits_two_for_invalid_parameters[horizon 為 0]` |
| M4a | `shared_state = state if state is not None else AlertState()` → `AlertState()`（忽略呼叫端 state） | 被抓到：`test_run_forever_honours_a_caller_supplied_alert_state` |
| M4b | 把 `run_once(..., state=shared_state)` 改為每輪 `state=AlertState()` | 被抓到：常駐測試的「恰好一次告警／恰好一行事件」 |
| M5 | `_local_cache_fetch` 缺檔改丟 `ConfigError` | 被抓到：`test_local_cache_fetch_raises_source_error_when_the_cache_is_missing` 與來源不可用的 exit 1 |

工具紀律：變異字串一律「以換行開頭、整行比對」並要求 `count(frm) == 1` 才執行，避免先前「4 空格字串是 8 空格字串的子字串」與「改到 docstring」兩類誤判。每次變異後立即還原，並比對檔案 sha256。還原後 `ediaad/cli.py` `672ace72`、`ediaad/__main__.py` `5a437844`、`ediaad/monitor.py` `72df2ba2` 與變異前一致，全套 `208 passed`。上表為**對最終版測試檔**（`f3e68536`）重跑的結果，6 個變異全數被抓到。

**M4a 的註記**：最初的 M4 寫成「`shared_state` 改建為 `AlertState()`」時存活，我一度判斷為等效變異；細看後確認它**不是**等效——`shared_state` 仍在迴圈外建立一次，跨輪去重不受影響，但「呼叫端傳入的 state 被丟棄」是實質行為改變，只是當時沒有任何測試釘住該契約。因此把變異拆為 M4a（忽略傳入 state）與 M4b（每輪重建），兩者現皆被抓到。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_cli_match_monitor.py -q` | 0（`21 passed in 16.97s`） | snap-2026-09-24-ocaievo-cli-match-monitor |
| 相關回歸（掃描＋統計＋偵測＋監控＋CLI） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_scan.py tests/test_outlook.py tests/test_patterns_detect.py tests/test_monitor.py tests/test_cli_match_monitor.py -q` | 0（`105 passed in 17.09s`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`208 passed in 17.87s`） | 同上 |
| 整檔 Red（移除實作） | `ocaievo/`：移除 `ediaad/cli.py` 後 `.venv/bin/python -m pytest tests/test_cli_match_monitor.py -q` | 2（`ModuleNotFoundError: No module named 'ediaad.cli'`） | 同上 |
| 變異後還原驗證 | 同本張單檔 | 0（`21 passed`），三個交付檔雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- **流程偏差（如實記載）**：
  1. Cycle 3 的實作先於測試，未取得 per-Cycle Red。已以「整檔 Red」與「變異檢查 6／6 全數擊殺」兩項證據補強，並在本紀錄明示，不掩蓋。
  2. Cycle 4 改寫時，我以「標記字串之後全部取代」的腳本修改測試檔，意外截掉尾端 5 個 Cycle 5 契約測試（測試數由 20 掉到 16）。由於改寫後立刻看到 `16 passed` 而察覺，隨即依原文補回並重跑（21 passed），此錯誤未進入任何已驗證狀態。教訓：改檔一律用精確片段取代，不用「截斷後重寫」。
- 已知邊界（記錄）：
  - `_local_cache_fetch` 是本張的**暫時**來源，只讀本機快取檔；完整來源鏈（快取 → 交易所 → 過期快取）屬 TASK-013 之後。因此本張的 exit 1 語意只覆蓋「本機快取缺失」一途。
  - `monitor` 的常駐模式目前無停止條件以外的排程語意（每輪固定 `sleep(poll_interval_seconds)`）；服務生命週期與背景執行屬後續 Task。
  - `ALLOWED_INTERVALS` 仍是模組常數（TASK-012 改為依來源查詢 `supported_intervals`）。
  - AC-029 的 60 秒門檻在本機以 4.02 秒通過；此為單機量測，非跨平台保證。
- 未涵蓋：真實網路來源（TASK-013～）、SQLite 落地與跨程序去重（TASK-018）、設定檔原子寫入（TASK-019）、通知管道（TASK-027）、`serve` 子命令與網頁（TASK-031 之後）。

## 版本標記的可重現性說明

本張起明確固定 `checked_version` 的「原始碼樹」計算方式（先前的紀錄未載明，無法從現在的樹重現，見下）：

```bash
cd ocaievo
find . -type f -not -path "./.venv/*" -not -path "./.cache/*" \
  -not -path "./.pytest_cache/*" -not -path "*/__pycache__/*" \
  | sort | xargs sha256sum | sha256sum
```

即「排除 `.gitignore` 所列產物後的檔案清單逐檔 sha256，再對整份清單取 sha256」，TASK-011 為 25 檔。**已知瑕疵**：TASK-001～TASK-010 的樹雜湊標籤以不同（未記載的）方式算出，本次以六種候選方法（相對／`./` 路徑、逐檔雜湊／串接內容、含／不含 `.cache`）都無法重現 TASK-009 與 TASK-010 的既有值；那些標籤應視為歷史標記而非可重算的校驗值。可重算的部分是逐檔 sha256（例如 `ediaad/monitor.py` `72df2ba2…` 與 TASK-010 紀錄一致，本次亦逐一比對過）。`docs/workflow/PROJECT.md` 已同步記載此慣例。
