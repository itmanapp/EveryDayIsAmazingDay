# TASK-004：穩健正規化、加權距離與相似度排序

- id：TASK-004
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-008","AC-009"]
- depends_on：["TASK-003"]
- test_evidence：["docs/workflow/tdd/TASK-004.md"]
- review_evidence：["docs/workflow/reviews/TASK-004.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`ediaad.similarity.rank(sample_feature, pool, weights=DEFAULT_WEIGHTS)` 以候選池自身的中位數與 IQR 對每一維做穩健正規化（IQR 為 0 的維度退化為 0），計算加權 L1 距離並以 `score = 1 / (1 + d)` 轉分數，回傳依分數由高到低排序的 `Match` 清單（`index`、`score`、`feature_distance`）；候選池中與範例完全相同的視窗排名第 1、分數為 1.0；所有分數落在 (0, 1]；同分時以索引升冪；權重長度不符、含負值、總和為 0 三種壞權重各自丟出 `ConfigError`；權重整體乘 2 後排序與分數完全不變。
- 本張不做：不做滑動視窗抽取與重疊抑制（TASK-005）；不改動 10 維特徵的定義或順序（TASK-003）；不做 `forward_stats`（TASK-006）；不做規律偵測（TASK-008）；不讀寫檔案、不連網、不輸出訊息；不做 CLI 或網頁參數面板；不定義空候選池或 `pool` 形狀不合的額外語意（SPEC 未要求）。
- 每個 AC 在本張負責的範圍：AC-008 全部（完全相同者排名第 1 且分數 1.0、分數值域 (0, 1]、同分索引升冪）；AC-009 全部（三種壞權重的 `ConfigError`、權重整體縮放不改變排序）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-008～AC-009、第 5 節模組表中 `ediaad/similarity.py` 一列（`Match`、`DEFAULT_WEIGHTS`、`rank`）、第 5 節「其他結構」的 `Match` 欄位、第 5 節原則 1 與 3、第 6 節「可重現性」（同分以索引升冪）、第 7 節測試策略第 4 列；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F4、第 4.3 節 `similarity.py`、第 5.2 節（中位數與 IQR 正規化、加權 L1 距離、`1/(1+d)` 分數、`np.lexsort` 的排序穩定性、為何不用平均數與標準差）、第 4.5 節資料流 A；`docs/workflow/CONTEXT.md`「相似度分數」（(0, 1]、不是機率）。
- 模組與公開介面：新增 `ediaad/similarity.py`，公開 `Match`（資料類別，欄位 `index`、`score`、`feature_distance`）、`DEFAULT_WEIGHTS`（長度 10 的權重向量，總和 > 0，預設全 1）、`rank(sample_feature, pool, weights=DEFAULT_WEIGHTS) -> list[Match]`。排序使用 `numpy.lexsort`（先分數降冪、再索引升冪）確保同分順序唯一；權重驗證在計算前完成並以 `ConfigError` 回報；模組不得匯入 `scan`、`patterns`、`monitor` 或任何 I/O。
- 預計觸及的檔案：`ediaad/similarity.py`、`tests/test_similarity.py`；實作前重新查證（重用 TASK-003 的 `ediaad/features.py` 與 TASK-002 的 `ediaad/errors.py`，不重複定義特徵或例外）。
- 必要環境／依賴：TASK-001 的 `.venv`（`numpy`、`pandas`、`pytest`）；測試資料以 `tmp_path` 或記憶體內合成序列產生，離線可跑，不需網路。

## 測試計畫

- 測試公開邊界：只呼叫 `ediaad.similarity.rank` 並觀察回傳 `Match` 清單的 `index`、`score`、`feature_distance`，以及 `DEFAULT_WEIGHTS` 的內容；候選池以 TASK-003 的 `extract_matrix` 或手工建構的 `(M, 10)` 陣列提供，不檢視正規化中間量。
- 第一個失敗行為與預期斷言：`ediaad/similarity.py` 尚未存在時，於專案根執行 `.venv/bin/python -m pytest tests/test_similarity.py -q` 預期 collection error（`ModuleNotFoundError: No module named 'ediaad.similarity'`）；實作後第一個綠燈斷言為「候選池含與範例完全相同的視窗時，`matches[0].index` 等於該視窗索引且 `matches[0].score == pytest.approx(1.0)`」。
- 後續例外／邊界情境：分數值域以 `all(0.0 < m.score <= 1.0 for m in matches)` 斷言（含距離極大的候選，分數趨近 0 但不為 0）；候選池只有 1 筆時每維 IQR 為 0，需退化為距離 0、分數 1.0 而非除以零；某一維在候選池中全部同值（IQR 為 0）時該維不得產生 NaN／Inf；兩個候選分數相同時以索引升冪；`DEFAULT_WEIGHTS` 長度契約與總和 > 0；三種壞權重（長度 9 或 11、含 `-1`、全 0）各自 `pytest.raises(ConfigError)` 並以 `match=` 斷言訊息指出問題；把合法權重整體乘 2 後，斷言 `[m.index for m in result]` 與 `[m.score for m in result]` 與原權重完全相同（權重絕對尺度不影響結果）。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_similarity.py -q`；相關回歸為專案根執行 `.venv/bin/python -m pytest tests/test_features.py tests/test_similarity.py -q` 與全套 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的執行指令表。
- 非程式任務的替代驗證與理由：不適用（本張為純計算程式任務，排序穩定性與錯誤回報都能在公開函式介面上以 pytest 斷言，無需替代驗證）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-003 的交付物（環境、`data.py`／`errors.py`、`features.py`；全套 43 passed）；本次新增 `ediaad/similarity.py` 與 `tests/test_similarity.py`（開工時以 `find . -type f -not -path "./.venv/*" | sort` 與逐檔 sha256 建立快照；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（預計 `docs/workflow/tdd/TASK-004.md`）
- Review 紀錄位置：見上方 review_evidence（預計 `docs/workflow/reviews/TASK-004.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-similarity` sha256:23c2dbff1a4d7d13a94a6fee605dda2f2b55e7db77ba802b34fcb382f4d70903（原始碼樹）；本張交付 `ediaad/similarity.py` `30ca12ea…`、`tests/test_similarity.py` `6820964a…`；全套 `56 passed`
- 取消、重開或變更原因：無
