# TASK-011：match／monitor 子命令、JSON 報表與效能門檻

- id：TASK-011
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-027","AC-028","AC-029"]
- depends_on：["TASK-005", "TASK-006", "TASK-010"]
- test_evidence：["docs/workflow/tdd/TASK-011.md"]
- review_evidence：["docs/workflow/reviews/TASK-011.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：在專案根執行 `.venv/bin/python -m ediaad match --data <csv> --sample <csv> --top N --horizon H --out report.json` 時 exit 0，且 `report.json` 的頂層鍵恰為 `sample`、`params`、`data_source`、`matches`、`outlook` 五個；輸入檔不存在或參數不合法時 exit 2，輸出檔不可寫時 exit 1。`.venv/bin/python -m ediaad monitor --config <json> --once` 單次執行 exit 0 並在 stdout 印出單行摘要，設定錯誤 exit 2、來源失敗 exit 1；常駐模式（不加 `--once`）收到 `SIGINT` 時不印 traceback 並以 exit 0 優雅結束。以 10,000 根序列、視窗 60、top 20 執行 `match` 並計時，在同一台開發機 60 秒內完成，且命中索引與 `outlook` 統計與小資料集的行為一致。
- 本張不做：不建立 `serve` 與 `license` 子命令（TASK-036）；不接 `ediaad.markets` registry 或任何網路來源，`match` 只讀本地 CSV 且 `data_source` 固定標示 `csv`（來源分派屬 TASK-012 之後）；不改動 `scan`、`outlook`、`monitor` 的核心邏輯，只呼叫其公開函式；不新增 JSON 報表五鍵以外的欄位；不執行 git 或任何對外動作。
- 每個 AC 在本張負責的範圍：AC-027 全部（`match` 子命令、五鍵 JSON 報表、三種 exit code 語意）；AC-028 全部（`monitor --once` 與常駐模式的摘要、exit code 與中斷處理）；AC-029 全部（10,000 根的實際計時紀錄與結果一致性）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-027～AC-029、第 5 節「輸入／輸出、驗證與錯誤格式」的 CLI exit code 規則（0 成功、1 執行期失敗、2 輸入或設定錯誤）與第 6 節效能需求（`match` 於 10,000 根 60 秒內）；`docs/architecture/ENGINEERING-REPORT.md` 第 3.1 節 F14（兩個子命令、exit code 表、報表五鍵）、第 4.5 節資料流 A 與資料流 B；`docs/workflow/PROJECT.md` 的執行指令表與環境實測表。
- 模組與公開介面：新增 `ediaad/cli.py`（`build_parser`、`main`）與 `ediaad/__main__.py`（`python -m ediaad` 入口）；只呼叫既有公開介面 `data.load_csv`、`features.extract` 與 `extract_matrix`、`scan.scan_similar`、`outlook.forward_stats`、`monitor.load_config`／`run_once`／`run_forever`／`format_alert`，不重複實作任何核心邏輯。
- 預計觸及的檔案：`ediaad/cli.py`、`ediaad/__main__.py`、`tests/test_cli_match_monitor.py`，必要時同步 `docs/workflow/PROJECT.md` 的指令表狀態；實作前重新查證。
- 必要環境／依賴：`.venv`（TASK-001）內 `numpy`、`pandas`、`pytest`；TASK-005（`scan_similar`）、TASK-006（`forward_stats`）、TASK-010（`load_config`／`run_once`／`run_forever`／`format_alert`）已完成；效能案例以 `tmp_path` 產生的合成 CSV 執行，全程離線。

## 測試計畫

- 測試公開邊界：以 `subprocess` 執行 `.venv/bin/python -m ediaad`（`match` 與 `monitor`）並觀察 exit code、stdout 摘要與 `report.json` 檔案內容；不直接呼叫 `cli.main` 的內部輔助函式。
- 第一個失敗行為與預期斷言：在 `ediaad/__main__.py` 尚未存在時執行 `python -m ediaad match --data a.csv --sample b.csv --top 5 --horizon 20 --out report.json`，預期 exit 1（`No module named ediaad`）；實作後對合成合法 CSV 執行同一命令，預期 exit 0，且 `set(json.load(open("report.json")).keys()) == {"sample", "params", "data_source", "matches", "outlook"}`。
- 後續例外／邊界情境：`--data` 指向不存在的檔案、`--top 0`、`--horizon -1` 各自 exit 2 且 stderr 指出不合法處；`--out` 指向 `tmp_path` 下權限 `0500` 的目錄時 exit 1 且不留下半寫報表；`monitor --once` 對含未知鍵的設定 exit 2、對注入失敗的 `fetch` exit 1；常駐 `monitor` 送出 `SIGINT` 後 exit 0 且輸出無 traceback；10,000 根案例記錄實際秒數並斷言小於 60 秒，同時斷言其命中索引與 `outlook` 欄位和 200 根小資料集的對應結果一致。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_cli_match_monitor.py -q`；相關回歸 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用（本張全部是可程式驗證的 CLI 行為與計時，無需人工檢查）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-010 的交付物（全套 187 passed）；本次新增 `ediaad/cli.py`、`ediaad/__main__.py` 與 `tests/test_cli_match_monitor.py`（開工時以 `find . -type f -not -path "./.venv/*" | sort` 與逐檔 sha256 建立快照；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-011.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-011.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-cli-match-monitor` sha256:3ef139627e2fd953dc1b3b8e1db07b538ca531f193fb3fcea9308e8d7eeedbce（原始碼樹，25 檔；計算方式見 `docs/workflow/PROJECT.md`「版本標記的計算慣例」）；本張交付 `ediaad/cli.py` `672ace72…`、`ediaad/__main__.py` `5a437844…`、`tests/test_cli_match_monitor.py` `f3e68536…`；全套 `208 passed`；AC-029 實測 10,000 根／視窗 60／top 20 耗時 3.86 秒
- 取消、重開或變更原因：無
