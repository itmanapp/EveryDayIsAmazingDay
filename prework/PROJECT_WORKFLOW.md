# 本專案的 AI 工作流程

讀取本專案適用的既有規則，再讀 `.project-workflow/SKILL.md`，按階段載入 references。工作文件在 `docs/workflow/`；範本在 `.project-workflow/assets/templates/`。以下路徑均相對於專案根目錄。

## 本次工作的方式

狀態：**實作中（implement）**。SPEC-001 v0.4 已 `ready`；37 張 Task 的單張文件皆完整（status 為 `ready`），實作授權已於 2026-09-24 記錄（見 `docs/workflow/PROJECT.md`），並依使用者指示把**所有實作與程式碼放在 `ocaievo/`**。目前依相依順序逐張 TDD，起點 TASK-001。

- 本次目標與範圍：依 `docs/architecture/ENGINEERING-REPORT.md` **從零重建** ediaad——一套完全在本機執行的市場規律偵測與監控提醒工具，外加只做版本記錄與授權的 Cloudflare 後端。範圍為使用者 2026-09-24 選定的「全部」：報告第 3、4、5 章的核心引擎、第 6 章的 Web 介面 G1–G11 與授權／更新／通知、第 7 章的多市場來源（Binance／TWSE／Twelve Data／自訂 CSV）與版本化 catalog，以及 Cloudflare Worker ＋ D1 後端。共 66 項 AC、37 張 Task。完整需求見 `docs/workflow/BRIEF.md`，測試邊界見 `docs/workflow/SPEC.md` 第 7 節。
- 程式碼位置與路徑慣例：所有實作與程式碼在 `ocaievo/`（`ediaad/`、`tests/`、`scripts/`、`cloudflare/`、`requirements*.txt`、`stop.sh`、`.venv/`）；專案根只保留工作流程文件。SPEC 與 Task 文件的實作路徑相對 `ocaievo/`，工作文件路徑相對專案根；執行指令的工作目錄為 `ocaievo/`。
- 關鍵設計事實（本專案最重要的性質）：所有門檻使用相對單位（ATR 倍數、band 倍數、K 線根數），因此**價格乘常數或平移後命中位置完全不變**（AC-006、AC-019）；核心運算不碰 I/O，監控的所有外部效果皆可注入（`fetch`／`emit`／`warn`／`sleep`／`should_stop`），所以全部自動測試離線可跑。
- 與報告不一致之處（皆有理由並記入 SPEC 第 9 節變更紀錄）：
  1. **台股除權息**（ADR-003）：報告稱 TWSE 除權息端點無可用來源；實測發現 `TWT49U?startDate=&endDate=` **可用**（2024-07 共 449 筆，含權值+息值），因此 AC-034 採完整還原為主、事件排除為輔。存證在 `docs/workflow/evidence/twse-probe/`。
  2. **不重建 `ediaad/sources/`**：報告第 4.3／6.1 節保留它是因為 v0.3 建構在既有 v0.2 程式碼上；本專案從零重建（ADR-001），沒有需要相容的呼叫端，保留會讓 Binance 取得出現兩條路徑並重現 F-001 的資料結構不一致風險。`ediaad/markets/crypto.py` 為唯一實作。
- 適用階段、各階段產物與通過條件：走完整流程 discover → spec → tasks → ready → implement → verify → complete。完整規則見 `.project-workflow/references/workflow.md`。本專案已通過 ready 閘門（SPEC ready、授權已記錄、無 draft Task），目前在 implement 階段逐張推進。
- 本次交付停點：**完成 37 張 Task 與 TASK-037 的整合驗收，產出 `docs/workflow/DELIVERY.md`**。對外動作仍不含 `git init`、push、開 Issue、合併、部署或發布——這些各自需要另行取得指示。
- 適用的測試／審查／人工驗收方式及理由：
  - 自動測試用 `pytest`，全部必須離線可跑；需要網路的部分（來源、授權、更新）一律以注入的假 HTTP 客戶端、假時鐘與假資料來源驗證，只有少量實機人工檢查。
  - 公開觀察邊界以 Python 公開函式、`python -m ediaad` 子程序、本機 HTTP 端點（`127.0.0.1:8787`）與 `cloudflare/` 的 `node --test` 為主；不直接呼叫 private 函式。
  - 規律偵測（TASK-008）以「依已知參數植入三相位」的合成序列為 oracle，逐相位斷言索引邊界，並以四種反例驗證零命中；尺度不變以乘常數與平移驗證命中索引完全相同。這是本專案最重要的一組測試。
  - 授權驗章（TASK-029）以 **RFC 8032 官方測試向量**為 oracle，不以自己實作的簽章驗自己實作的驗章。
  - 環境建置（TASK-001）與整合交付（TASK-037）沒有可先寫的行為 Red，TDD 紀錄的 `verification` 填 `alternative` 並寫明理由；其餘 Task 一律先 Red 後 Green。
  - 每張 Task 完成後由同一 AI 分兩次、以分開的清單做 Spec Review 與品質 Review，標為 `self-review`；本專案未指定獨立 reviewer。
  - 必要的人工／視覺檢查：K 線圖三相位標註（AC-043）、Chrome／Wayland 下的網頁互動（AC-042～AC-050）、Linux 桌面通知（AC-051）、除權息還原前後的命中差異（AC-034）。
  - 不適用的方式及原因：不引入瀏覽器自動化與 Node 建置工具鏈，故不做跨瀏覽器視覺回歸；macOS／Windows 無實機，故其桌面通知在交付報告標示未實機驗證；Cloudflare 無部署授權，故只做本機 `node --test`，不做線上端到端驗收。

## 詳細資料與接續

- 環境、真實執行指令、自行決策範圍及使用者授權：`docs/workflow/PROJECT.md`。務必先看其中的環境限制（`sudo` 因 `no new privileges` 不可用、無預裝 pip、`.venv` 用 `venv --without-pip` + `get-pip.py`）。
- 規格與測試策略：`docs/workflow/SPEC.md`（附錄 A 是報告 F1–F14、G1–G20 與第 4／6／7 章子系統到 AC 的需求來源對照矩陣，確認範圍時可逐條核對）；任務及 AC 對照：`docs/workflow/TASKS.md`；領域詞彙：`docs/workflow/CONTEXT.md`。
- 重大決策與理由：`docs/workflow/adr/ADR-001.md`（從零重建與單一 Spec）、`ADR-002.md`（純 Python Ed25519）、`ADR-003.md`（台股除權息改採官方完整還原）。
- 需求來源副本：`docs/architecture/ENGINEERING-REPORT.md`（read-only 語意，不在本專案修改）。
- 進度與下一步：`docs/workflow/STATE.md`。續作先核對磁碟、現有檔案快照與測試／Review 證據，再接手當前 Task。任務狀態以單張 Task 檔為權威。
- 文件一致性檢查：`.project-workflow/references/validation.md`；執行 `python3 .project-workflow/scripts/validate_workflow.py .`。結構通過不代表產品測試已通過。

摘要只記錄本專案的工作方式與上述文件的導覽。命令、授權及進度保留在各自的權威文件，不在此重複維護。範本的待填欄位不是已確認需求或測試證據。
