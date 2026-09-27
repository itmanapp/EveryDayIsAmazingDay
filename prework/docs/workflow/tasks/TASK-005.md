# TASK-005：滑動視窗掃描與重疊抑制

- id：TASK-005
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-010","AC-011"]
- depends_on：["TASK-004"]
- test_evidence：["docs/workflow/tdd/TASK-005.md"]
- review_evidence：["docs/workflow/reviews/TASK-005.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`ediaad.scan.scan_similar(series, sample, window, top, step=1, overlap=0.5)` 依 `features.extract_matrix` 抽出候選特徵、以 `similarity.rank` 取得分數排序後，依分數順序貪婪接受互不衝突者，回傳不超過 `top` 筆的 `ScanMatch` 清單（`start_index`、`end_index`、`score`、`time_start`、`time_end`），每筆寬度為 `window`（`end_index == start_index + window - 1`）；重疊比例 `max(0, min(e1,e2) - max(s1,s2) + 1) / window` 嚴格大於 `overlap` 者被丟棄，因此重疊 60% 的兩段只留高分那筆，而重疊恰好 50% 的兩段都保留；四種壞參數各自丟出 `ConfigError` 並指出不合法處。
- 本張不做：不做特徵抽取與距離計算的實作（TASK-003／TASK-004，本張只呼叫）；不做後續走勢統計（TASK-006）；不做 `detect`（TASK-008）；不讀寫檔案、不連網、不輸出訊息；不做 CLI 報表與 `report.json`（TASK-011）；不做全域最佳化（報告第 5.3 節刻意採貪婪）。
- 每個 AC 在本張負責的範圍：AC-010 全部（結果寬度等於 window、筆數不超過 top、重疊 60% 只留高分、恰好 50% 兩筆都保留）；AC-011 全部（範例長度不等於 W、序列短於 W、`top` 或 `step` 或 `overlap` 不合法、序列缺 `time` 欄位四類的 `ConfigError` 與訊息）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-010～AC-011、第 5 節模組表中 `ediaad/scan.py` 一列（`ScanMatch`、`scan_similar`）、第 5 節「其他結構」的 `ScanMatch` 欄位、第 5 節原則 1 與 3、第 7 節測試策略第 4 列；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F5、第 4.3 節 `scan.py`、第 5.3 節（七步流程、重疊公式、嚴格大於的邊界定義、貪婪取捨、`(M, 10)` 的效能設計）、第 4.5 節資料流 A；`docs/workflow/CONTEXT.md`「重疊抑制」（預設 50%、恰好等於門檻者保留，且與「提醒去重」不同）。
- 模組與公開介面：新增 `ediaad/scan.py`，公開 `ScanMatch`（資料類別，欄位 `start_index`、`end_index`、`score`、`time_start`、`time_end`）與 `scan_similar(series, sample, window, top, step=1, overlap=0.5) -> list[ScanMatch]`。模組只允許向下依賴 `features`、`similarity`、`errors`；`time_start`／`time_end` 由序列的 `time` 欄位以起訖索引取得，缺欄位時以 `ConfigError` 回報。
- 預計觸及的檔案：`ediaad/scan.py`、`tests/test_scan.py`；實作前重新查證（重用 `ediaad/features.py`、`ediaad/similarity.py`、`ediaad/errors.py`、`ediaad/data.py`，不重複實作距離或排序）。
- 必要環境／依賴：TASK-001 的 `.venv`（`numpy`、`pandas`、`pytest`）；測試以合成序列人工植入重疊片段（長度 100、window 20），離線可跑，不需網路。

## 測試計畫

- 測試公開邊界：只呼叫 `ediaad.scan.scan_similar`，觀察回傳 `ScanMatch` 清單的長度、`start_index`／`end_index` 與時間欄位，以及 `ConfigError` 的型別與訊息；不檢視貪婪迴圈或快取等內部結構。
- 第一個失敗行為與預期斷言：`ediaad/scan.py` 尚未存在時，於專案根執行 `.venv/bin/python -m pytest tests/test_scan.py -q` 預期 collection error（`ModuleNotFoundError: No module named 'ediaad.scan'`）；實作後第一個綠燈斷言為「長度 100、window 20 的序列植入兩段重疊 60% 的候選後，`len(result) == 1`，且該筆 `end_index - start_index + 1 == 20`」。
- 後續例外／邊界情境：植入兩段重疊恰好 50% 的候選，斷言兩筆都被保留（嚴格大於門檻的邊界，`docs/architecture/ENGINEERING-REPORT.md` 第 5.3 節明訂）；`top=1` 時回傳筆數為 1；`top` 大於候選數時不補空值；`step=5` 時所有 `start_index` 皆為 5 的倍數；`overlap=0` 時僅真正不重疊者可共存；四種壞參數各自 `pytest.raises(ConfigError)` 並以 `match=` 斷言訊息指出不合法處（範例長度不等於 `window`、序列長度小於 `window`、`top < 1` 或 `step < 1` 或 `overlap` 不在 `[0, 1)`、序列缺 `time` 欄位）；`time_start`／`time_end` 需等於序列中以起訖索引取得的時間值。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_scan.py -q`；相關回歸為專案根執行 `.venv/bin/python -m pytest tests/test_features.py tests/test_similarity.py tests/test_scan.py -q` 與全套 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的執行指令表。
- 非程式任務的替代驗證與理由：不適用（本張為純計算程式任務，重疊抑制的 50% 邊界以人工植入片段即可精確斷言，無需替代驗證）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-004 的交付物（全套 56 passed）；本次新增 `ediaad/scan.py` 與 `tests/test_scan.py`（開工時以 `find . -type f -not -path "./.venv/*" | sort` 與逐檔 sha256 建立快照；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（預計 `docs/workflow/tdd/TASK-005.md`）
- Review 紀錄位置：見上方 review_evidence（預計 `docs/workflow/reviews/TASK-005.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-scan` sha256:9e3074fb542f14c4c8d7f0d42513a9d8a8e0c26f4ba5bb0100c80b91207e3619（原始碼樹）；本張交付 `ediaad/scan.py` `cfd068a3…`、`tests/test_scan.py` `b8b0b991…`；全套 `74 passed`
- 取消、重開或變更原因：無
