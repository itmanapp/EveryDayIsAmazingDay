# TASK-008：ATR 與規律偵測器（相位、反例、去重、尺度不變）

- id：TASK-008
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-016","AC-017","AC-018","AC-019","AC-020"]
- depends_on：["TASK-007"]
- test_evidence：["docs/workflow/tdd/TASK-008.md"]
- review_evidence：["docs/workflow/reviews/TASK-008.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`ediaad.patterns.atr(series, period)` 依 `previous_close[0] = close[0]`、`TR[i] = max(high[i]-low[i], |high[i]-previous_close[i]|, |low[i]-previous_close[i]|)` 計算真實區間，前 `period - 1` 個為 NaN、之後為 rolling 平均，且每個索引只使用當下（含）以前的資料（把植入點之後的資料乘 10，`ATR[range_end]` 差異小於 1e-12）；`ediaad.patterns.detect(series, spec)` 依 SPEC 第 5.5 節六條定義回傳 `PatternEvent` 清單（`pattern_id`、`range_start_index`、`range_end_index`、`breakdown_index`、`recovery_index`、`confidence`、`band`、`breakdown_depth`、`recovery_bars`），四個相位索引與 `band`、`breakdown_depth`、`recovery_bars` 符合第 5.5 節定義、`confidence` 落在 [0, 1]；四種反例（跌破深度不足、深度超過上限、回歸前出現更低低點、回歸逾時）皆回傳空清單；整段乘 0.01／0.5／1000 或加常數平移後命中事件的四個索引完全相同；同一段結構被多個長度命中時只保留最長的一次，結果依盤整相位長度由長到短排序。
- 本張不做：不實作 `learn`（TASK-009）；不做 `load_config`／`run_once`／提醒與去重（TASK-010）；不改動 `PatternSpec` 的欄位、驗證與序列化契約（TASK-007）；不做相似度路線（`features`／`similarity`／`scan`）；不讀寫檔案、不連網、不輸出訊息；不做 CLI；不新增 SPEC 未定義的第七條判定條件或額外門檻。
- 每個 AC 在本張負責的範圍：AC-016 全部（前 13 個 NaN、之後與手算 rolling 平均相符、不引用未來）；AC-017 全部（四個相位索引與 `band`、`breakdown_depth`、`recovery_bars`、`confidence` 值域）；AC-018 全部（四種反例零命中）；AC-019 全部（乘常數與平移後四個索引不變）；AC-020 全部（同結構只留最長、依盤整相位長度由長到短排序）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-016～AC-020、第 5 節模組表中 `ediaad/patterns.py` 一列（`atr`、`detect`）、第 5 節「PatternEvent」資料契約、第 5 節原則 1 與 3、第 6 節「效能」（`detect` 於 1,000 根 2 秒內）與「可重現性」、第 7 節測試策略第 6 列；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F8、第 4.3 節 `patterns.py`、第 4.4 節「PatternEvent」、第 5.4 節（ATR 公式、`cumsum` 滾動平均、「不引用未來」是硬性要求）、第 5.5 節（六條判定條件完整定義、二分搜尋找最長合法區間、取最長區間而非最緊區間對測試夾具的影響）、第 5.6 節（信心值三項平均的公式）、第 5.9 節（去重鍵用時間而非索引的理由）；`docs/workflow/CONTEXT.md`「ATR」「區間帶寬（band）」「相位（phase）」「規律事件（PatternEvent）」「信心值（confidence）」「尺度不變」。
- 模組與公開介面：於 `ediaad/patterns.py` 擴充（不新增檔案）公開 `PatternEvent`（資料類別，九個欄位依 SPEC 第 5 節順序）、`atr(series, period) -> pandas.Series`（前 `period - 1` 為 NaN）、`detect(series, spec) -> list[PatternEvent]`。`atr` 以 `numpy.cumsum` 實作 O(1) 滾動平均；`detect` 對每個 `j` 以二分搜尋求最小合法起始 `i`（`band` 對 `i` 單調不減），信心值依第 5.6 節公式計算並 `clip` 到 [0, 1]；模組不得匯入 `monitor`、`scan`、`config`，也不得讀寫檔案或輸出訊息。
- 預計觸及的檔案：`ediaad/patterns.py`（在 TASK-007 已建立的檔案上擴充）、`tests/test_patterns_detect.py`；實作前重新查證（`docs/workflow/PROJECT.md` 的單檔測試範例即為 `tests/test_patterns_detect.py`；重用 TASK-002 的 `ediaad/errors.py` 與 Series 契約）。
- 必要環境／依賴：TASK-001 的 `.venv`（`numpy`、`pandas`、`pytest`）；測試資料為依已知參數植入三相位的合成序列（含 `PatternSpec` 的預設與改寫版本），離線可跑，不需網路；效能要求（1,000 根 2 秒內）可在同一測試檔以寬鬆上限斷言，避免不穩定的嚴格計時。

## 測試計畫

- 測試公開邊界：只呼叫 `ediaad.patterns.atr` 與 `ediaad.patterns.detect` 並觀察回傳值（`pandas.Series`、`list[PatternEvent]` 的欄位與索引）；合成序列以 `ediaad.data.from_rows` 或等價的 Series 建立；不檢視二分搜尋或累積和的內部狀態。
- 第一個失敗行為與預期斷言：`atr` 尚未存在時，於專案根執行 `.venv/bin/python -m pytest tests/test_patterns_detect.py -q` 預期以 `AttributeError` 失敗（`module 'ediaad.patterns' has no attribute 'atr'`）；實作後第一個綠燈斷言為「週期 14 的 ATR 前 13 個值皆為 NaN（`pandas.isna(...).all()`），第 14 個值與手算 rolling 平均以 `pytest.approx` 相符」。
- 後續例外／邊界情境：ATR 的 `period=1` 時每個索引都有值且等於當根 TR；不引用未來——把植入點之後的資料乘 10，斷言 `ATR[range_end]` 差異小於 1e-12；門檻恰好相等的方向性——`band == band_atr_multiple_max × ATR[j]` 需成立（`<=`）、`low[k] == min(low[i..j])` 需不成立（嚴格 `<`）、`depth` 恰好等於 `breakdown_depth_band_min`／`breakdown_depth_band_max` 需成立（閉區間），並以四種反例情境斷言 `detect(...) == []`（深度不足、深度超過上限、回歸前出現更低低點、回歸逾時）；`confidence` 以 `0.0 <= e.confidence <= 1.0` 斷言，且 `band_score` 在 `band` 遠小於上限時接近 1；去重——同一段結構被多個長度命中時斷言只留一筆且其盤整長度最大；排序——多筆命中時斷言 `[e.range_end_index - e.range_start_index + 1 for e in events]` 由大到小；尺度不變——整段乘 0.01／0.5／1000 與加常數平移後斷言 `[(e.range_start_index, e.range_end_index, e.breakdown_index, e.recovery_index) for e in events]` 與原序列完全相同；序列過短（長度小於 `range_bars_min + 1`）時斷言回傳空清單而非丟錯。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_patterns_detect.py -q`；相關回歸為專案根執行 `.venv/bin/python -m pytest tests/test_patterns_spec.py tests/test_patterns_detect.py -q` 與全套 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的執行指令表。
- 非程式任務的替代驗證與理由：不適用（本張為程式任務，相位邊界與反例都能以合成 oracle 精確斷言，無需替代驗證）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-007 的交付物（全套 122 passed）；本次在 `ediaad/patterns.py` 擴充 `atr`／`PatternEvent`／`detect`，並新增 `tests/test_patterns_detect.py`（開工時以 `find . -type f -not -path "./.venv/*" | sort` 與逐檔 sha256 建立快照；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（預計 `docs/workflow/tdd/TASK-008.md`）
- Review 紀錄位置：見上方 review_evidence（預計 `docs/workflow/reviews/TASK-008.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-patterns-detect` sha256:819486e7792c225bfd778b30b71e35f47dc7c59f12704a1f452d9dc721262c94（原始碼樹）；本張交付 `ediaad/patterns.py` `5d5dc091…`、`tests/test_patterns_detect.py` `c98f2e6b…`；全套 `150 passed`
- 取消、重開或變更原因：無
