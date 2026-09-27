# TASK-003：10 維尺度不變特徵抽取與批次矩陣

- id：TASK-003
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-005","AC-006","AC-007"]
- depends_on：["TASK-002"]
- test_evidence：["docs/workflow/tdd/TASK-003.md"]
- review_evidence：["docs/workflow/reviews/TASK-003.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`ediaad.features.extract(window)` 將一段 K 線視窗壓縮成長度 10 的一維 `numpy` float64 向量，順序等於 `FEATURE_NAMES`，且逐維與手算值相符（容差 1e-9）；整段價格乘 0.01／0.5／1／1000 後 10 維特徵全部不變（容差 1e-9），加常數平移後第 3、4、5、6、8、9、10 維不變（第 1、2、7 維依定義使用價格比值，本就不具平移不變性，見 SPEC AC-006）；全平坦（`high == low`）與零量能等退化視窗回傳有限值，不出現 NaN／Inf；`ediaad.features.extract_matrix(series, window, step)` 對長度 200、視窗 20、步長 1 的序列回傳形狀 `(181, 10)` 的矩陣，每一列與逐窗 `extract` 相同，且矩陣列寬固定不隨視窗長度增加。
- 本張不做：不做穩健正規化、加權距離與排序（TASK-004）；不做滑動掃描與重疊抑制（TASK-005）；不做 `detect` 與 ATR（TASK-008）；不讀寫檔案、不連網、不輸出任何訊息（SPEC 第 5 節原則 1）；不引入 `scipy`／`scikit-learn`；不定義 `序列長度 < window` 的行為（該情境由 TASK-005 的 `scan_similar` 以 `ConfigError` 擋下）。
- 每個 AC 在本張負責的範圍：AC-005 全部（10 維數值、順序等於 `FEATURE_NAMES`、容差 1e-9）；AC-006 全部（四種乘常數下 10 維全部不變、三種平移下第 3／4／5／6／8／9／10 維不變、第 1／2／7 維明列為不具平移不變性、退化視窗為有限值且無 NaN／Inf）；AC-007 全部（`extract_matrix` 形狀 `(181, 10)`、逐列等同逐窗 `extract`、記憶體佔用不隨視窗長度增加）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-005～AC-007、第 5 節模組表中 `ediaad/features.py` 一列（`FEATURE_NAMES`、`extract`、`extract_matrix`）、第 5 節原則 1、第 6 節「可重現性」、第 7 節測試策略第 3 列；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F3、第 4.3 節 `features.py`、第 5.1 節（10 維公式表、退化情境的除法處理、為何選這 10 個）、第 5.2 節（特徵只用於相似度路線，規律路線不依賴它）、第 5.3 節（候選矩陣 `(M, 10)` 的效能設計）；`docs/workflow/CONTEXT.md`「特徵向量（feature vector）」「尺度不變（scale invariance）」「視窗（window）」「候選池（pool）」。
- 模組與公開介面：新增 `ediaad/features.py`，公開 `FEATURE_NAMES`（長度 10 且順序即輸出順序）、`extract(window) -> numpy.ndarray`（形狀 `(10,)`、dtype float64）、`extract_matrix(series, window, step=1) -> numpy.ndarray`（形狀 `(M, 10)`，`M = len(range(0, L - window + 1, step))`）。所有除法須以先檢查分母或 `numpy.divide(..., where=...)` 處理，退化時回傳有限值；不得在模組內使用亂數、檔案或網路。
- 預計觸及的檔案：`ediaad/features.py`、`tests/test_features.py`（必要時 `tests/conftest.py` 新增合成 OHLC 序列夾具）；實作前重新查證（不修改 TASK-002 已交付的 `ediaad/data.py` 與 `ediaad/errors.py`，除非發現契約缺陷）。
- 必要環境／依賴：TASK-001 的 `.venv`（`numpy`、`pandas`、`pytest`）；`Series` 由 TASK-002 的 `load_csv`／`from_rows` 產生；測試離線、可用固定合成序列與手算值，不需網路或外部資料。

## 測試計畫

- 測試公開邊界：只呼叫 `ediaad.features.extract` 與 `ediaad.features.extract_matrix`，以及讀取 `FEATURE_NAMES`；以 `pytest.approx` 逐維比對，不檢視私有輔助函式。
- 第一個失敗行為與預期斷言：`ediaad/features.py` 尚未存在時，於專案根執行 `.venv/bin/python -m pytest tests/test_features.py -q` 預期 collection error（`ModuleNotFoundError: No module named 'ediaad.features'`）；實作後第一個綠燈斷言為 `len(FEATURE_NAMES) == 10`、`extract(window).shape == (10,)`、`extract(window).dtype == numpy.float64`，且第 1 維等於手算的 `close[-1] / close[0] - 1`。
- 後續例外／邊界情境：手算算例涵蓋全部 10 維（含 `return_std` 的母體標準差、`volume_ratio` 前半量能為 0 時取 0、`ma_slope_normalized` 在收盤標準差為 0 時取 0、`close_position` 在 `max(high) == min(low)` 時取 0）；長度 1 與長度 2 的極短視窗需回傳有限值；全平坦（`high == low`）與 `volume` 全 0 需以 `numpy.isfinite(...).all()` 斷言且不得出現 NaN／Inf；四種乘常數後以容差 1e-9 斷言 10 維全部不變；三種平移後斷言第 3、4、5、6、8、9、10 維不變，**並另以斷言證明第 1 維（`total_return`）確實會改變**——避免把「不變」與「測試空轉」混為一談；`extract_matrix` 以 `step=1` 斷言 `(181, 10)`、以 `step=5` 斷言列數與起始索引對應、以 `step=window` 斷言不重疊；逐列迴圈呼叫 `extract` 並斷言矩陣與逐窗結果 `numpy.allclose(..., atol=1e-12)`；記憶體契約以「矩陣為單一 2 維 float64 陣列、`shape[1] == 10` 且每列 `nbytes` 固定」斷言，不實測 RSS。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_features.py -q`（`docs/workflow/PROJECT.md` 的單檔測試範例即為本檔）；相關回歸為專案根執行 `.venv/bin/python -m pytest -q`。
- 非程式任務的替代驗證與理由：不適用（本張為純計算程式任務，尺度不變與退化情境都能在公開函式介面上以性質測試斷言，無需替代驗證）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001（環境）與 TASK-002（`ediaad/data.py`、`ediaad/errors.py`、`tests/test_data.py`，17 passed）的交付物；本次新增 `ediaad/features.py` 與 `tests/test_features.py`。開工前另修正 SPEC AC-006（v0.3 → v0.4，見 SPEC 第 9 節）
- TDD 紀錄位置：見上方 test_evidence（預計 `docs/workflow/tdd/TASK-003.md`）
- Review 紀錄位置：見上方 review_evidence（預計 `docs/workflow/reviews/TASK-003.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-features` sha256:eca3deca94d213cb0f009e6c5537f57bd431b03ff79ba9910d981142f7662272（原始碼樹）；本張交付 `ediaad/features.py` `e6bce065…`、`tests/test_features.py` `8c486efe…`；全套 `43 passed`
- 取消、重開或變更原因：無
