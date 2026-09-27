# TASK-036：CLI serve 與 license 子命令

- id：TASK-036
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-064"]
- depends_on：["TASK-011", "TASK-020", "TASK-030", "TASK-032"]
- test_evidence：["docs/workflow/tdd/TASK-036.md"]
- review_evidence：["docs/workflow/reviews/TASK-036.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`python -m ediaad` 的子命令存在且 exit code 語意一致——`serve` 啟動本機服務；`license status`、`license activate --key ...`、`license renew [--trigger ...]` 分別對應 TASK-030／TASK-031 的既有函式；exit code 0 表示成功、1 表示執行期失敗（網路或來源失敗、輸出不可寫）、2 表示輸入或設定錯誤（密鑰格式、參數不合法、設定或租約檔損毀）。所有錯誤轉為單行可讀訊息並寫 stderr，不吐 traceback；`--help` 與各子命令 `--help` 皆 exit 0。
- 本張不做：不重實作既有 `match`／`monitor` 子命令（TASK-011）；不實作 HTTP 服務、SSE 或靜態資源（TASK-020、TASK-021）；不實作授權邏輯、驗章、時鐘防護或續期判定（TASK-028～TASK-031）；不實作更新檢查（TASK-032）；不做桌面啟動器、PID／埠防護與 `stop.sh`（TASK-026，本張的 `serve` 只負責啟動與參數轉譯）；不做 GUI 或互動式提示（密鑰以參數傳入，不從 stdin 讀取以免進入 shell 歷史）。
- 每個 AC 在本張負責的範圍：AC-064 全部（`serve` 與 `license status／activate／renew` 子命令存在、行為與 exit code 語意一致）。子命令背後的核心行為分別由 TASK-020（serve）、TASK-030（activate／status 的狀態判定）、TASK-031（renew）與 TASK-032（更新檢查）負責，本張不重複其驗證，只在 CLI 邊界上驗 exit code 與訊息。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-064、第 5 節模組表 `ediaad/cli.py`（`build_parser`、`main`）與「CLI exit code：0 成功、1 執行期失敗、2 輸入或設定錯誤」、第 3 節主要流程步驟 3（`python -m ediaad serve`）與步驟 8（續期與更新）、第 7 節測試策略列（CLI 以端到端子程序測試）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.1 節元件圖（`cli.py` 保留並新增 `serve` 與 `license` 子命令）、第 6.4 節（三個觸發點，`license renew --trigger manual` 對應 `manual`）；`docs/workflow/PROJECT.md` 執行指令表（`serve` 啟動命令、`EDIAAD_PORT`／`EDIAAD_HOME` 環境變數、`stop.sh` 屬 TASK-026）。
- 模組與公開介面：`ediaad/cli.py` 既有的 `build_parser() -> argparse.ArgumentParser` 與 `main(argv=None) -> int`（回傳 exit code，由 `ediaad/__main__.py` 轉成 `sys.exit`）；新增子命令
  - `serve`：參數 `--port`（預設 `EDIAAD_PORT` 或 8787，只 bind `127.0.0.1`）、`--home`（預設 `EDIAAD_HOME`），內部呼叫 TASK-020 的 `Application.start()`／`create_server`。
  - `license status`：唯讀顯示 `lease_status` 結果與剩餘天數，**不發出網路請求**。
  - `license activate --key <KEY>`：呼叫 TASK-030 的 `activate`，成功後印出租約到期日。
  - `license renew [--trigger manual|timer|start]`（預設 `manual`）：呼叫 TASK-031 的 `renew`。
  - 錯誤轉譯集中在一處：`ConfigError` → 2、`SourceError` → 1、其他 `EdiaadError` → 1，未知例外只印可讀訊息（不印 traceback）。
- 預計觸及的檔案：`ediaad/cli.py`、`ediaad/__main__.py`、`tests/test_cli_serve.py`、`tests/test_cli_license.py`；必要時 `tests/_ed25519_fixture.py`（沿用 TASK-030 的簽章夾具）；實作前重新查證既有 `match`／`monitor` 子命令的命名與 `PROJECT.md` 指令表是否一致。
- 必要環境／依賴：`.venv`＋`pytest`；子程序測試以 `sys.executable` 執行 `-m ediaad`，`EDIAAD_HOME` 指向 `tmp_path`；`license activate`／`renew` 的成功情境以測試內啟動的 loopback 假授權服務（`http.server` 綁 `127.0.0.1:0`，回傳測試夾具簽章的租約或 403），全程不連外網。

## 測試計畫

- 測試公開邊界：以 `subprocess.run([sys.executable, "-m", "ediaad", ...], capture_output=True, text=True, env=...)` 觀察 exit code 與 stdout／stderr；另以 `build_parser()` 驗證子命令與參數樹（不直接呼叫 `main` 內部的私有函式）。
- 第一個失敗行為與預期斷言：子命令尚未註冊時執行 `python -m ediaad license status` 得到 argparse 用法錯誤的 exit 2、stderr 含 `invalid choice`；實作後同一命令在 `EDIAAD_HOME` 指向 `tmp_path`（無租約）時 exit 2 並附「尚未啟用」的可讀訊息，或在有有效租約時 exit 0 並列出狀態與剩餘天數。
- 後續例外／邊界情境：
  1. `serve`：`EDIAAD_PORT` 已被佔用 → exit 1 並附可讀訊息；未佔用時可 bind `127.0.0.1`、在 10 秒內就緒（以 TASK-020 的就緒探測為準），收到中斷訊號後優雅結束且 exit 0。
  2. `license activate`：缺 `--key` → exit 2；假服務回 403（已撤銷）→ exit 2 且**不落地** `lease.json`；假服務不可達 → exit 1；成功 → exit 0 且 `lease.json` 存在並可被 TASK-030 的驗證接受。
  3. `license renew`：成功 → exit 0 且 `lease.json` 的 `expires_at` 重算為 `now + 30 天`；假服務對過期租約回 403 → 依 SPEC exit code 語意明確定義（輸入／狀態錯誤為 2）並以測試固定；逾時 → exit 1 且不修改既有租約。
  4. `--trigger` 非法值 → argparse exit 2；未提供時預設 `manual`。
  5. 損毀的 `lease.json`／`settings.json` → exit 2，訊息指出檔名與問題，且不覆蓋原檔。
  6. `python -m ediaad --help`、`serve --help`、`license --help`、`license activate --help` 皆 exit 0。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_cli_serve.py tests/test_cli_license.py -q`；人工複核子程序 `.venv/bin/python -m ediaad license status`（先將 `EDIAAD_HOME` 指向測試目錄）；回歸 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用，exit code 與訊息皆可在子程序層先寫 Red。
- 必要的人工檢查：`python -m ediaad serve` 後以瀏覽器開啟 `http://127.0.0.1:8787` 的實際互動屬 AC-041～AC-050（TASK-020～TASK-026），不在本張範圍；本張只驗子程序層的 exit code、就緒與優雅結束。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-035 與 TASK-025 的交付物（Python 全套 **971 passed**、Node **82 passed**），檔案樹 sha256 `45876364bc01a9749bb4597dcbd6f98453525f31b72ac3b2710a0d5dc4ff78f5`（119 檔，即 TASK-035 的 `checked_version`）。本次新增 `tests/test_cli_serve.py`／`tests/test_cli_license.py`／`tests/_cli_helpers.py`，修改 `ediaad/cli.py`（`serve` 與 `license` 子命令）、`ediaad/launcher.py`（啟動時的離線授權驗證與 features 分級）、`ediaad/license.py`（`HTTP_CLIENT`／`public_key_from_env`／`load_lease` 的檔名訊息）、`ediaad/web/routes.py`（預設客戶端修正）與三個既有測試檔（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-036.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-036.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-cli-serve-license` sha256:ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab（原始碼樹，122 檔）；`ediaad/cli.py` `d0dcc0a2…`、`ediaad/launcher.py` `8f43da1b…`、`ediaad/license.py` `aa609934…`、`ediaad/web/routes.py` `ef01c2f9…`、`tests/test_cli_serve.py` `a8573484…`、`tests/test_cli_license.py` `b3d524f8…`、`tests/_cli_helpers.py` `8f0e81d5…`、`tests/test_web_watchlist_status.py` `4b2ab6ce…`、`tests/test_notify.py` `8f942fe4…`、`tests/test_update.py` `91eb6f4b…`；Python 全套 **1007 passed**、Node `node --test` **82 passed**；變異矩陣 24 個 → **24 偵測到**（0 存活、0 無效）
- 取消、重開或變更原因：無（第 1 輪 Review 修正 TASK-025 遺留的預設 HTTP 客戶端缺陷、`load_lease` 的檔名、可設定的簽章公鑰，以及三處跨 Task 的測試／替身更新）
