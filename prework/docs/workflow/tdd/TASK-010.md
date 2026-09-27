# TASK-010 測試紀錄

- task_id：TASK-010
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-monitor sha256:9916447ac2b5ee5952ec372e470005f4dde834718a905474213e0c26bc3cf376
- alternative_reason：無（五個 Cycle 中有四個有真實 Red）
- Task／Spec 版本：TASK-010 / SPEC-001 v0.4
- 測試邊界：只呼叫 `load_config`／`run_once`／`run_forever`／`format_alert`／`append_event`／`event_times`，並觀察 `Watchlist`／`RunResult`、`emit` 的內容、`warn` 的訊息與事件檔內容；`fetch`／`emit`／`warn`／`sleep`／`should_stop`／`now` 全部以測試替身注入。離線可跑。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-009 的交付物，全套 **162 passed**（本張完成後為 187 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## Cycle 1：設定載入與驗證（AC-022，真實 Red → Green）

- 測試：合法設定回傳 `Watchlist`、明確 `pattern_spec`、缺鍵、未知鍵、型別錯、`instruments` 為空、不支援週期（訊息含 `instruments[0]`）、`pattern_spec.pattern_id` 與頂層不一致、`ALLOWED_INTERVALS` 契約，共 9 個。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_monitor.py -q` | 2 | `ModuleNotFoundError: No module named 'ediaad.monitor'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `9 passed in 0.32s` | snap-2026-09-24-ocaievo-monitor／2026-09-24 |

- 最小實作：`Instrument`／`Watchlist`／`AlertState`／`RunResult` 與 `load_config`（缺鍵／未知鍵／型別／空陣列／週期／`pattern_spec` 身分一致；訊息指出鍵名或 `instruments[i].interval`）。其餘公開函式先以 `NotImplementedError` 佔位，讓後續 Cycle 有真實 Red。

## Cycle 2：三輪輪詢的去重（AC-023，真實 Red → Green）

- 夾具：`build_series_with_pattern(offset)` 在指定位置植入完整結構（前置深谷界定盤整起點）；測試以同一份序列跑兩輪、再以 `offset=40` 的新事件跑第三輪。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `3 failed`：`NotImplementedError`（`event_times`／`run_once`／`format_alert`） | 同上／2026-09-24 |
| Green | 同上 | 0 | `12 passed in 0.31s` | 同上／2026-09-24 |

- 實作：`event_times`（由事件取起訖時間）、`format_alert`（**`run_once` 的必要前置**，故一併於本 Cycle 實作）、`run_once`（取得 → 偵測 → 去重 → 統計 → 輸出）、`run_forever`。
- 去重鍵 = `(symbol, interval, pattern_id, 事件開始時間的 ISO 字串)`；測試直接斷言 `state.seen` 的內容與 `emit` payload 的 `event_start_time`。
- **本 Cycle 同時完成 TASK-006 的 A-4 待辦**：`run_once` 以真實 `PatternEvent` 呼叫 `forward_stats(..., end_attr="recovery_index")`，該整合路徑（F-002 的修法）現在有端到端測試覆蓋，不再只有測試替身。

## Cycle 3：錯誤隔離與程式錯誤上拋（AC-024，真實 Red → Green）

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `2 failed`：`SourceError` 與 `KeyError`（畸形資料框架）皆直接外洩 | 同上／2026-09-24 |
| Green | 同上 | 0 | `15 passed in 0.33s` | 同上／2026-09-24 |

- 實作：把「評估階段」（取得資料 → 偵測 → 去重 → 統計）包在 `except (EdiaadError, KeyError, IndexError)`，失敗只記 warning 並繼續下一個商品；`ValueError` 這類程式錯誤**不攔截**，向上拋出（有測試）。
- **計數不變式的設計**：把「評估」與「輸出」分開——先在同一輪把所有待發提醒放進 `pending`，評估成功才 `processed += 1`，再輸出。因此失敗的商品既不算 `processed` 也不算 `alerted`，`processed + warnings == 商品數` 在失敗情境下成立（測試斷言此式）。`state.mark_alerted` 也只在真正輸出時呼叫，避免「評估失敗卻已被標記為提醒過」。

## Cycle 4：資料不足與「無命中」的區分（AC-025，真實 Red → Green）

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `2 failed`：短序列被判為 `processed=2, skipped=0`（正是 F-003 的混淆） | 同上／2026-09-24 |
| Green | 同上 | 0 | `19 passed in 0.35s` | 同上／2026-09-24 |

- 實作：在 `detect` **之前**檢查 `len(series) < range_bars_min + 1`，不足時 `warn`（訊息含「資料不足」）並 `skipped += 1`、`warnings += 1`、`continue`。若直接呼叫 `detect`，它只會回傳空清單，「無法評估」與「評估後沒中」就無法區分。
- 對照組：長度足夠但無命中 → `processed == 1`、`skipped == 0`；長度**恰好等於** `range_bars_min + 1` → 必須被評估（邊界）。

## Cycle 5：提醒輸出格式與 JSONL 附加寫入（AC-026，真實 Red → Green）

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `3 failed`：`append_event` 的 `NotImplementedError`×2，以及**我的斷言寫錯**（見下） | 同上／2026-09-24 |
| Green | 同上 | 0 | `24 passed in 0.34s` | 同上／2026-09-24 |

- 實作：`append_event` 以 `open("a")` 附加寫入、自動建立父目錄、欄位以 `sort_keys=True` 輸出、缺欄位時先丟 `ConfigError`（不寫入半殘的一行）。
- 如實記載的測試錯誤：`test_run_once_payload_carries_all_nine_event_fields` 原本斷言 `history_samples == 0`，實際為 **1**——事件在序列中段（recovery 索引 23、horizon 3、共 80 根），後續走勢足夠。**是我的斷言錯，不是實作錯**；已修正為 1 並補上 `history_up_probability is not None`。

## 補測：`run_forever` 抓到真實缺陷

- 追加 `test_run_forever_loops_until_should_stop`（注入 `should_stop` 與 `sleep`），**首次執行即失敗**：`run_forever` 每一輪都把 `state=None` 傳給 `run_once`，使每輪各自建立新的 `AlertState` → **同一事件每輪都會重新提醒**，去重形同無效。
- **修正**：迴圈開始前建立（或沿用）一份 `shared_state`，整輪共用。
- 這是一般測試容易漏掉的路徑（`run_once` 的測試都自己傳入共用的 state，因此看不到這個缺陷）。

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 移除去重檢查 | 被抓到：`test_three_rounds_alert_once_zero_once_...`、`test_run_forever_loops_until_should_stop` |
| M2 | 去重鍵改用**事件結束**時間 | 被抓到：`test_dedup_key_is_symbol_interval_pattern_and_event_start_time` |
| M3 | 移除「資料不足」檢查 | 被抓到：`test_insufficient_data_is_skipped_with_a_warning` 等 3 個 |
| M4 | 例外攔截放寬為 `except Exception` | 被抓到：`test_programming_errors_are_not_swallowed` |
| M5 | `append_event` 改為覆寫模式（`"w"`） | 被抓到：`test_append_event_never_rewrites_existing_lines` 等 2 個 |
| M6 | `format_alert` 欄位順序調換 | 被抓到：兩個 `format_alert` 測試 |

M2 與 M6 第一次因替換字串不精確而未套用（工具已改為要求 `count(frm) == 1` 才執行）；修正字串後兩者都被抓到。還原後 `ediaad/monitor.py` 雜湊 `72df2ba238c5c2f74eb4343f66082e85b207a5df07daae79147a8d77a2cf338e` 與變異前一致，全套 `187 passed`。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_monitor.py -q` | 0（`25 passed`） | snap-2026-09-24-ocaievo-monitor |
| 相關回歸（統計＋偵測＋監控） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_outlook.py tests/test_patterns_detect.py tests/test_monitor.py -q` | 0（`66 passed`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`187 passed in 1.31s`） | 同上 |
| 變異後還原驗證 | 同上 | 0（`187 passed`），檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 已知邊界（記錄）：`Instrument` 本張只實作 `symbol`／`interval`；SPEC 第 5 節另列 `source_id`／`display_name`，將於 TASK-012（多來源 registry）補上——報告第 3.1 節 F10 的設定範例也只含 `symbol`／`interval`。`ALLOWED_INTERVALS` 目前是模組常數，TASK-012 改為依來源查詢 `supported_intervals`。
- 未涵蓋：CLI 子命令與 exit code（TASK-011）；SQLite 落地與跨程序去重（TASK-018，本張為記憶體內）；設定檔原子寫入（TASK-019）；通知管道（TASK-027）。
- `run_once` 新增了選用參數 `now`（注入時鐘），用於事件檔的 `detected_at`；未注入時預設 `pd.Timestamp.now(tz="UTC")`。這是為了讓「外部效果可注入」與測試可重現（SPEC 第 5 節原則 2），已在 review 標明。
