# TASK-027 Code Review

- task_id：TASK-027
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-notify sha256:337e645a8137bd0ddf8c44ae382e8891875274629574f62361c76d1dc7b31749
- Task／Spec 版本：TASK-027 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含兩個事件型別的設計、冗餘分支的移除與變異存活者的處理）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `b1f771602b9dcc75f6b0269b17bb9401086929a84d7d83b22e64bfd805126ee5`（72 個檔案）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `337e645a8137bd0ddf8c44ae382e8891875274629574f62361c76d1dc7b31749`（79 個檔案）；本張新增 `ediaad/notify/{__init__,message,web,browser,desktop}.py`（`82ab116b…`／`6f250859…`／`e252f865…`／`afa109ce…`／`48249977…`）、`ediaad/web/static/notify.js` `7fc5f8dd…`、`tests/test_notify.py` `e6989ded…`；修改 `ediaad/app.py` `4b0ae0e2…`、`ediaad/launcher.py` `c1474c43…`、`ediaad/web/static/index.html` `bbe18d0e…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：上述十個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`monitor.py`（`emit` 介面**刻意不動**，報告第 6.6 節「引擎 0 改動」）／`web/sse_hub.py`（沿用 TASK-021 的推播與去重）／`store.py`（TASK-018 的去重鍵來源）
- 程式規範來源：`docs/workflow/SPEC.md` 第 4 節 AC-051、第 5 節 `ediaad/notify/`（`Notifier`／`WebNotifier`／`BrowserNotifier`／`DesktopNotifier`）與依賴方向、第 7 節測試策略（假通知後端 ＋ Linux 實機人工檢查）、第 2 節 out of scope；`docs/architecture/ENGINEERING-REPORT.md` 第 6.6 節通知子系統與第 3.2 節；`docs/workflow/PROJECT.md` 環境實測（`notify-send` 存在、`DBUS_SESSION_BUS_ADDRESS` 已設定）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-051 | `ediaad/notify/`（五個模組）、`ediaad/web/static/notify.js`、`ediaad/app.py`（`enable_notifications`／`make_emit`）、`ediaad/launcher.py`；`tests/test_notify.py` 20 個案例 | 符合 | A-1～A-6（advisory） |

逐條核對：

- **AC-051「網頁內提示」**：`WebNotifier` 以 `event="alert"` 推播原始 payload（由 TASK-021 的 `events.js` 顯示在事件清單）；以假 hub 斷言 `publish` 的參數，並以真 `SSEHub` 斷言訂閱者收到 `alert` 幀。符合。
- **AC-051「瀏覽器原生通知（`Notification` API，`http://127.0.0.1` 屬安全來源）」**：`BrowserNotifier` 以 `event="notification"` 推播只有 `title`／`body`／`tag` 的 payload，`notify.js` 在權限為 granted 時以 `new Notification(title, {body, tag})` 顯示；前端純函式以 Node ＋ 假 `Notification` 驗證（granted／denied／unsupported 三態）。符合。
- **AC-051「服務端桌面通知（Linux 以 `notify-send` 實測）」**：`DesktopNotifier` 在 Linux 以 `notify-send <title> <body>` 執行（假 runner 逐項斷言 argv）；macOS `osascript`、Windows PowerShell toast 只產生命令並在 TDD 標示**未實機驗證**。**Linux 實機的實際彈出未執行**（見 A-2）。符合（實機人工檢查待辦）。
- **AC-051「同一事件不重複通知（對照 AC-023 的 1、0、1）」**：以 `monitor.run_once` 三輪（同一事件、同一事件、新事件）驗證通知次數為 1、0、1；傳輸層另有第二道防線（`SSEHub` 對兩個事件型別都以事件 id 去重，測試斷言 `seen_ids` 只有兩個）。符合。
- **AC-051「網頁關閉（無 SSE 訂閱者）時網頁管道靜默但桌面通知仍觸發」**：以真 `SSEHub`（`client_count == 0`）斷言兩個推播仍被記錄、而 runner 仍被呼叫一次。符合。
- **AC-051「macOS／Windows 路徑在交付報告標示為未實機驗證」**：TDD 紀錄與本 Review 都明確標示；命令組裝（含引號跳脫）有自動測試。符合。

## 品質 Review

- **引擎 0 改動（報告第 6.6 節）**：`monitor.run_once` 的 `emit` 介面完全沒動，通知只是在 `Application.make_emit()` 這個既有接縫上多接幾個消費者。這讓「通知」與「監控」可以各自演進，也讓 TASK-010／TASK-018 的去重測試不需要修改。
- **兩個事件型別是必要的設計，不是冗餘**：`SSEHub` 以事件內容去重（`event_id_for` 優先用去重鍵），若兩個管道送同一份 payload，第二個會被當成重複而抑制。`notification` 的 payload 刻意不含去重鍵（id 變成內容雜湊，與 `alert` 的 id 不同），並以 `tag` 帶上同一個去重鍵供頁面端去重。測試直接斷言「兩個 id 必須不同」，變異 `N07`／`N09` 也證明這條契約被釘住。
- **通知失敗絕不影響監控**：四條失敗路徑（平台不支援、命令不存在、非 0 結束、`OSError`／沒有 session bus）都只記 warning 並返回；`DesktopNotifier` 只攔 `OSError`（程式缺陷不吞）。這符合「提醒失敗不該讓輪詢停擺」的產品要求。
- **通知預設不啟用（可測性與禮貌）**：`Application.create()` 的 `notifiers` 是空的，`make_emit` 因此維持 TASK-021 的行為（只推播網頁管道）；只有 `launcher --serve` 明確呼叫 `enable_notifications()`。這避免測試或工具在使用者的桌面上彈出真實通知，也讓「未啟用」與「已啟用」兩條路徑各有測試（`N21`／`N22` 是偵測點）。
- **命令組裝是純函式、執行是可注入的**：`command_for(platform, title, body)` 可完全離線驗證，`runner`／`which`／`env` 三個注入點讓「命令不存在」與「沒有桌面工作階段」都能測試；引號跳脫（AppleScript 的 JSON 引號、PowerShell 的單引號加倍）有專門測試——這是最容易被忽略、卻會讓通知在真實系統上靜默失敗的地方。
- **F-003 的原則延伸到通知文字**：`describe_probability` 對「沒有樣本」明說無樣本，**樣本 0 卻帶著機率的不一致輸入也不得顯示百分比**（變異 `N01` 的偵測點）。
- **前端可測性沿用既有手法**：`notify.js` 是載入時不碰文件的 IIFE，支援判斷／權限／顯示都是純函式並以假的 `Notification` 驗證；權限只在使用者第一次點擊時詢問（瀏覽器會拒絕沒有互動的請求）。
- **冗餘碼的移除（兩處）**：`DesktopNotifier.available()` 沒有呼叫端（`build_notifiers` 自己判斷）→ 移除；`notify.js` 的 `requestPermission` 支援檢查與 `try`／`catch` 等價（`N26` 連續兩次存活證明）→ 移除檢查並在註解說明。
- **變異測試的強度**：25 個變異在凍結版全數被抓到。第一階段抓到 1 個真實存活者（`N01`，兩個「無樣本」分支對原測試輸入等價）並以不一致輸入擊殺；另有 2 處判讀為冗餘並移除。
- **測試品質**：通知命令以假 runner 逐項斷言（含參數順序與跳脫）；推播同時用假 hub（契約）與真 `SSEHub`（交付）；去重沿用 AC-023 的三輪夾具；前端以 Node 執行真實檔案。全部離線且**不執行**真實通知命令。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 跨 Task 缺口（沿用 TASK-013 A-1～TASK-026 A-1） | advisory（**需在後續 Task 處理**） | 通知能力「已接線、待驅動」：`make_emit` 能一次觸發三個管道，但沒有執行路徑會週期性呼叫 `run_once`（TASK-025 的監控執行緒）；`Store` 寫入端、`GET/POST /api/watchlist`、各來源 `cache_dir` 同樣待接 | TASK-025 應完成監控執行緒（`run_once` ＋ `Store`）、監控清單端點與系統狀態頁；系統狀態頁可一併顯示「已啟用的通知管道」 | 待辦（已記於 `STATE.md` 待決事項） |
| A-2 | Linux 實機通知 | advisory（**未執行**） | SPEC 第 7 節人工檢查第 3 項：`notify-send` 是否真的彈出。自動測試刻意不執行真實命令（避免在使用者工作階段彈窗） | 交付前在 Linux 實機執行一次：以 `DesktopNotifier(platform="linux")` 或 `python3 -c` 觸發一次通知並目視確認，記錄 `DBUS_SESSION_BUS_ADDRESS` 與 `notify-send` 版本 | 待辦（替代驗證：argv 逐項斷言） |
| A-3 | macOS／Windows | advisory（**未實機驗證**） | `osascript` 與 PowerShell toast 只產生命令（含跳脫測試），未在對應系統執行；Windows 的 WinRT toast 腳本尤其可能因系統版本而異 | 交付報告必須標示未實機驗證（SPEC 第 2 節 out of scope）；若日後要支援，需在實機上驗證腳本並考慮 `powershell` 路徑差異（`powershell.exe`） | 已標示（TDD／Review／交付報告） |
| A-4 | `notify.js` 的黏著層 | advisory | `attach`（`EventSource` 訂閱、權限詢問、tag 去重）沒有自動測試；只有純函式與頁面接線有證據 | 交付前的人工檢查涵蓋：允許通知後收到推播會彈出、拒絕權限時不彈且不報錯、同一事件只彈一次 | 待辦（交付前人工檢查） |
| A-5 | 通知的內容格式 | advisory | 通知文字是單行摘要（商品、週期、事件時間、信心、歷史機率）；沒有圖示、沒有點擊後跳轉到圖表頁 | 報告第 6.6 節只要求三個管道能觸發；若要「點通知跳到 K 線圖」，需要新的 AC 與前端路由 | 已記錄（無現時需求） |
| A-6 | 流程記載 | advisory（非程式） | 三輪去重測試第一版用自製 `Watchlist` 假物件而漏了 `horizon` 欄位（`AttributeError`）；變異 `N01` 因兩個分支對原輸入等價而存活；`N26` 連續兩次存活後判讀為冗餘並移除程式碼 | 已全部修正並如實記載（改用真的 `Watchlist`／`Instrument`；補不一致輸入；移除 `available()` 與 `requestPermission` 的支援檢查） | **已記載** |

## 修正與重審

- 第 1 輪：Spec Review AC-051 的六項宣稱逐條符合（Linux 實機彈出與 macOS／Windows 實機為待辦 advisory）；品質 Review 無 blocking。
- 依變異檢查補強測試 1 處（樣本 0 卻帶機率的不一致輸入），移除冗餘碼 2 處（`DesktopNotifier.available()`、`notify.js` 的 `requestPermission` 支援檢查）。
- 依測試回饋修正夾具 1 處（三輪去重測試改用真的 `Watchlist`／`Instrument`）。
- 重審：重跑單檔（20 passed）與全套（**798 passed**）、兩個流程驗證器（exit 0），並在凍結版重跑變異矩陣（**25／25 偵測到**）；重讀 `notify/` 五個模組與 `notify.js` 複查事件型別、payload 契約、失敗路徑、權限流程與引號跳脫。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-051 的六項宣稱逐條符合；Linux 實機與 macOS／Windows 實機列為待辦 advisory）
- 品質 Review：passed（無 blocking；A-1 需在後續 Task 落實，A-2／A-4 為交付前人工檢查，A-3 已標示未實機驗證，A-5／A-6 已記錄）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（TASK-025）、A-2（交付前人工檢查）、A-3（SPEC 第 2 節 out of scope，交付報告標示）、A-4（交付前人工檢查）、A-5（需新 AC）、A-6（已記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：Linux 桌面通知的實際彈出未執行；macOS／Windows 未實機驗證；`notify.js` 的 `EventSource`／權限／去重黏著層未自動測試；通知尚未被週期性觸發（A-1）；通知文字沒有圖示與點擊跳轉
