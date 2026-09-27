# TASK-001 Code Review

- task_id：TASK-001
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-bootstrap sha256:283a658017f2894616aef3b8f1729d61f4a76fe52f4568fe76d99f48d2f7e008
- Task／Spec 版本：TASK-001 / SPEC-001 v0.3
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（52 檔，sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：組合 sha256 `283a658017f2894616aef3b8f1729d61f4a76fe52f4568fe76d99f48d2f7e008`；個別檔案——`ocaievo/scripts/bootstrap_env.py` `cb784b5e452c09175da1ae9ebbc6fb3f382c4cab037e0d227708d522c184b34b`、`ocaievo/requirements.txt` `dbb7eda4f1974291145b96ae392e3ef1cc12921da39ef71653cc5a082af0b9d8`、`ocaievo/requirements-dev.txt` `a6e85fae05a2d343d6e237e4c23661e50567e5e75c51bcde9ea6f907d41cbf47`、`.gitignore` `30571a6772b88beae5b9a3bf6cec1fc4c733babccb6ca074444e4881d70174bd`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），因此以開工前後的檔案清單與逐檔 sha256 比對；本張新增 3 檔（`ocaievo/scripts/bootstrap_env.py`、`ocaievo/requirements.txt`、`ocaievo/requirements-dev.txt`）、修改 1 檔（`.gitignore`），並新增工作文件（TDD／Review／基準快照）
- 納入的已提交、未提交、新增檔案：上述 4 個程式／設定檔（本張交付物）＋ 本張 TDD 與 Review 紀錄
- 排除的既有修改及理由：`docs/workflow/` 既有文件、`docs/architecture/ENGINEERING-REPORT.md`、`.project-workflow/` 為規劃階段產物或工具包快照，非本張交付範圍；`.venv/` 為產物，不納入審查
- 程式規範來源：`docs/workflow/SPEC.md` 第 5 節（模組責任、原則 1「計算不碰 I/O」、錯誤分層）、`docs/workflow/PROJECT.md`（環境限制與指令）、`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-001 | `ocaievo/scripts/bootstrap_env.py`；證據 `docs/workflow/tdd/TASK-001.md` Cycle 1～3 | 符合 | — |

逐條核對 AC-001 的三個斷言：

1. **exit code 0**：實跑 `python3 scripts/bootstrap_env.py` → exit 0，並輸出 `Successfully installed … numpy-2.5.3 … pandas-3.0.6 … pytest-9.1.1`。符合。
2. **`.venv` 內 numpy／pandas／pytest 可 import**：`.venv/bin/python -m pytest --version` → `pytest 9.1.1`、exit 0；腳本結尾以 `import numpy, pandas, pytest` 驗證並印出三套件版本。符合。
3. **重跑第二次仍 exit 0 且不重複破壞環境**：第二次執行印出「環境已就緒，無需變更（冪等）」、exit 0，且未重新下載或安裝；`--check` 亦 exit 0。符合。

Given「乾淨環境，無 pip、無法使用 sudo」：本機 `pip`／`pip3` 不存在、`sudo -n true` 因 `no new privileges` 失敗（`docs/workflow/PROJECT.md` 實測表），實作未使用兩者。符合。

未多做未要求的行為：沒有建立桌面圖示、沒有安裝 `requirements` 以外的套件、沒有 `git` 操作。符合 TASK-001 的「本張不做」。

## 品質 Review

已檢查項目與結果：

- **錯誤處理與 exit code 分層**：輸入或環境錯誤（Python 版本不足、缺依賴清單）回 `2`；下載／安裝失敗回 `1`；成功回 `0`。與 `PROJECT.md` 的 exit code 語意一致。實測缺 `requirements-dev.txt` → exit 2 並指出檔名；不可達 URL → exit 1 並印出 `URLError`。未發現問題。
- **資源釋放與資料安全**：下載以 `with urllib.request.urlopen(...)` 關閉連線；失敗路徑不刪除 `.venv`（實測 sentinel 檔保留）；`--recreate` 是唯一會刪除環境的路徑，且需明確旗標。未發現問題。
- **輸入驗證**：`PROJECT_DIR` 由 `__file__` 解析，與 cwd 無關（實測從專案根執行仍正確）；依賴清單存在性在動作前檢查。未發現問題。
- **模組責任與依賴**：只用標準庫（`argparse`、`subprocess`、`sys`、`urllib`、`venv`、`pathlib`、`os`）；未引入 curl／wget 或第三方套件，符合 SPEC 第 5 節「一次安裝、零額外依賴」。未發現問題。
- **命名與可讀性**：函式名與訊息為白話且指出下一步（例如「既有 .venv 未被刪除；修正問題後可重跑本腳本」）。未發現問題。
- **測試能否辨認退化**：本張以子程序 exit code 與 import 結果為觀察邊界，能辨認「環境未就緒卻回報成功」「失敗時刪除環境」兩類退化。未發現問題。
- **與既有維護習慣一致**：專案此時無其他程式碼可比較；已依 SPEC 第 5 節的模組與錯誤分層命名。未發現問題。
- **未實機驗證項**：Windows 佈局分支（`Scripts/python.exe`）無法在本機驗證；`--recreate` 分支未實跑（對已驗證環境具破壞性）。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 可維護性 | advisory | `ocaievo/scripts/bootstrap_env.py` `main()` 內以區域 `import shutil` | 可移至檔頭；但區域載入讓 `--recreate` 以外的路徑不載入 `shutil`，影響極小 | 延後（理由如上；不影響 AC-001 行為，且改動會使已驗證版本失效，須重新驗證） |
| A-2 | 錯誤處理 | advisory | 若 `.venv` 存在但損壞（例如 `bin/python` 被刪），未加 `--recreate` 時會在既有目錄上補建，可能留下混雜狀態 | 可加入「偵測損壞並提示使用 `--recreate`」；但自動刪除使用者環境有資料風險，寧可要求明確旗標 | 延後（TASK-001 未要求自動重建；`--recreate` 為文件化補救方式） |
| A-3 | 未驗證項 | advisory | Windows 路徑分支與 `--recreate` 分支未實跑 | 需要時在對應平台驗證 | 延後（開發機為 Linux；交付報告將標示） |

## 修正與重審

第 1 輪未發現 blocking，因此無修正迴圈。A-1～A-3 為 advisory，已記錄理由並延後；依 `references/review.md`，advisory 不阻擋 `done`。

## 結果

- Spec Review：passed（AC-001 三項斷言逐條符合，無多做未要求行為）
- 品質 Review：passed（錯誤處理、資源釋放、輸入驗證、模組責任、命名、退化辨識皆已檢查，未發現 blocking 問題）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（區域 import，影響極小）、A-2（損壞環境需明確 `--recreate`，避免自動刪除使用者環境）、A-3（Windows 與 `--recreate` 分支未實機驗證）
- 能否標為 done：**可以**
- 限制與未驗證事項：Windows 佈局與 `--recreate` 分支未實跑；本張無自動化測試檔（`setup` 類型，依 TASK-001 測試計畫採替代驗證）
