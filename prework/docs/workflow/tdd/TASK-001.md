# TASK-001 測試紀錄

- task_id：TASK-001
- verification：alternative
- result：passed
- checked_version：snap-2026-09-24-ocaievo-bootstrap sha256:283a658017f2894616aef3b8f1729d61f4a76fe52f4568fe76d99f48d2f7e008
- alternative_reason：本張是 `setup` 類型，交付物是「讓後續 Task 能跑測試的環境」。在腳本存在之前，`.venv` 不存在、`pytest` 也無法執行，因此沒有任何可先寫而失敗的產品行為測試（Red 只能是「檔案不存在」，無法斷言目標行為）。依 `references/tdd.md`「純文件或低風險設定不強造 Red」與 TASK-001 測試計畫的記載，改以**實際執行子程序並檢查 exit code、`.venv` 內容與 import 結果**作為替代驗證，並涵蓋冪等、缺檔與下載失敗三種邊界。
- Task／Spec 版本：TASK-001 / SPEC-001 v0.3
- 測試邊界：以子程序執行 `python3 scripts/bootstrap_env.py`（工作目錄 `ocaievo/`，另測從專案根執行以驗證 cwd 無關性），觀察 exit code、stdout 訊息與 `.venv` 內容；依賴以 `.venv/bin/python -c "import numpy, pandas, pytest"` 驗證。不呼叫腳本內部的 private 函式。
- 基線結果：開工前 `ocaievo/` 不存在，`.venv` 不存在。開工快照為 `docs/workflow/evidence/baseline-before-implement.txt`（52 檔，sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：見 `alternative_reason`。替代驗證的具體項目與結果列於下方 Cycle 1～3。

## Cycle 1：環境尚未就緒（真實失敗訊號）

- AC 與預期行為：AC-001 的「檢查」語意——環境尚未建置時必須明確回報失敗，而非靜默成功。
- 測試檔案／案例：無測試檔（子程序驗證）。
- 工作目錄與環境：`ocaievo/`，Python 3.12.3，無 `.venv`。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `python3 scripts/bootstrap_env.py --check` | 1 | `[bootstrap] 檢查失敗：.venv 或依賴尚未就緒`；`ls -d .venv` → 沒有此一檔案或目錄 | 尚未有 `.venv`／2026-09-24 |
| Green | `python3 scripts/bootstrap_env.py` | 0 | `Successfully installed ... numpy-2.5.3 ... pandas-3.0.6 ... pytest-9.1.1`；`完成`；`python 3.12.3 / numpy 2.5.3 / pandas 3.0.6 / pytest 9.1.1` | snap-2026-09-24-ocaievo-bootstrap／2026-09-24 |

- Red 確實因目標行為失敗的解釋：失敗來自主張的目標行為本身（環境未就緒 → 回報失敗），不是工具缺失或拼字錯誤；同一命令在建置後即為 exit 0。
- 最小實作摘要：`ocaievo/scripts/bootstrap_env.py`（`venv --without-pip` 建環境 → 標準庫 `urllib` 下載 `get-pip.py` → 以 venv 的 python 安裝 pip → `pip install -r requirements.txt -r requirements-dev.txt` → import 驗證）、`requirements.txt`、`requirements-dev.txt`。

## Cycle 2：冪等與版本釘選

- AC 與預期行為：AC-001「重跑第二次仍 exit 0 且不重複破壞環境」。
- 測試檔案／案例：無測試檔（子程序驗證）。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Green | `python3 scripts/bootstrap_env.py`（第二次，requirements 已釘為 `numpy==2.5.3`／`pandas==3.0.6`／`pytest==9.1.1`） | 0 | `[bootstrap] 環境已就緒，無需變更（冪等）`，未重新下載或安裝 | snap-2026-09-24-ocaievo-bootstrap／2026-09-24 |
| Green | `python3 scripts/bootstrap_env.py --check` | 0 | `檢查通過：.venv 與依賴皆就緒` | 同上 |
| Green | 專案根執行 `python3 ocaievo/scripts/bootstrap_env.py --check` | 0 | 同上（證明路徑以本檔位置解析，與工作目錄無關） | 同上 |
| Green | `ocaievo/.venv/bin/python -m pytest --version` | 0 | `pytest 9.1.1` | 同上 |

- 說明：`requirements.txt`／`requirements-dev.txt` 在首次安裝後釘為實際安裝並驗證通過的精確版本（numpy 2.5.3、pandas 3.0.6、pytest 9.1.1），以確保可重現。

## Cycle 3：錯誤路徑（缺檔與下載失敗）

- AC 與預期行為：TASK-001 測試計畫的例外情境——缺依賴清單要指出檔名；下載失敗要留下可讀錯誤且**不刪除既有 `.venv`**。
- 測試檔案／案例：無測試檔（子程序驗證；下載失敗在隔離目錄 `/tmp/bt_fail/` 以替換 URL 的副本執行，不動本專案產物）。

| 階段 | 實際命令 | exit code | 關鍵輸出／證據位置 | 程式版本／日期 |
| --- | --- | --- | --- | --- |
| Green | 暫時移走 `requirements-dev.txt` 後執行 `python3 scripts/bootstrap_env.py --check` 與 `python3 scripts/bootstrap_env.py` | 2 | `[bootstrap] 找不到依賴清單：requirements-dev.txt（預期位於 …/ocaievo）` | 同上 |
| Green | 隔離目錄中把 `GET_PIP_URL` 改為 `https://127.0.0.1:9/get-pip.py` 後執行 | 1 | `環境建置失敗：URLError: <urlopen error [Errno 111] Connection refused>`；`既有 .venv 未被刪除；修正問題後可重跑本腳本`；`.venv/KEEP_ME` 內容 `sentinel` 仍存在 | 同上 |

- 說明：移走的 `requirements-dev.txt` 已還原；`/tmp/bt_fail/` 為隔離測試目錄，不在專案內。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit code | 版本／證據位置 |
| --- | --- | --- | --- |
| Review 未發現 blocking；advisory 一項已記錄於 review 報告並決定延後 | `ocaievo/`：`python3 scripts/bootstrap_env.py --check` | 0 | snap-2026-09-24-ocaievo-bootstrap／`docs/workflow/reviews/TASK-001.md` |
| 全套測試可執行（此時尚無測試檔，pytest 以「未收集到測試」結束屬預期） | `ocaievo/`：`.venv/bin/python -m pytest --version` | 0 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 未執行且刻意不做：`--recreate` 路徑未實跑（會刪除並重建 `.venv`，對已驗證環境具破壞性）；該分支僅在明確需要重建時使用，程式碼已由 Review 檢視。
- 未執行：Windows 佈局（`Scripts/python.exe`）無法在本機驗證；已以 `os.name` 分支處理並在 Review 記錄為未實機驗證。
