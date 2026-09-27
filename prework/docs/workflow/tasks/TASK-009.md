# TASK-009：由範例學習規律參數

- id：TASK-009
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-021"]
- depends_on：["TASK-008"]
- test_evidence：["docs/workflow/tdd/TASK-009.md"]
- review_evidence：["docs/workflow/reviews/TASK-009.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`ediaad.patterns.learn(sample)` 對一段至少 12 根的數值範例推估出可用的 `PatternSpec`：以真實區間的滾動中位數為尺，依門檻階梯 (1.0, 1.5, 2.0, 3.0, 4.0, 6.0) 倍由嚴到鬆取第一個能找到合法盤整區間的門檻，再用與 `detect` 相同的二分搜尋取最長區間；跌破相位取盤整區間之後的最低點（未低於區間下緣即無法推估）、回歸相位取跌破之後第一根收盤回到區間均值（找不到即無法推估）；把實測相對量放寬成容差區間（`range_bars_min = round(實際根數 × 0.5)`、`range_bars_max = round(實際根數 × 1.5)`、`band_atr_multiple_max = clip(實際 band / ATR × 1.2, 1.0, 6.0)`、`breakdown_depth_band_min = max(0.05, 實際深度 × 0.7)`、`breakdown_depth_band_max = min(3.0, 實際深度 × 1.3)`、`recovery_bars_max = 實際回歸根數 + 2`）；推估結果落在容差內、以該規格 `detect` 能命中範例自身、同一範例重跑結果完全相同、無法推估時丟出 `ConfigError` 且不回傳隨意參數。
- 本張不做：不改動 `atr` 與 `detect` 的行為（TASK-008）；不做網頁「學習」頁與 CSV 貼上／上傳（TASK-023；本張輸入為已載入的序列，CSV 解析沿用 TASK-002 的 `load_csv`）；不做模型訓練、不做隨機搜尋或最佳化（報告第 5.7 節：沒有隨機性、沒有權重）；不做監控設定檔；不讀寫檔案、不連網、不輸出訊息。
- 每個 AC 在本張負責的範圍：AC-021 全部（推估規格落在容差內、用該規格 `detect` 能命中自己的範例、範例無法推估時丟出 `ConfigError` 且不回傳隨意參數、同一範例重跑結果完全相同）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-021、第 5 節模組表中 `ediaad/patterns.py` 一列的 `learn`、第 5 節「輸入／輸出、驗證與錯誤格式」原則、第 6 節「可重現性」（同一輸入位元相同、不使用隨機）、第 8 節風險 3（單一範例學習可能過擬合 → 容差朝「更容易命中範例」放寬）、第 7 節測試策略第 6 列；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F9、第 4.3 節 `patterns.py`、第 4.5 節資料流 C、第 5.7 節（長度至少 12 根、門檻階梯、跌破與回歸的判定、六條容差公式、為何用滾動中位數而非平均 ATR）、第 5.5 節（與 `detect` 共用的二分搜尋）；`docs/workflow/CONTEXT.md`「範例學習（learn）」（不是模型訓練）。
- 模組與公開介面：於 `ediaad/patterns.py` 擴充（不新增檔案）公開 `learn(sample) -> PatternSpec`；內部可共用 TASK-008 已建立的 ATR／二分搜尋輔助邏輯，但不得複製出第二套判定門檻。失敗一律以 `ediaad/errors.py` 的 `ConfigError` 回報，且不得在建構 `PatternSpec` 前就先放寬到無意義的門檻（推估不出來就報錯，不回傳隨意參數）。
- 預計觸及的檔案：`ediaad/patterns.py`（在 TASK-007／TASK-008 已建立的檔案上擴充）、`tests/test_patterns_learn.py`；實作前重新查證（不得破壞 `PatternSpec` 契約與 `detect` 既有行為）。
- 必要環境／依賴：TASK-001 的 `.venv`（`numpy`、`pandas`、`pytest`）；測試資料為依已知參數合成的三段式範例序列（至少 12 根，另備一段約 30 根的完整三相位範例），離線可跑，不需網路。

## 測試計畫

- 測試公開邊界：只呼叫 `ediaad.patterns.learn`，再把回傳的 `PatternSpec` 交給 `ediaad.patterns.detect` 與 `ediaad.patterns.to_json` 觀察結果；不檢視門檻階梯或二分搜尋的內部變數。
- 第一個失敗行為與預期斷言：`learn` 尚未存在時，於專案根執行 `.venv/bin/python -m pytest tests/test_patterns_learn.py -q` 預期以 `AttributeError` 失敗（`module 'ediaad.patterns' has no attribute 'learn'`）；實作後第一個綠燈斷言為「以已知參數合成的範例呼叫 `learn` 後，`len(detect(sample, spec)) >= 1`，且該筆事件的四個相位索引等於植入位置」。
- 後續例外／邊界情境：範例長度 11（少於 12 根）→ `pytest.raises(ConfigError)`；範例全平坦、跌破相位未低於盤整區間下緣 → `ConfigError`；有跌破但收盤始終未回到區間均值 → `ConfigError`；三個失敗情境都要斷言「呼叫未取得任何 `PatternSpec`」且訊息指出無法推估的原因（不得回傳隨意參數）；容差公式以手算值斷言（`range_bars_min`／`range_bars_max` 為實際根數的 0.5／1.5 倍四捨五入、`band_atr_multiple_max` 被 `clip` 在 1.0～6.0、`breakdown_depth_band_min` 下限 0.05 且 `breakdown_depth_band_max` 上限 3.0、`recovery_bars_max` 為實際回歸根數 + 2）；確定性——同一範例連續兩次 `to_json(learn(sample))` 字串完全相同（無隨機）；推估出的規格 `detect` 自己的範例時，斷言命中事件的盤整區間覆蓋植入的盤整相位。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_patterns_learn.py -q`；相關回歸為專案根執行 `.venv/bin/python -m pytest tests/test_patterns_spec.py tests/test_patterns_detect.py tests/test_patterns_learn.py -q` 與全套 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的執行指令表。
- 非程式任務的替代驗證與理由：不適用（本張為程式任務，推估結果與容差都能以合成 oracle 精確斷言，無需替代驗證）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-008 的交付物（全套 150 passed）；本次在 `ediaad/patterns.py` 擴充 `learn`，並新增 `tests/test_patterns_learn.py`（開工時以 `find . -type f -not -path "./.venv/*" | sort` 與逐檔 sha256 建立快照；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（預計 `docs/workflow/tdd/TASK-009.md`）
- Review 紀錄位置：見上方 review_evidence（預計 `docs/workflow/reviews/TASK-009.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-patterns-learn` sha256:d03c1cf328f8d9b6710be4f7b5593ec4fbb440155119f70c3877d94c70d7119a（原始碼樹）；本張交付 `ediaad/patterns.py` `0e771abd…`、`tests/test_patterns_learn.py` `327ed652…`；全套 `162 passed`
- 取消、重開或變更原因：無
