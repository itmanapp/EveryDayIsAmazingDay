# TASK-027 測試紀錄

- task_id：TASK-027
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-notify sha256:337e645a8137bd0ddf8c44ae382e8891875274629574f62361c76d1dc7b31749
- alternative_reason：**部分替代**——桌面通知是否真的彈出、macOS／Windows 命令是否可用，無法在無桌面工作階段的自動測試中驗證（且自動測試**刻意不執行**真實通知命令）。本張以可注入的 `runner`／`which`／`env` 驗證命令組裝與全部失敗路徑，並以真的 `SSEHub` 驗證兩個推播事件型別；Linux 實機的 `notify-send` 彈出與 macOS／Windows 實機仍**未執行**（見「未執行或受阻」）。
- Task／Spec 版本：TASK-027 / SPEC-001 v0.4
- 測試邊界：（1）通知命令的組裝（三個平台）與失敗處理（命令不存在、非 0 結束、`OSError`、沒有 session bus）；（2）推播：假 hub 觀察 `publish` 參數、真 `SSEHub` 觀察兩個事件型別與無訂閱者時的行為；（3）去重：以 `monitor.run_once` 三輪（同一事件、同一事件、新事件）驗證 1、0、1；（4）前端 `notify.js` 的純函式以 Node ＋ 假 `Notification` 驗證。全部離線，**不執行任何真實通知命令**。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-026 的交付物，全套 **778 passed**（本張完成後為 **798 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `b1f771602b9dcc75f6b0269b17bb9401086929a84d7d83b22e64bfd805126ee5`（72 個檔案）。
- TDD 不適用的理由與替代驗證（若有）：見「未執行或受阻」第 1 點。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/notify/__init__.py` | `82ab116b` | 新增：`Notifier` Protocol 與 `build_notifiers`（依平台與 `which` 組出可用管道） |
| `ediaad/notify/message.py` | `6f250859` | 新增：`notification_text`／`describe_probability`（三個管道共用的標題與內容） |
| `ediaad/notify/web.py` | `e252f865` | 新增：`WebNotifier`（包裝 `SSEHub.publish`，`event="alert"`） |
| `ediaad/notify/browser.py` | `afa109ce` | 新增：`BrowserNotifier`／`notification_for`（`event="notification"`，payload 只有 title／body／tag） |
| `ediaad/notify/desktop.py` | `48249977` | 新增：`command_for`／`command_name`／`DesktopNotifier`（可注入 runner／which／env／warn） |
| `ediaad/web/static/notify.js` | `7fc5f8dd` | 新增：權限、顯示與 `EventSource` 黏著層（`window.ediaadNotify`） |
| `ediaad/app.py` | `4b0ae0e2` | 修改：`notifiers` 欄位、`enable_notifications()`、`make_emit` 走通知管道（未啟用時維持 TASK-021 行為） |
| `ediaad/launcher.py` | `c1474c43` | 修改：`--serve` 服務程序啟用三管道通知 |
| `ediaad/web/static/index.html` | `bbe18d0e` | 修改：載入 `notify.js` |
| `tests/test_notify.py` | `e6989ded` | 新增：20 個測試（含 1 個三輪去重整合案例與 1 組 Node 純函式斷言） |

## Cycle 1：三個管道與組裝（AC-051，真實 Red → Green）

- 測試（17 個）：`command_for("linux")` 以 `notify-send` 開頭且第二／第三個參數就是標題與內容；`DesktopNotifier(platform="linux", runner=假)` 讓假 runner 收到**一次**命令、內容含商品代號與事件時間；macOS 產生 `osascript`＋`display notification`、Windows 產生 PowerShell toast、不支援的平台回空清單；**引號跳脫**（AppleScript 的雙引號、PowerShell 的單引號）不會讓腳本壞掉；`notify-send` 不存在時不執行且留下可讀警告；runner 回傳非 0 或丟出 `OSError` 都只記 warning（不中斷）；沒有 `DBUS_SESSION_BUS_ADDRESS` 時跳過並警告；`notification_text` 帶齊商品／週期／事件時間／信心／機率／樣本數，且**沒有樣本（含樣本 0 卻帶機率的不一致輸入）一律說「無樣本」、不得出現百分比**；`WebNotifier` 以 `event="alert"` 推播原 payload；`BrowserNotifier` 以 `event="notification"` 推播只有 `title`／`body`／`tag` 的 payload，`tag` 等於事件的去重鍵且其**事件 id 與網頁管道不同**（否則會被 hub 當成重複而抑制）；三個管道對同一事件都觸發（真 `SSEHub` 的訂閱者收到 `alert` 與 `notification` 兩幀、runner 被呼叫一次）；**沒有訂閱者時網頁管道靜默但桌面通知仍觸發**；同一事件不重複推播（hub 的 `seen_ids` 只有兩個）；`build_notifiers` 依平台與 `which` 選出 3／2 個管道且順序固定；以 `monitor.run_once` 三輪驗證通知次數 **1、0、1**（AC-023 的去重沒有被通知層繞過）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_notify.py -q` | 2 | collection error：`ModuleNotFoundError: No module named 'ediaad.notify'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `17 passed`（前端三項仍紅，屬 Cycle 2） | snap-2026-09-24-ocaievo-notify／2026-09-24 |

- 實作：`ediaad/notify/`（`message`／`web`／`browser`／`desktop`／`__init__`）。
- **為什麼瀏覽器通知要是一個獨立的事件型別**：`SSEHub` 以事件內容去重，兩個管道若送同一份 payload，第二個會被當成重複而抑制。`notification` 的 payload 刻意**不含**去重鍵欄位（id 因此是內容雜湊，與網頁管道的 id 不同），並以 `tag` 帶上同一個去重鍵讓頁面端也能去重。這一點有測試直接斷言（兩個 id 必須不同），也是變異 `N07`／`N09` 的偵測點。
- **通知失敗絕不影響監控**：命令不存在、非 0 結束、`OSError`、沒有 session bus 四條路徑都只記 warning；`DesktopNotifier` 不吞掉程式缺陷（只攔 `OSError`）。
- **通知預設不啟用**（`Application.create()` 的 `notifiers` 是空的）：測試或工具不該在使用者的桌面上彈出真實通知；服務啟動路徑（`launcher --serve`）明確呼叫 `enable_notifications()`，並有測試以假的 `Application` 斷言呼叫順序（`pid` → `signals` → `notify` → `start` → `shutdown`）。
- **如實記載的夾具錯誤**：三輪去重測試第一版用自製的 `Watchlist` 假物件，漏了 `horizon` 欄位（`run_once` 會用到）→ `AttributeError`；已改用真的 `monitor.Watchlist` 與 `markets.base.Instrument`。

## Cycle 2：前端瀏覽器通知（AC-051，真實 Red → Green）

- 測試（3 個）：`/static/notify.js` 以正確的 `Content-Type` 提供且含 `ediaadNotify`／`/api/events/stream`／`notification`；首頁載入 `notify.js`；以 Node ＋ 假 `Notification` 驗證：`supported` 對沒有 `Notification` 的環境回 `false`；`permission` 三態（granted／denied／unsupported）；`describe` 只取 title／body；`show` 在 granted 時建立通知（標題、`body`、`tag` 都正確）且在 denied／unsupported 時回 `false` 且**不建立**通知；`requestPermission` 對不支援與沒有 API 的環境回 `false`、對可用環境回要求後的權限。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | 同上 | 1 | `2 failed, 17 passed, 1 error`：`notify.js` 404、Node 讀不到檔案 | 同上／2026-09-24 |
| Green | 同上 | 0 | `20 passed in 2.17s` | 同上／2026-09-24 |

- 實作：`notify.js`（純函式 ＋ `attach` 黏著層；權限在使用者第一次點擊頁面時才詢問，`tag` 去重；`EventSource` 監聽 `notification` 事件）與 `index.html` 的 script。
- **權限只在互動時詢問**：瀏覽器會拒絕沒有使用者互動的權限請求，因此 `attach` 監聽第一次 `click`；`show` 在沒有 granted 時直接回 `false`（不嘗試顯示）。

## 變異測試（兩階段：先殺存活者，再跑凍結版）

- 工具：`/tmp/mutate_task027.py`（整行替換、`count(frm) == 1` 才套用、逾時 180 秒、跑完立即還原並比對 sha256、`flock` 確保單一行程）。
- 矩陣：**25 個變異**（`message.py` 3、`web.py` 1、`browser.py` 3、`desktop.py` 9、`__init__.py` 2、`app.py` 2、`launcher.py` 1、`notify.js` 3、`index.html` 1），涵蓋「無樣本」與百分比、標題內容、兩個事件型別、payload 契約與 tag、三個平台的命令與引號跳脫、四條失敗路徑、管道組裝與順序、`enable_notifications`／`make_emit` 的兩條路徑、服務啟用通知、前端支援判斷／權限／顯示選項、首頁接線。
- **第一階段抓到 1 個真實存活者並補強測試擊殺**：`N01`（`describe_probability` 的「沒有樣本」分支拿掉）存活——我的測試只用了「機率為 `None` 且樣本 0」的輸入，而下一行的 `up_probability is None` 也會回「無樣本」，兩個分支對該輸入等價。已補「樣本 0 卻帶著機率」的不一致輸入（真實世界的防禦情境），此時少了第一個分支就會顯示 `50.0%（0 次）`。
- **2 處判讀為冗餘並直接移除**（專案既有原則：移除冗餘碼而不是補測試）：
  1. `DesktopNotifier.available()` 沒有任何呼叫端（`build_notifiers` 自己用 `command_name` ＋ `which` 判斷），留著只會製造不可觀測的分支 → 移除。
  2. `notify.js` 的 `requestPermission` 原本先檢查 `supported(win)` 與 `requestPermission` 是否為函式；`N26` 連續兩次存活證明那段檢查與後面的 `try`／`catch` 等價（不支援的環境會在呼叫時丟 `TypeError`，一樣回 `false`）→ 移除檢查，只留 `try`／`catch` 並在註解說明。
- **最終凍結版結果：25／25 全數偵測到（0 存活、0 無效）**，逐輪輸出形如 `19 passed, 1 failed`（20 個測試）。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `.venv/bin/python -m pytest tests/test_notify.py -q` | 0 | `20 passed in 2.03s` |
| `.venv/bin/python -m pytest -q` | 0 | `798 passed, 2 warnings in 133.71s` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |

## 未執行或受阻

1. **Linux 桌面通知的實際彈出未執行**（自動測試刻意不執行真實通知命令，以免在使用者的工作階段中彈窗）：`notify-send` 的 argv 已由假 runner 逐項斷言（含參數順序與引號跳躍），但「畫面上真的出現通知」依 SPEC 第 7 節人工檢查第 3 項，需在 Linux 實機執行一次並記錄。
2. **macOS／Windows 只產生命令，未實機驗證**（SPEC 第 2 節 out of scope）：`osascript` 與 PowerShell toast 的命令組裝有測試（含跳脫），但沒有在對應系統上執行過；交付報告必須標示未實機驗證。
3. **`notify.js` 的 `attach`（EventSource ＋ 權限詢問 ＋ tag 去重）未自動測試**：只有純函式與頁面接線有自動證據；實際權限對話框與作業系統通知中心的行為需人工檢查。
4. **通知的端到端觸發尚未接上監控執行緒**：`Application.make_emit()` 已能一次觸發三個管道（有測試），但**沒有任何執行路徑會週期性呼叫 `run_once`**（TASK-025 的缺口 A-1）；目前的通知能力在服務中是「已接線、待驅動」。
