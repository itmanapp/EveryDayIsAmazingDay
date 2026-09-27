# TASK-026 Code Review

- task_id：TASK-026
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-launcher sha256:b1f771602b9dcc75f6b0269b17bb9401086929a84d7d83b22e64bfd805126ee5
- Task／Spec 版本：TASK-026 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含殭屍程序缺陷、`is_running` 兩半語意的修正與變異存活者的處理）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `92a48f6f6039b811521ef6b55d0a6491742e0679922f311fa5f8a14c104f241b`（67 個檔案）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `b1f771602b9dcc75f6b0269b17bb9401086929a84d7d83b22e64bfd805126ee5`（72 個檔案）；本張新增 `ediaad/launcher.py` `ee899bec…`、`scripts/ediaad_launcher.py` `baab3c2a…`、`stop.sh` `4d998aa4…`、`ediaad.desktop` `a00146a9…`、`tests/test_launcher_lifecycle.py` `af3f7771…`；修改 `ediaad/app.py` `664418bd…`、`ediaad/paths.py` `a9b66427…`、`ediaad/web/routes.py` `76a558aa…`、`ediaad/web/static/index.html` `a87a8423…`、`ediaad/web/static/app.js` `9a794d51…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：上述十個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`config.py`／`store.py`／`monitor.py`／`patterns.py`／`markets/*`／`web/server.py`／`web/sse_hub.py` 本張只呼叫未修改
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-049／AC-050、第 5 節 `ediaad/launcher.py`（`main`／`is_running`／`wait_ready`）與 `ediaad/app.py`（`Application`／`start`／`stop`）、第 5 節依賴方向、第 6 節效能（就緒等待上限 10 秒）與可及性、第 7 節人工檢查第 2 項；`docs/workflow/PROJECT.md` 的執行指令表與環境實測（`xdg-open`／`firefox`／`google-chrome`、Wayland）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.1／6.2 節；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-049 | `ediaad/launcher.py`、`scripts/ediaad_launcher.py`、`ediaad.desktop`、`ediaad/app.py`（PID 檔）、`tests/test_launcher_lifecycle.py` 20 個案例 | 符合 | A-1～A-6（advisory） |
| AC-050 | `ediaad/app.py`（`shutdown`／訊號）、`ediaad/web/routes.py`（`POST /api/shutdown`）、`index.html`／`app.js`（按鈕）、`stop.sh`、`tests/test_launcher_lifecycle.py` 5 個案例 | 符合 | A-1、A-3、A-5、A-6（advisory） |

逐條核對：

- **AC-049「未啟動時背景啟服務、等就緒（最多 10 秒）、開瀏覽器」**：`main` 以 `_spawn_service` 啟動背景子程序（`start_new_session=True`，不隨啟動器結束），以 `wait_ready`（`GET /api/health`，預設上限 10 秒）等就緒，就緒後才呼叫 `open_browser`。測試 `test_launcher_starts_the_service_and_opens_the_browser_after_readiness` 在注入的 opener 裡**當場斷言埠已在回應**，因此「不得在未取得就緒前搶先開瀏覽器」是被直接證明的順序性質，而不是註解。符合。
- **AC-049「已啟動時只開瀏覽器，不啟第二個程序」**：`is_running`（PID 檔指向活著的程序 ＋ `/api/health` 通過）為真時只開瀏覽器；測試以 `spawn` 間諜斷言**沒有**任何 spawn 呼叫，且 PID 檔內容不變。符合。
- **AC-049「PID 檔與埠探測可防止重複啟動」**：PID 檔那一半用 `read_pid` ＋ `is_alive`（含殭屍判斷），埠那一半用 health check；另有「程序活著但還沒就緒 → 等它，不啟第二個」與「沒有我們的 PID 檔但埠被佔用 → exit 2，不啟子程序」兩條路徑，各有測試。符合。
- **AC-049 的例外情境**：就緒逾時會**終止自己啟動的子程序**（以假子程序斷言 `terminate` 被呼叫）；陳舊 PID 檔（程序已不存在或內容損毀）視為未啟動並可安全覆寫；8787 被非 ediaad 的程序佔用時回可讀錯誤且不誤判為「已在執行」。符合。
- **AC-050「按網頁按鈕或執行 `./stop.sh` 都能優雅結束、清除 PID 檔、釋放 8787 埠」**：`POST /api/shutdown` → `Application.request_shutdown()` → 服務主迴圈走 `Application.shutdown()`（`stop()` → `close()` → 移除 PID 檔）；`stop.sh` 送 SIGTERM、等待、必要時 SIGKILL、清除 PID 檔。兩條路徑都有「程序結束 ＋ PID 檔不存在 ＋ 埠釋放」的斷言；SIGTERM 單獨送達時服務也必須**自己**移除 PID 檔（不靠 stop.sh 的清理）。符合。
- **AC-050「之後可再次啟動成功」**：整合測試在 `./stop.sh` 之後再次執行啟動器，斷言 exit 0、新的 PID（與前一次不同）且就緒。符合。

## 品質 Review

- **「是否已在執行」的兩半語意不同，這是本張最重要的判定設計**：PID 檔那一半是「這個 PID 還活著嗎」（含殭屍），埠那一半是「這個埠上的服務真的是 ediaad 嗎」（`/api/health`）。純 TCP 探測（`port_is_open`）只用在「埠被**別的**程序佔用」的判斷——若把「有人接受連線」當成「我們的服務在跑」，外來 listener 就會被誤判為已啟動。這條界線由兩個測試分別固定（`test_is_running_requires_a_live_process_and_a_responding_service`、`test_wait_ready_does_not_accept_a_foreign_listener`），變異 `L07`（把 health check 換成 TCP 探測）也被抓到。
- **殭屍程序是真實缺陷，不是理論問題**：`os.kill(pid, 0)` 對「已結束但還沒被回收」的程序仍然成功。實作前 `test_shutdown_endpoint_stops_the_service` 就是這樣失敗的（子程序已關閉，但啟動器還沒 `wait()` 它，於是 `is_alive` 永遠為真）。修正為再讀 `/proc/<pid>/stat` 的狀態欄（`Z` 視為已結束），並在 `stop.sh` 的 `is_alive` 做同一件事——兩邊都必須處理，否則 `stop.sh` 會對殭屍空等 10 秒再 SIGKILL。變異 `L03`／`L04`（拿掉殭屍判斷）都被抓到。
- **關閉路徑只有一條**：網頁按鈕、SIGTERM、SIGINT 都設定同一個 `shutdown_event`，由服務主迴圈統一走 `Application.shutdown()`；`/api/shutdown` **只設定事件並立刻回應**（在 handler 裡直接關服務會讓瀏覽器收到連線中斷而不是明確結果）。變異 `A03`／`R01`（事件不被設定）與 `A04`（`shutdown()` 少一步）都被抓到。
- **PID 檔的兩個細節**：`write_pid_file` 先寫暫存檔再 `os.replace`（原子；啟動器可能在另一個行程讀它），`remove_pid_file` 只移除**內容是自己的 PID** 的檔案（否則真正在服務的程序會失去防護）。兩者都有測試，變異 `A01`／`A02` 也被抓到。
- **外部效果全部可注入**：`opener`／`spawn`（啟動器）與 `which`／`spawn`（`open_browser`）讓測試不需要真的開瀏覽器，也不會動到使用者正在執行的服務；`--no-browser` 讓真實入口腳本也能被自動測試。這符合 SPEC 第 5 節原則 2，也是「程序生命週期能用真實程序驗證、但不必真的開桌面」的關鍵。
- **`--serve` 與 TASK-036 的關係已先安排好**：服務程序本體放在 `launcher.serve_main`，模組 docstring 明確要求 TASK-036 的 `serve` 子命令呼叫同一個函式（不要再寫第二套）。這是跨 Task 的重用約定，已列入 advisory A-4。
- **冗餘碼的移除**：`open_browser` 原本有 `opener` 參數，但注入其實發生在 `main`，該分支永遠不會被走到 → 已移除，只留真正被使用的 `which`／`spawn`。
- **可及性**：按鈕是原生 `<button type="button">`、狀態用 `aria-live`、結果以文字表達（不依賴顏色）。符合 SPEC 第 6 節。
- **變異測試的強度**：30 個變異中 29 個被抓到，1 個（`L18`，`main` 最前面的快速路徑）判讀為**等價**並已在 TDD 紀錄說明理由（移除後同一個情況會落到「PID 檔指向活著的程序 → `wait_ready` → 開瀏覽器」，而 `wait_ready` 用的正是同一個 health check，因此所有輸入的結果相同）；保留它的理由是讓 AC 的「共同判定」在程式碼裡一眼可見。第一階段另有 2 個真實存活者（`L16`、`S03`）已各補一個行為斷言擊殺。
- **測試品質**：以真實子程序 ＋ 埠探測觀察程序生命週期（這是唯一能驗證生命週期的方式），以 `tmp_path` 的 `EDIAAD_HOME` 與臨時埠隔離，fixture 保證收乾淨（等待逾時後升級 SIGKILL）。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 缺口（沿用 TASK-013 A-1～TASK-024 A-1） | advisory（**需在後續 Task 處理**） | 服務仍不會自己跑監控：`run_once` 沒人呼叫、`Store` 寫入端未接、沒有 `GET/POST /api/watchlist`；非 CSV 來源仍拿不到 `cache_dir`。本張只把「啟動／停止」接起來 | TASK-025 應完成監控執行緒、`Store` 讀寫、監控清單端點、系統狀態頁與各來源 `cache_dir` 接線 | 待辦（已記於 `STATE.md` 待決事項） |
| A-2 | 桌面整合 | advisory（**未執行**） | `ediaad.desktop` 只有內容斷言；雙擊圖示、瀏覽器實際開啟、`ss -ltnp` 確認埠擁有者皆未人工檢查 | 交付前在 Wayland 桌面雙擊一次，並各按一次「關閉服務」與 `./stop.sh` | 待辦（替代驗證已記錄於 TDD） |
| A-3 | `Exec` 的絕對路徑 | advisory | `ediaad.desktop` 的 `Exec`／`Path` 是本專案檢出的絕對路徑；專案搬移後需手動同步，且沒有自動檢查能發現 | 若要隨處可用，可改為由安裝腳本產生桌面檔（目前沒有安裝流程，屬交付後事項）；已在檔案內註解說明 | 已記錄（檔案內註解） |
| A-4 | 跨 Task 重用約定 | advisory（需追認） | `serve_main`（`--serve`）與 TASK-036 的 CLI `serve` 子命令是同一件事的兩個入口 | TASK-036 的 `serve` 必須呼叫 `launcher.serve_main`（或等價的共用函式），不要再寫第二套；建議在 TASK-036 的接手上下文註明 | 待辦（已寫入 `launcher.py` docstring 與本表） |
| A-5 | SPEC 第 5 節模組表 | advisory（需追認） | `ediaad/launcher.py` 已在模組表，但表上的對外 API 只有 `main`／`is_running`／`wait_ready`，本張另加 `serve_main`（`--serve` 服務程序本體）；`ediaad/paths.py` 新增的 `pid_path` 也未列在該模組的 API 欄位 | 下次 SPEC 修訂時把 `serve_main` 與 `pid_path` 補進對應模組的對外 API（與 TASK-020／024 的模組表追認項目一併處理） | 待追認（已記於 `STATE.md` 待決事項） |
| A-6 | 流程記載 | advisory（非程式） | `home` fixture 的清理會對 PID 檔裡的 PID 送 SIGTERM，而有三個測試刻意把自己的 PID 寫進 PID 檔 → 測試跑到一半**整個 pytest 行程被殺**、輸出中斷；另有一處 `open_browser` 的死參數與一個變異字串因實作修正而失效 | 已修正（加 `pid != os.getpid()` 守衛、清理升級為 SIGKILL、移除死參數、修正變異字串後在同一份凍結檔案重跑）並如實記載 | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-049／AC-050 的六項宣稱逐條符合；品質 Review 無 blocking。
- 依測試回饋修正實作 2 處：`is_alive` 加入殭屍判斷（`/proc/<pid>/stat` 的 `Z`），`stop.sh` 同步；`is_running` 的埠那一半改為 health check（純 TCP 探測只留給「埠被別的程序佔用」）。
- 依變異檢查補強測試 2 處（「程序活著 ＋ 外來 listener」的錯誤語意、`stop.sh` 損毀 PID 檔的訊息），並移除 1 處冗餘參數（`open_browser` 的 `opener`）。
- 重審：重跑單檔（25 passed）與全套（**778 passed**）、兩個流程驗證器（exit 0），並在凍結版重跑變異矩陣（**29／30 偵測到，1 個等價**）；重讀 `launcher.py`／`app.py` 的關閉路徑與 `stop.sh` 複查訊號、清理與 PID 檔語意。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-049 的五項宣稱、AC-050 的三項宣稱逐條符合）
- 品質 Review：passed（無 blocking；A-1 需在後續 Task 落實，A-2 為交付前人工檢查，A-3～A-5 已記錄或待追認，A-6 為流程記載）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-025）、A-2（交付前人工檢查）、A-3（需安裝流程，屬交付後）、A-4（TASK-036 遵守）、A-5（Spec 補 API 欄位）、A-6（已記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：桌面圖示雙擊與瀏覽器實際開啟未驗證（已有子程序生命週期、埠釋放與注入式開啟時機的證據）；`ediaad.desktop` 的絕對路徑需隨搬移更新；`stop.sh` 的等待上限是政策（測試固定「正常 8 秒內完成」與「逾時後 SIGKILL」）；服務仍不會自己跑監控（A-1）
