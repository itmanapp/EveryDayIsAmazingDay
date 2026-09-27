# TASK-026：桌面一鍵啟動、重複啟動防護與優雅關閉

- id：TASK-026
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-049","AC-050"]
- depends_on：["TASK-020"]
- test_evidence：["docs/workflow/tdd/TASK-026.md"]
- review_evidence：["docs/workflow/reviews/TASK-026.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：執行 `python3 scripts/ediaad_launcher.py` 時，服務未啟動的情況會以背景子程序啟動服務、等待就緒（health check，最多 10 秒）後才呼叫瀏覽器開啟 `http://127.0.0.1:8787`；服務已啟動時只開瀏覽器、不啟第二個程序；是否已在執行由 PID 檔（`$EDIAAD_HOME/ediaad.pid`）加埠探測共同判定；按網頁「關閉服務」按鈕或執行 `./stop.sh` 都能優雅結束服務、清除 PID 檔、釋放 8787 埠，之後可再次啟動成功。
- 本張不做：不做登入自動常駐與 systemd 單元（報告第 6.2 節明確不做）、不改監控迴圈與網頁既有行為、不做三管道通知（TASK-027）、不做授權驗證與到期停止（TASK-030／031）、不做更新檢查（TASK-032）；不建立對外位址、不開 HTTPS、不在未取得就緒前搶先開瀏覽器。
- 每個 AC 在本張負責的範圍：AC-049 全部（未啟動時背景啟服務、等就緒最多 10 秒、開瀏覽器；已啟動時只開瀏覽器不啟第二個；PID 檔與埠探測防止重複啟動）；AC-050 全部（網頁按鈕與 `stop.sh` 的優雅結束、PID 清除、埠釋放、可再次啟動）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-049／AC-050、第 5 節 `ediaad/launcher.py`（`main`、`is_running`、`wait_ready`）與 `ediaad/app.py`（`Application`、`start`、`stop`）、第 6 節效能（啟動就緒等待上限 10 秒）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.2 節服務生命週期與啟動器（PID 檔、埠佔用偵測、重複啟動防護、就緒等待與優雅關閉）與第 6.1 節元件圖；`docs/workflow/PROJECT.md` 的執行指令表（`python3 scripts/ediaad_launcher.py`、`./stop.sh`）與環境實測（`xdg-open`、`firefox`、`google-chrome` 存在；`DISPLAY=:0`、`WAYLAND_DISPLAY`、`XDG_SESSION_TYPE=wayland`）。
- 模組與公開介面：新增 `ediaad/launcher.py`（`main(argv=None) -> int`、`is_running(pid_path, port) -> bool`、`wait_ready(port, timeout=10.0) -> bool`、`open_browser(url)` 以 `subprocess` 呼叫 `xdg-open`，路徑與 opener 皆可注入以利測試）與薄入口 `scripts/ediaad_launcher.py`；新增 `stop.sh`（讀 PID 檔、送終止訊號、等待程序結束並清理）與 `ediaad.desktop` 桌面檔；`ediaad/app.py` 的 `Application` 需提供寫入／移除 PID 檔及處理 `SIGTERM`／`SIGINT` 的優雅關閉路徑（關閉監控執行緒、HTTP 服務與 SQLite 連線後才移除 PID 檔）；`ediaad/web/routes.py` 新增 `POST /api/shutdown` 觸發同一條關閉路徑。
- 預計觸及的檔案：`ediaad/launcher.py`、`scripts/ediaad_launcher.py`、`stop.sh`、`ediaad.desktop`、`ediaad/app.py`、`ediaad/web/routes.py`、`tests/test_launcher_lifecycle.py`；實作前重新查證（特別是 TASK-020 是否已提供可安全呼叫的 `Application.stop()`）。
- 必要環境／依賴：TASK-020 的 `Application` 與 `create_server`；標準庫 `subprocess`、`os`、`signal`、`socket`、`time`；測試使用 `tmp_path` 的 PID 檔與非 8787 的臨時埠，`open_browser` 以注入的假函式取代，避免真的開啟瀏覽器或動到使用者正在執行的服務。

## 測試計畫

- 測試公開邊界：以子程序真實啟動與停止服務並以 socket 連線探測埠，觀察 PID 檔、exit code 與程序生命週期；`open_browser` 以假函式記錄被呼叫的 URL。
- 第一個失敗行為與預期斷言：先寫「PID 檔不存在且埠無人監聽時，`ediaad.launcher.is_running(pid_path, port)` 回 `False`」。實作前執行 `.venv/bin/python -m pytest tests/test_launcher_lifecycle.py -q` 預期收集期失敗 `ModuleNotFoundError: No module named 'ediaad.launcher'`；實作後回 `False`，且未啟動情境下 `python3 scripts/ediaad_launcher.py` exit 0、就緒後才記錄到一次 `open_browser` 呼叫。
- 後續例外／邊界情境：就緒等待逾時（超過 10 秒）要回報失敗並終止自己啟動的子程序，不留孤兒程序；陳舊 PID 檔（程序已不存在）視為未啟動並可安全覆寫；8787 被非 ediaad 的程序佔用時不得誤判為「已在執行」，需回可讀錯誤；已啟動時再次執行啟動器不得產生第二個程序（以程序數與埠擁有者驗證）；`stop.sh` 與 `POST /api/shutdown` 後 PID 檔被清除、埠釋放且可再次啟動成功。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_launcher_lifecycle.py -q`；相關回歸 `.venv/bin/python -m pytest -q`；實際啟動沿用 `docs/workflow/PROJECT.md` 的 `python3 scripts/ediaad_launcher.py` 與 `./stop.sh`。
- 非程式任務的替代驗證與理由：不適用（程序生命週期可以子程序與埠探測自動驗證）；另依 SPEC 第 7 節人工檢查第 2 項，實際雙擊桌面圖示觀察瀏覽器開啟、按「關閉服務」與執行 `./stop.sh` 後以 `ss -ltnp` 或 socket 連線確認 8787 已釋放，並記錄結果。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-024 的交付物（全套 **753 passed**），檔案樹 sha256 `92a48f6f6039b811521ef6b55d0a6491742e0679922f311fa5f8a14c104f241b`（67 檔）；本次新增 `ediaad/launcher.py`、`scripts/ediaad_launcher.py`、`stop.sh`、`ediaad.desktop`、`tests/test_launcher_lifecycle.py`，並修改 `ediaad/app.py`、`ediaad/paths.py`、`ediaad/web/routes.py`、`ediaad/web/static/index.html`、`ediaad/web/static/app.js`（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-026.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-026.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-launcher` sha256:b1f771602b9dcc75f6b0269b17bb9401086929a84d7d83b22e64bfd805126ee5（原始碼樹，72 檔）；`ediaad/launcher.py` `ee899bec…`、`ediaad/app.py` `664418bd…`、`ediaad/paths.py` `a9b66427…`、`ediaad/web/routes.py` `76a558aa…`、`scripts/ediaad_launcher.py` `baab3c2a…`、`stop.sh` `4d998aa4…`、`ediaad.desktop` `a00146a9…`、`ediaad/web/static/index.html` `a87a8423…`、`ediaad/web/static/app.js` `9a794d51…`、`tests/test_launcher_lifecycle.py` `af3f7771…`；全套 **778 passed**；變異矩陣 30 個（29 偵測到、1 等價）
- 取消、重開或變更原因：無
