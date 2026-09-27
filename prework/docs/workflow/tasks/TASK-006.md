# TASK-006：後續走勢統計與雙路線共用介面

- id：TASK-006
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-012","AC-013"]
- depends_on：["TASK-002"]
- test_evidence：["docs/workflow/tdd/TASK-006.md"]
- review_evidence：["docs/workflow/reviews/TASK-006.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`ediaad.outlook.forward_stats(fragments, series, horizon, end_attr="end_index")` 對每個片段以 `end = getattr(fragment, end_attr)` 取得結束索引，計算 `close[end + horizon] / close[end] - 1`，排除 `end + horizon` 超出序列者，回傳 `OutlookStats`（`samples`、`up_probability`、`mean_return`、`median_return`、`std_return`），其中上漲機率只計報酬嚴格大於 0 者、`std_return` 為母體標準差（`ddof=0`）；無樣本時 `samples=0` 且其餘四個欄位為 `None`（不是 0）；`end_attr` 未指定時預設使用 `end_index`，指定為 `recovery_index` 時對具該欄位的物件同樣得到正確結果，使相似度路線（`ScanMatch`）與規律路線（`PatternEvent`）共用同一個函式。
- 本張不做：不產生片段清單（`ScanMatch` 於 TASK-005、`PatternEvent` 於 TASK-008）；不實作偵測或掃描；不匯入 `scan` 或 `patterns`（SPEC 第 5 節與報告第 4.2 節的依賴方向約束，改以 `Protocol` 描述「有結束索引欄位的物件」）；不做 SQLite 事件查詢；不做片段相關性處理（報告第 5.8 節已揭露的統計偏誤）；不做 CLI 報表。
- 每個 AC 在本張負責的範圍：AC-012 全部（`samples`、`up_probability`、平均／中位數／母體標準差與手算相符、`end+H` 超出者排除、報酬恰為 0 不算上漲、無樣本時四個欄位為 `None`）；AC-013 全部（以 `end_attr` 指名結束欄位、兩條路線共用同一函式、未指定時預設 `end_index`，即 F-002 回歸）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-012～AC-013、第 5 節模組表中 `ediaad/outlook.py` 一列（`OutlookStats`、`forward_stats`）、第 5 節「其他結構」的 `OutlookStats` 與 `ScanMatch`／`PatternEvent` 欄位、第 5 節原則 1 與 3、第 7 節測試策略第 5 列；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F6、第 4.2 節（`outlook` 刻意不匯入 `scan`，以 `Protocol` 描述「有 `end_index` 的物件」）、第 4.3 節 `outlook.py`、第 4.4 節 `ScanMatch` 與 `PatternEvent`、第 5.8 節（計算式、尾端排除的理由、`None` 而非 0 的理由、已知統計偏誤）、第 4.5 節資料流 A 與 B；`docs/workflow/CONTEXT.md`「後續走勢（forward path）／horizon」。
- 模組與公開介面：新增 `ediaad/outlook.py`，公開 `OutlookStats`（資料類別，欄位 `samples`、`up_probability`、`mean_return`、`median_return`、`std_return`）與 `forward_stats(fragments, series, horizon, end_attr="end_index") -> OutlookStats`；以 `typing.Protocol`（例如 `HasEndIndex`）描述輸入片段的形狀，並以 `getattr(fragment, end_attr)` 取值。模組只依賴 `numpy`／`pandas` 與 `errors`，不得匯入 `scan`、`patterns`、`monitor`，也不得讀寫檔案、連網或輸出訊息。
- 預計觸及的檔案：`ediaad/outlook.py`、`tests/test_outlook.py`；實作前重新查證（重用 TASK-002 的 `ediaad/errors.py` 與 Series 契約；不新增 `ScanMatch` 或 `PatternEvent` 定義）。
- 必要環境／依賴：TASK-001 的 `.venv`（`numpy`、`pandas`、`pytest`）；測試以合成的已知後續報酬序列與輕量測試替身（同時具備 `end_index` 與 `recovery_index` 兩個欄位）進行，離線可跑，不需網路。

## 測試計畫

- 測試公開邊界：只呼叫 `ediaad.outlook.forward_stats` 並觀察回傳 `OutlookStats` 的五個欄位；片段以測試替身或既有結構提供；以手算報酬作為 oracle，不檢視內部彙總方式。
- 第一個失敗行為與預期斷言：`ediaad/outlook.py` 尚未存在時，於專案根執行 `.venv/bin/python -m pytest tests/test_outlook.py -q` 預期 collection error（`ModuleNotFoundError: No module named 'ediaad.outlook'`）；實作後第一個綠燈斷言為「兩個後續報酬分別為 `+0.10` 與 `-0.05` 的片段得到 `samples == 2`、`up_probability == pytest.approx(0.5)`、`mean_return == pytest.approx(0.025)`」。
- 後續例外／邊界情境：`end + horizon` 恰好等於序列長度時必須排除，而 `end == len(series) - 1 - horizon` 時必須保留（以成對斷言固定邊界）；報酬恰為 0 的樣本計入 `samples` 但不計入上漲（以 `up_probability` 的變化斷言，例如兩個片段中一個 0、一個正的結果為 0.5）；空片段清單與「全部片段都被尾端排除」兩種情況都得到 `samples == 0` 且 `up_probability`／`mean_return`／`median_return`／`std_return` 皆為 `None`；`std_return` 以 `ddof=0` 手算值斷言（刻意與 `pandas` 預設 `ddof=1` 不同）；同一個測試替身同時具備 `end_index` 與 `recovery_index` 且兩值不同，未指定 `end_attr` 時斷言採用 `end_index`（預設值回歸）；以 `end_attr="recovery_index"` 重跑並斷言結果對應 `recovery_index`，作為 AC-013 的路線契約；`PatternEvent` 的真實整合斷言於 TASK-007／TASK-008 完成後納入回歸。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_outlook.py -q`；相關回歸為專案根執行 `.venv/bin/python -m pytest tests/test_data.py tests/test_outlook.py -q` 與全套 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的執行指令表。
- 非程式任務的替代驗證與理由：不適用（本張為純計算程式任務，統計值以手算 oracle 斷言，兩條路線的共用介面以測試替身即可驗證，無需替代驗證）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-005 的交付物（全套 74 passed）；本次新增 `ediaad/outlook.py` 與 `tests/test_outlook.py`（開工時以 `find . -type f -not -path "./.venv/*" | sort` 與逐檔 sha256 建立快照；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（預計 `docs/workflow/tdd/TASK-006.md`）
- Review 紀錄位置：見上方 review_evidence（預計 `docs/workflow/reviews/TASK-006.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-outlook` sha256:1f053e86d43c06c5f18e2e96251708c5bf4823d5d75b3bafa336bb2a366fac44（原始碼樹）；本張交付 `ediaad/outlook.py` `afa74970…`、`tests/test_outlook.py` `63f243a0…`；全套 `87 passed`
- 取消、重開或變更原因：無
