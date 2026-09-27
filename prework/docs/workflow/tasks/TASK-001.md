# TASK-001：可重現的 venv、pip 取得與依賴安裝腳本

- id：TASK-001
- type：setup
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-001"]
- depends_on：[]
- test_evidence：["docs/workflow/tdd/TASK-001.md"]
- review_evidence：["docs/workflow/reviews/TASK-001.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：在一台沒有 `pip`、也無法使用 `sudo` 的機器上，執行 `python3 scripts/bootstrap_env.py` 會建立 `.venv`、取得 pip、安裝 `requirements.txt` 與 `requirements-dev.txt` 的依賴，並讓 `.venv/bin/python -m pytest --version` 可用；重跑第二次不破壞既有環境且仍 exit 0。
- 本張不做：不安裝任何產品程式碼（`ediaad/` 套件本張不建立）；不建立桌面圖示；不引入 `requirements` 以外的套件；不執行 `git` 或任何對外動作。
- 每個 AC 在本張負責的範圍：AC-001 全部（腳本存在、可重現、冪等、exit code 0）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-001 與第 5 節「模組責任與邊界」原則 1；`docs/workflow/PROJECT.md` 的環境實測表（`sudo` 因 `no new privileges` 不可用、`pip` 未安裝、`python3 -m venv --without-pip` 可用、PyPI 與 `bootstrap.pypa.io` 可達）。
- 模組與公開介面：新增 `scripts/bootstrap_env.py`（以 `main()` 回傳 exit code）、`requirements.txt`（`numpy`、`pandas`）、`requirements-dev.txt`（`pytest`）。
- 預計觸及的檔案：`scripts/bootstrap_env.py`、`requirements.txt`、`requirements-dev.txt`、`.gitignore`（排除 `.venv/`、`.cache/`）；實作前重新查證。
- 必要環境／依賴：Python 3.12.3、網路可達 `bootstrap.pypa.io` 與 PyPI；不需要 `sudo`、`pip`、`curl`。

## 測試計畫

- 測試公開邊界：以子程序執行 `python3 scripts/bootstrap_env.py` 並檢查 exit code 與 `.venv` 內容；以 `.venv/bin/python -c "import numpy, pandas, pytest"` 驗證依賴。
- 第一個失敗行為與預期斷言：在腳本尚未存在時執行同一命令，預期 `exit code 2`（`can't open file ... No such file or directory`）；實作後預期 exit code 0。
- 後續例外／邊界情境：`.venv` 已存在時重跑；`get-pip.py` 下載失敗時要留下可讀錯誤且不刪除既有 `.venv`；`requirements` 缺少時要指出檔名。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `python3 scripts/bootstrap_env.py`、`.venv/bin/python -m pytest --version`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：本張沒有可先寫的行為 Red（環境尚未存在，任何測試都無法執行），TDD 紀錄的 `verification` 填 `alternative`，`alternative_reason` 寫明「環境建置無從先 Red，改以實際執行、重跑冪等與依賴 import 作為替代驗證」。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：`docs/workflow/evidence/baseline-before-implement.txt`（52 個檔案，sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`；本專案未初始化 Git，故以檔案快照為基準）。開工時工作區沒有產品程式碼，`ocaievo/` 只有本張新增的檔案。
- TDD 紀錄位置：見上方 test_evidence（預計 `docs/workflow/tdd/TASK-001.md`）
- Review 紀錄位置：見上方 review_evidence（預計 `docs/workflow/reviews/TASK-001.md`）
- 目前被驗證版本／檔案狀態：檔案快照 `snap-2026-09-24-ocaievo-bootstrap`（`ocaievo/scripts/bootstrap_env.py`、`ocaievo/requirements.txt`、`ocaievo/requirements-dev.txt`、`.gitignore`）
- 取消、重開或變更原因：無
