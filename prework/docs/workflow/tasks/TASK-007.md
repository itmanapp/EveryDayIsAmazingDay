# TASK-007：規律規格模型、驗證與序列化

- id：TASK-007
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-014","AC-015"]
- depends_on：["TASK-002"]
- test_evidence：["docs/workflow/tdd/TASK-007.md"]
- review_evidence：["docs/workflow/reviews/TASK-007.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`ediaad.patterns.PatternSpec` 是 frozen 的資料類別，含 `pattern_id`、`range_bars_min`、`range_bars_max`、`band_atr_multiple_max`、`atr_period`、`breakdown_bars_max`、`breakdown_depth_band_min`、`breakdown_depth_band_max`、`recovery_bars_max`、`recovery_target` 十個欄位（依 SPEC 第 5 節順序），全部為根數、倍數或具名目標等相對單位且不含任何價格欄位；`__post_init__` 在建構當下即驗證（含 `range_bars_min <= range_bars_max` 的交叉檢查、非負與下限、`recovery_target` 必須在 `RECOVERY_TARGETS` 內），不合法者丟出 `ConfigError`，因此不合法規格無法被建構出來；`NAMED_PATTERNS` 收錄內建規律 `range_fakeout_reversion` 與其 SPEC 第 5 節的預設值；`to_json(spec)` 以 `sort_keys=True` 產生穩定鍵序，`from_json(payload)` 還原後與原規格完全相等（round-trip），且對缺欄位、多欄位、型別不符各自丟出 `ConfigError`。
- 本張不做：不實作 `atr`、`detect`、`learn`（TASK-008／TASK-009 於同一個 `ediaad/patterns.py` 擴充）；不做 `PatternEvent`；不做監控設定檔驗證（TASK-010 的 `load_config`）；不做網頁參數面板或範例學習頁；不讀寫檔案、不連網、不輸出訊息；不新增 `recovery_target` 的候選值（目前只有 `range_mean`）。
- 每個 AC 在本張負責的範圍：AC-014 全部（合法規格可建立、frozen 不可變、不合法規格在 `__post_init__` 即丟 `ConfigError`、全部欄位皆為相對單位且無價格欄位）；AC-015 全部（`to_json`／`from_json` round-trip 相等、輸出鍵序穩定、缺欄位／多欄位／型別不符各自 `ConfigError`）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-014～AC-015、第 5 節模組表中 `ediaad/patterns.py` 一列（`PatternSpec`、`PatternEvent`、`NAMED_PATTERNS`、`RECOVERY_TARGETS`、`to_json`、`from_json`、`atr`、`detect`、`learn`）、第 5 節「PatternSpec」資料契約與內建預設值、第 5 節原則 1 與 3、第 6 節「可重現性」、第 7 節測試策略第 6 列；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F7、第 4.3 節 `patterns.py`、第 4.4 節「PatternSpec」（全部相對單位是尺度不變在資料結構層的保證、`__post_init__` 驗證含交叉檢查）、第 5.5 節（規格欄位在偵測中的角色）；`docs/workflow/CONTEXT.md`「規律規格（PatternSpec）」（不含任何價格欄位）。
- 模組與公開介面：新增 `ediaad/patterns.py`，本張公開 `PatternSpec`（`@dataclass(frozen=True)`，十個欄位，`__post_init__` 驗證）、`NAMED_PATTERNS`（至少含 `range_fakeout_reversion`）、`RECOVERY_TARGETS`（目前只有 `range_mean`）、`to_json(spec) -> str`、`from_json(payload: str | dict) -> PatternSpec`（名稱依 SPEC 第 5 節與報告第 4.3 節；是否同時以 `PatternSpec.to_json()`／`from_json()` 方法提供便利入口，實作前重新查證）。驗證失敗一律以 `ediaad/errors.py` 的 `ConfigError` 回報，`from_json` 不得以預設值補齊缺欄位。
- 預計觸及的檔案：`ediaad/patterns.py`、`tests/test_patterns_spec.py`；實作前重新查證（重用 TASK-002 的 `ediaad/errors.py`；本張建立 `ediaad/patterns.py` 後，TASK-008／TASK-009／TASK-010 會在同一檔或匯入本檔擴充，不得破壞已定契約）。
- 必要環境／依賴：TASK-001 的 `.venv`（`pytest`；本張只需標準庫 `dataclasses`、`json` 與既有例外模組）；測試離線可跑，不需 `numpy`／`pandas` 之外的依賴，也不需網路。

## 測試計畫

- 測試公開邊界：只透過 `ediaad.patterns` 的公開名稱建構 `PatternSpec`、呼叫 `to_json`／`from_json`、讀取 `NAMED_PATTERNS` 與 `RECOVERY_TARGETS`；不呼叫私有驗證函式，也不斷言 `__post_init__` 的實作細節。
- 第一個失敗行為與預期斷言：`ediaad/patterns.py` 尚未存在時，於專案根執行 `.venv/bin/python -m pytest tests/test_patterns_spec.py -q` 預期 collection error（`ModuleNotFoundError: No module named 'ediaad.patterns'`）；實作後第一個綠燈斷言為「`PatternSpec(**NAMED_PATTERNS["range_fakeout_reversion"])` 可成功建構，且對已建構實例指派新值時 `pytest.raises(dataclasses.FrozenInstanceError)`」。
- 後續例外／邊界情境：`range_bars_min > range_bars_max`、負數（如 `atr_period=-1`、`breakdown_depth_band_min=-0.1`）、`band_atr_multiple_max=0`、`breakdown_bars_max=-1`、`recovery_bars_max=-2`、`range_bars_min=0`、未知 `recovery_target`（如 `"range_high"`）皆 `pytest.raises(ConfigError)`；`range_bars_min == range_bars_max` 為合法邊界；型別錯誤（`range_bars_min` 給 `"20"`、`True` 給 int 欄位、`"3.0"` 給 float 欄位）需 `ConfigError`；`from_json` 對缺欄位、多一個未知鍵、型別不符三種輸入各自 `ConfigError` 且不建構出任何規格；round-trip 以 `from_json(to_json(spec)) == spec` 斷言（frozen dataclass 的相等語意），並斷言同一 spec 連續兩次 `to_json` 輸出字串完全相同（`sort_keys=True` 的鍵序穩定），以及 `json.loads(to_json(spec))` 的鍵集合等於欄位集合。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_patterns_spec.py -q`；相關回歸為專案根執行 `.venv/bin/python -m pytest tests/test_patterns_spec.py tests/test_data.py -q` 與全套 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的執行指令表。
- 非程式任務的替代驗證與理由：不適用（本張為程式任務，規格驗證與序列化都能在公開介面上以 pytest 斷言，無需替代驗證）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-006 的交付物（全套 87 passed）；本次建立 `ediaad/patterns.py`（僅 PatternSpec 部分）與 `tests/test_patterns_spec.py`（開工時以 `find . -type f -not -path "./.venv/*" | sort` 與逐檔 sha256 建立快照；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（預計 `docs/workflow/tdd/TASK-007.md`）
- Review 紀錄位置：見上方 review_evidence（預計 `docs/workflow/reviews/TASK-007.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-patterns-spec` sha256:8f6edeb7ddfb91c799b8c42a470657afaa1efee3eff4cb5695041faf179b1058（原始碼樹）；本張交付 `ediaad/patterns.py` `1eed0009…`、`tests/test_patterns_spec.py` `03eac75e…`；全套 `122 passed`
- 取消、重開或變更原因：無
