# TASK-026 測試紀錄

- task_id：TASK-026
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-launcher sha256:b1f771602b9dcc75f6b0269b17bb9401086929a84d7d83b22e64bfd805126ee5
- alternative_reason：**部分替代**——桌面圖示的雙擊體驗與桌面整合（圖示外觀、`xdg-open` 實際開啟瀏覽器）無法在無桌面自動化的環境驗證；本張以「真實子程序 ＋ 埠探測 ＋ PID 檔」自動驗證程序生命週期，並以可注入的 `opener`／`which`／`spawn` 驗證開啟瀏覽器的時機與順序，實際雙擊與瀏覽器開啟仍**未執行**（見「未執行或受阻」）。
- Task／Spec 版本：TASK-026 / SPEC-001 v0.4
- 測試邊界：（1）真實程序：以子程序啟動服務，觀察 PID 檔、`GET /api/health`、`POST /api/shutdown`、`stop.sh`、SIGTERM 與「再次啟動」；（2）單元：`read_pid`／`is_alive`／`is_running`／`wait_ready`／`open_browser` 與啟動器四種情況（已執行／啟動中／陳舊 PID／埠被別人佔用），全部使用 `tmp_path` 的 `EDIAAD_HOME` 與臨時埠，不碰使用者的服務。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-024 的交付物，全套 **753 passed**（本張完成後為 **778 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `92a48f6f6039b811521ef6b55d0a6491742e0679922f311fa5f8a14c104f241b`（67 個檔案）。
- TDD 不適用的理由與替代驗證（若有）：見「未執行或受阻」第 1 點（桌面圖示與瀏覽器實際開啟）。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/launcher.py` | `ee899bec` | 新增：`main`（一鍵啟動）、`serve_main`／`--serve`（服務程序本體）、`is_running`／`read_pid`／`is_alive`／`port_is_open`／`wait_ready`／`open_browser`／`build_parser` |
| `ediaad/app.py` | `664418bd` | 修改：`pid_path` 欄位、`shutdown_event`、`write_pid_file`／`remove_pid_file`／`request_shutdown`／`install_signal_handlers`／`shutdown` |
| `ediaad/paths.py` | `a9b66427` | 修改：`pid_path`（`<home>/ediaad.pid`） |
| `ediaad/web/routes.py` | `76a558aa` | 修改：`POST /api/shutdown` |
| `scripts/ediaad_launcher.py` | `baab3c2a` | 新增：薄入口（補 `sys.path` 後呼叫 `launcher.main`） |
| `stop.sh` | `4d998aa4` | 新增：讀 PID 檔 → SIGTERM → 等待 → 必要時 SIGKILL → 清除 PID 檔 |
| `ediaad.desktop` | `a00146a9` | 新增：桌面圖示（指向啟動器） |
| `ediaad/web/static/index.html` | `a87a8423` | 修改：「服務」區塊與「關閉服務」按鈕 |
| `ediaad/web/static/app.js` | `9a794d51` | 修改：按鈕 → `POST /api/shutdown` 與文字狀態 |
| `tests/test_launcher_lifecycle.py` | `af3f7771` | 新增：25 個測試（含 8 個真實程序／腳本的整合案例） |

## Cycle 1：啟動器與判定（AC-049，真實 Red → Green）

- 測試（20 個）：`is_running` 在沒有 PID 檔且沒有服務時為 `False`；`read_pid` 對缺檔／非數字／負數／0 回 `None`、對正常內容回整數；`is_alive` 對自己為真、對已結束的子程序與不存在的 PID 為假、對 `0`／負數為假；`is_running` 需要「程序活著 **且** health check 通過」（程序活著但沒有服務 → 假；真服務 → 真；埠上只有別人的 listener → 假）；`wait_ready` 對無人服務的埠在逾時後回 `False`（且不拖太久）、對真實服務回 `True`、**對不會說 HTTP 的外來 listener 回 `False`**；`open_browser` 依序找 `xdg-open`／`firefox`／`google-chrome`，找不到時回 `False` 而不丟例外；啟動器三種情況：已在執行只開瀏覽器（**不啟第二個程序**，PID 不變）、陳舊 PID 檔視為未啟動並覆寫、埠被別的程序佔用回 exit 2 且不啟子程序、就緒逾時回 exit 1 並終止自己的子程序；`Application.write_pid_file`／`remove_pid_file` 只動自己的 PID 檔。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_launcher_lifecycle.py -q` | 2 | collection error：`ImportError: cannot import name 'launcher'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `20 passed in 12.08s` | snap-2026-09-24-ocaievo-launcher／2026-09-24 |

- 實作：`ediaad/launcher.py`（判定與啟動流程、`--serve` 服務程序本體）、`ediaad/app.py`（PID 檔、關閉事件、訊號、`shutdown()`）、`ediaad/paths.py`（`pid_path`）、`scripts/ediaad_launcher.py`、`ediaad.desktop`。
- **`is_running` 的兩半語意不同（本張最重要的判定設計）**：PID 檔那一半用 `read_pid` ＋ `is_alive`（**含殭屍判斷**），埠那一半用 `/api/health`。純 TCP 探測（`port_is_open`）只用在「埠被別的程序佔用」的判斷上——若把「有沒有人接受連線」當成「我們的服務在跑」，外來 listener 就會被誤判為已啟動（測試 `test_is_running_requires_a_live_process_and_a_responding_service` 與 `test_wait_ready_does_not_accept_a_foreign_listener` 分別固定這兩件事）。
- **殭屍程序是真實缺陷，不是理論問題**：`os.kill(pid, 0)` 對「已結束但還沒被回收」的程序仍然成功。第一版就是這樣讓 `test_shutdown_endpoint_stops_the_service` 失敗（子程序已關閉，但測試程序還沒 `wait()` 它，於是 `is_alive` 永遠為真）。已改為再讀 `/proc/<pid>/stat` 的狀態欄（`Z` 視為已結束），並在 `stop.sh` 做同樣的判斷（`kill -0` 對殭屍也會成功）。
- **啟動器四種情況都有測試**：已執行（只開瀏覽器、PID 不變、不 spawn）、啟動中（PID 活著但還沒就緒 → 等它）、陳舊 PID（覆寫並啟動）、埠被別的程序佔用（exit 2、不 spawn、訊息含埠號）。
- **如實記載的自傷**：`home` fixture 的清理邏輯會讀 PID 檔並送 SIGTERM，但有三個測試刻意把自己的 PID 寫進 PID 檔（判定用），於是清理時**對 pytest 自己送訊號**——測試跑到一半整個行程被殺、輸出中斷。已加 `pid != os.getpid()` 的守衛，並把清理升級為「等待逾時後 SIGKILL」，避免留下程序。

## Cycle 2：優雅關閉與網頁按鈕（AC-050，真實 Red → Green）

- 測試（5 個）：`Application.shutdown()` 會停止服務、關閉資料庫並移除 PID 檔（埠在 `shutdown` 後釋放）；`POST /api/shutdown` 回 200／`shutting_down`，服務程序在期限內結束、PID 檔被清除、埠釋放；SIGTERM 單獨就能讓服務**自己**優雅結束並移除 PID 檔（不靠 SIGKILL）；首頁有「關閉服務」按鈕且 `app.js` 打的是 `/api/shutdown`；`stop.sh` 可執行、缺 PID 檔時回「找不到 PID 檔」、內容損毀時回「無法解讀」並清除、對忽略 SIGTERM 的程序會在逾時後 SIGKILL 並清除 PID 檔、正常情況在 8 秒內完成（走優雅路徑而不是等到逾時）。
- 真實入口腳本的整合案例：`python3 scripts/ediaad_launcher.py --no-browser` 第一次啟動成功、第二次是 no-op（PID 不變）；`./stop.sh` 之後 PID 檔清除、埠釋放、**再次啟動成功且是新的程序**。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `18 passed, 1 failed`：`/api/shutdown` 回 200 但服務沒有結束（殭屍判定缺陷） | 同上／2026-09-24 |
| Green | 同上 | 0 | `25 passed in 18.34s` | 同上／2026-09-24 |

- 實作：`Application.shutdown()`（`stop()` → `close()` → **最後**移除 PID 檔；順序有意義：PID 檔留到最後，讓「還在服務但正在關閉」的窗口仍被視為已啟動）、`request_shutdown()`／`install_signal_handlers()`（SIGTERM／SIGINT 與網頁按鈕走同一個事件）、`routes.shutdown`（只設定事件並立刻回應，真正的停止由服務主迴圈執行）、`index.html`／`app.js` 的按鈕、`stop.sh`。
- **`--serve` 與 TASK-036 的關係**：啟動器需要「一個可以背景執行的服務程序」，而 CLI 的 `serve` 子命令屬 TASK-036。本張把服務程序本體放在 `launcher.serve_main`（`--serve`），TASK-036 的 `serve` 應呼叫**同一個函式**而不是再寫一套（已寫在模組 docstring 與 Review 的 advisory）。
- **`--no-browser` 是為了可測性也是實用選項**：沒有桌面環境（或 CI）時只啟動服務不開瀏覽器，因此真實入口腳本可以被自動測試。

## 變異測試（兩階段：先殺存活者，再跑凍結版）

- 工具：`/tmp/mutate_task026.py`（整行替換、`count(frm) == 1` 才套用、每輪逾時 180 秒、跑完立即還原並比對 sha256、`flock` 確保單一行程）。
- 矩陣：**30 個變異**（`launcher.py` 18、`app.py` 4、`routes.py` 2、`stop.sh` 4、`index.html`／`app.js` 各 1），涵蓋 PID 解析與殭屍判斷、`is_running` 的兩半、`wait_ready` 的 health check、瀏覽器尋找鏈、`_serve_command` 的參數、PID 檔寫入與「只移除自己的」、關閉事件、`shutdown()` 的順序、`/api/shutdown` 的行為與狀態、`stop.sh` 的 SIGTERM／SIGKILL／清理／PID 解析、按鈕與端點的接線。
- **第一階段抓到 2 個真實存活者並補強測試擊殺**：
  1. `L16`（「程序活著但還沒就緒」的分支拿掉）存活——原本的 `is_running` 用純 TCP 探測，於是「我們的程序活著 ＋ 埠被外來 listener 佔用」被當成「已在服務」而直接開瀏覽器，兩種分支的差異沒有測試。已把 `is_running` 的埠那一半改成 health check，並新增 `test_live_pid_with_a_foreign_listener_reports_a_startup_failure`（要回 exit 1 且訊息不得說「已被其他程序佔用」）。
  2. `S03`（`stop.sh` 只把「空字串」視為損毀）存活——損毀的 PID 檔會走「程序已不存在」分支，訊息不同但測試沒斷言。已補「必須出現『無法解讀』」的斷言。
- **1 個判讀為等價、並已說明的存活者**：`L18`（`main` 最前面的 `is_running` 快速路徑拿掉）。移除後「已在服務」的情況會落到「PID 檔指向活著的程序 → `wait_ready` → 開瀏覽器」，而 `wait_ready` 用的正是 `is_running` 那半的 health check，因此**每一個輸入的結果都相同**（服務在跑 → 開瀏覽器；程序在但沒就緒 → exit 1）。保留快速路徑的理由是它讓 AC 的「PID 檔與埠探測共同判定」在程式碼裡一眼可見，且 `is_running` 是 SPEC 第 5 節列出的公開介面。已在此如實記載為等價變異，不是測試缺口。
- **另有一處在跑之前移除的冗餘碼**：`open_browser` 原本有 `opener` 參數，但注入其實發生在 `main`（`open_browser` 的分支永遠不會被測試走到）→ 已移除該參數，只留 `which`／`spawn` 兩個真正被使用的注入點。
- **最終凍結版結果：30 個變異中 29 個偵測到、1 個等價（`L18`）、0 個無效**（`L05` 第一次因為我改了 `is_running` 的實作而字串失效，修正字串後在**同一份凍結檔案**上重跑並偵測到，逐輪輸出形如 `24 passed, 1 failed`）。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `.venv/bin/python -m pytest tests/test_launcher_lifecycle.py -q` | 0 | `25 passed in 18.34s` |
| `.venv/bin/python -m pytest -q` | 0 | `778 passed, 2 warnings in 131.87s` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |

## 未執行或受阻

1. **桌面圖示的實際雙擊與瀏覽器開啟未執行**（無桌面自動化、也不應在使用者的工作階段裡真的開瀏覽器）：`ediaad.desktop` 只有內容斷言（`Type=Application`、`Exec=` 指向啟動器、`Terminal=false`），`open_browser` 的實際開啟以注入的 `which`／`spawn` 驗證。交付前應在 Wayland 桌面雙擊一次，確認瀏覽器開啟且 `ss -ltnp` 顯示 8787 由 ediaad 持有，並各按一次「關閉服務」與 `./stop.sh`。
2. **`ediaad.desktop` 的 `Exec` 是絕對路徑**（本專案檢出的位置）；若專案搬到別的路徑需同步修改，且沒有自動檢查能發現（已在檔案內註解說明）。
3. **`stop.sh` 的等待上限是政策而非契約**（`EDIAAD_STOP_TIMEOUT` 預設 10 秒）：測試固定「正常情況 8 秒內完成」與「逾時後 SIGKILL 並清理」，但沒有（也不該）斷言精確秒數。
