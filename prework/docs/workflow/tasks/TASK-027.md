# TASK-027：網頁、瀏覽器原生與服務端桌面三管道通知

- id：TASK-027
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-051"]
- depends_on：["TASK-018", "TASK-020"]
- test_evidence：["docs/workflow/tdd/TASK-027.md"]
- review_evidence：["docs/workflow/reviews/TASK-027.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：一次命中經 TASK-018 的去重後，三個管道各自可觸發——網頁內提示（推播給已連線頁面）、瀏覽器原生通知（`Notification` API，`http://127.0.0.1` 屬安全來源）、服務端桌面通知（Linux 以 `notify-send` 實測彈出）；同一事件不重複通知（連續三輪只有第一輪發出，對照 AC-023 的 1、0、1）；網頁關閉（無 SSE 訂閱者）時網頁管道靜默但桌面通知仍觸發；macOS 的 `osascript` 與 Windows 的 PowerShell toast 只產生對應命令並標示未實機驗證。
- 本張不做：不改 `monitor.run_once` 的 `emit` 介面（報告第 6.6 節「引擎 0 改動」）、不做事件歷史查詢（TASK-021）、不做 K 線圖與各管理頁、不做授權與更新相關通知；不引入通知第三方套件（如 `plyer`）；不驗證 macOS／Windows 實機（SPEC 第 2 節 out of scope）；不自行重算去重（沿用 TASK-018）。
- 每個 AC 在本張負責的範圍：AC-051 全部（網頁內提示、瀏覽器原生通知、服務端桌面通知皆能觸發；Linux 以 `notify-send` 實測；macOS／Windows 路徑在交付報告標示為未實機驗證）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-051、第 5 節 `ediaad/notify/`（`Notifier`、`WebNotifier`、`BrowserNotifier`、`DesktopNotifier`）、第 7 節測試策略（假通知後端＋Linux 實機人工檢查；「桌面通知無法在 CI 驗證；macOS／Windows 標示未實機驗證」）、第 2 節 out of scope；`docs/architecture/ENGINEERING-REPORT.md` 第 6.6 節通知子系統表（網頁內提示／`Notification` API／`notify-send`、`osascript`、PowerShell toast，沿用可注入 `emit` 實作另一種 emitter）與第 3.2 節通知功能；`docs/workflow/PROJECT.md` 環境實測（`notify-send` 存在、`DBUS_SESSION_BUS_ADDRESS` 已設定）。
- 模組與公開介面：新增 `ediaad/notify/__init__.py`（`Notifier` Protocol：`notify(event: dict) -> None`；`build_notifiers(hub, platform=None, which=shutil.which, runner=None) -> list[Notifier]` 依環境組出可用的管道）、`ediaad/notify/web.py` 的 `WebNotifier(hub)`（包裝 TASK-021 的 `SSEHub.publish`，無訂閱者時靜默）、`ediaad/notify/browser.py` 的 `BrowserNotifier`（產生前端 `Notification` 所需的 payload，經既有推播送達頁面）、`ediaad/notify/desktop.py` 的 `DesktopNotifier`（純函式 `command_for(platform, title, body) -> list[str]` 與 `notify(event)`；`runner` 可注入，失敗只記 warning）；新增 `ediaad/web/static/notify.js` 處理瀏覽器通知權限與顯示；`ediaad/app.py` 把 `run_once` 的 `emit` 接到這些 notifier，引擎邏輯不變。
- 預計觸及的檔案：`ediaad/notify/__init__.py`、`ediaad/notify/web.py`、`ediaad/notify/browser.py`、`ediaad/notify/desktop.py`、`ediaad/web/static/notify.js`、`ediaad/app.py`、`tests/test_notify.py`；實作前重新查證（特別是 TASK-021 的 `SSEHub.publish` 與 TASK-018 的去重介面是否已定案）。
- 必要環境／依賴：TASK-018 的去重與事件落地、TASK-020（`Application`）與 TASK-021 的推播（本張依賴表中為 TASK-018、TASK-020，推播端點若尚未完成則以假 hub 驗證）；標準庫 `subprocess`、`shutil.which`、`platform`；Linux 實機需 `notify-send` 與可用的 `DBUS_SESSION_BUS_ADDRESS`。

## 測試計畫

- 測試公開邊界：`DesktopNotifier` 以假 runner（記錄 argv、可回傳失敗）觀察實際要執行的命令；`WebNotifier` 以假 hub（記錄 `publish` 呼叫）觀察推播；`BrowserNotifier` 只斷言 payload 契約；`build_notifiers` 依平台與 `which` 的組裝結果。真實 `notify-send` 只在 Linux 人工檢查執行，不進自動測試。
- 第一個失敗行為與預期斷言：先寫「在平台為 `linux` 時 `DesktopNotifier.notify(event)` 讓假 runner 收到一次 `argv[0] == "notify-send"` 的呼叫，且命令列包含商品代號與事件時間」。實作前執行 `.venv/bin/python -m pytest tests/test_notify.py -q` 預期收集期失敗 `ModuleNotFoundError: No module named 'ediaad.notify'`；實作後斷言成立。
- 後續例外／邊界情境：`notify-send` 不存在（`which` 回 `None`）或 runner 回傳非 0 時只記 warning、不得中斷監控迴圈；`DBUS_SESSION_BUS_ADDRESS` 未設定時回可讀警告並跳過桌面通知；沒有任何 SSE 訂閱者時 `WebNotifier` 靜默而 `DesktopNotifier` 仍觸發；同一事件連續三輪只有第一次通知（沿用去重，提醒次數 1、0、1）；`command_for` 對 macOS 與 Windows 分別產生 `osascript` 與 PowerShell 命令且不實際執行。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_notify.py -q`；相關回歸 `.venv/bin/python -m pytest -q`。
- 非程式任務的替代驗證與理由：不適用（通知後端可注入，自動測試可完整覆蓋命令組裝與錯誤處理）；桌面通知是否真的彈出無法在無桌面工作階段的自動測試中驗證，依 SPEC 第 7 節人工檢查第 3 項在 Linux 實機以 `notify-send` 實測並記錄，macOS／Windows 僅記錄命令產生結果並標示未實機驗證。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-026 的交付物（全套 **778 passed**），檔案樹 sha256 `b1f771602b9dcc75f6b0269b17bb9401086929a84d7d83b22e64bfd805126ee5`（72 檔）；本次新增 `ediaad/notify/`（`__init__.py`／`message.py`／`web.py`／`browser.py`／`desktop.py`）、`ediaad/web/static/notify.js` 與 `tests/test_notify.py`，並修改 `ediaad/app.py`、`ediaad/launcher.py`、`ediaad/web/static/index.html`（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-027.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-027.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-notify` sha256:337e645a8137bd0ddf8c44ae382e8891875274629574f62361c76d1dc7b31749（原始碼樹，79 檔）；`ediaad/notify/__init__.py` `82ab116b…`、`message.py` `6f250859…`、`web.py` `e252f865…`、`browser.py` `afa109ce…`、`desktop.py` `48249977…`、`ediaad/web/static/notify.js` `7fc5f8dd…`、`ediaad/app.py` `4b0ae0e2…`、`ediaad/launcher.py` `c1474c43…`、`ediaad/web/static/index.html` `bbe18d0e…`、`tests/test_notify.py` `e6989ded…`；全套 **798 passed**；變異矩陣 25／25 偵測到（0 存活）
- 取消、重開或變更原因：無
