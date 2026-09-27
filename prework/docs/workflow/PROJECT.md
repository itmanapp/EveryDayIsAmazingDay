# 專案設定

- 專案名稱：ediaad（依 `docs/architecture/ENGINEERING-REPORT.md` 從零重建）
- 目標專案根目錄：`/home/itx-u24d/桌面/DSH/EveryDayIsAmazingDay`
- **程式碼位置（使用者指示 2026-09-24）**：所有實作與程式碼一律放在子資料夾 `ocaievo/`。`ocaievo/` 內含 `ediaad/`（套件）、`tests/`、`scripts/`、`cloudflare/`、`requirements*.txt`、`stop.sh`、`.venv/`；專案根只保留工作流程文件（`PROJECT_WORKFLOW.md`、`AGENTS.md`、`.project-workflow/`、`docs/`）
- **路徑慣例**：SPEC 與 Task 文件中的實作檔案路徑一律**相對 `ocaievo/`**（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`、`tests/test_data.py` 指 `ocaievo/tests/test_data.py`）；工作文件與證據路徑（`docs/workflow/…`、`.project-workflow/…`）則相對專案根。下方執行指令的工作目錄為 `ocaievo/`
- 工具包來源／版本：<https://github.com/itmanapp/skills-agent-spec>，clone commit `f441dbe`（`skills/project-workflow/VERSION` = `v1.0`），取得日期 2026-09-24
- 溝通語言：繁體中文
- 技術棧與版本：Python 3.12.3（`ocaievo/.venv`，`venv --without-pip` + `get-pip.py`）、執行期依賴僅 `numpy`、`pandas`，開發再加 `pytest`；本機服務使用標準庫 `http.server`／`socketserver`／`sqlite3`／`ssl`／`hashlib`；前端為原生 HTML／CSS／JS 與 `<canvas>`；授權簽章用純 Python Ed25519（RFC 8032）；Cloudflare 後端為 JavaScript Worker（WebCrypto 簽章）＋ D1，本機以 `node --test` 驗證純函式
- 既有規範與領域文件：需求與架構權威來源為 `docs/architecture/ENGINEERING-REPORT.md`（報告日期 2026-09-24，對應程式版本 Git tag `V1.0`／commit `4e6c2a7`）。本專案**不沿用**該 tag 的程式碼，只沿用其功能與架構設計；領域詞彙見 `docs/workflow/CONTEXT.md`

## 執行指令

工作目錄均為 `ocaievo/`（`cd ocaievo` 後執行）。`bootstrap_env.py` 以自身檔案位置解析路徑，因此從任何工作目錄執行都指向同一個 `ocaievo/.venv`。

| 用途 | 工作目錄 | 實際命令 | 狀態／驗證日期 |
| --- | --- | --- | --- |
| 安裝依賴 | `ocaievo/` | `python3 scripts/bootstrap_env.py` | 已驗證 2026-09-24（exit 0；TASK-001 done） |
| 啟動（服務） | `ocaievo/` | `.venv/bin/python -m ediaad serve` | 待建立（TASK-020） |
| 啟動（桌面圖示） | `ocaievo/` | `python3 scripts/ediaad_launcher.py` | 待建立（TASK-026） |
| 停止服務 | `ocaievo/` | `./stop.sh` | 待建立（TASK-026） |
| 單項／單檔測試 | `ocaievo/` | `.venv/bin/python -m pytest tests/test_features.py -q` | 待建立（TASK-003） |
| 全套測試 | `ocaievo/` | `.venv/bin/python -m pytest -q` | 環境已就緒 2026-09-24；測試檔自 TASK-002 起建立 |
| 後端 Worker 測試 | `ocaievo/cloudflare/` | `node --test` | 待建立（TASK-033） |
| lint | `ocaievo/` | 不適用 | 本版不引入 lint 工具，維持「一次安裝、零額外依賴」；以測試與 Review 取代 |
| 型別檢查 | `ocaievo/` | 不適用 | 同上；未使用靜態型別檢查器 |
| build | `ocaievo/` | 不適用 | 純 Python 直譯執行，無需打包步驟；Cloudflare Worker 由 `wrangler deploy` 發布（部署不在授權範圍） |

單檔測試以 `pytest` 的位置參數指定檔案，例如 `.venv/bin/python -m pytest tests/test_patterns_detect.py -q`；`-k` 指定單一案例。從專案根執行時等價於 `ocaievo/.venv/bin/python -m pytest ocaievo/tests/test_patterns_detect.py -q`。

## 環境與測試資料

2026-09-24 實測（非引用報告附錄，逐項重跑）：

| 檢查 | 實測結果 | 對設計的影響 |
| --- | --- | --- |
| `sudo -n true` | 失敗（`The "no new privileges" flag is set`）→ 無法取得 root | 不得依賴系統套件安裝 |
| `pip`／`pip3` | 未安裝 | 必須 `venv --without-pip` + `get-pip.py` |
| `curl`／`wget` | 存在（`/usr/bin/curl`、`/usr/bin/wget`） | 與報告附錄「無 curl」不同；仍以標準庫 `urllib` 下載，不新增外部工具依賴 |
| `python3 -m venv --without-pip` | 成功 | 建置路徑可行 |
| `numpy`／`pandas`／`pytest`（系統） | 未安裝 | 全部裝進 `ocaievo/.venv` |
| `cryptography`（系統） | 已裝 41.0.7 | **不使用**；Ed25519 以純 Python 實作，避免 `.venv` 新增依賴（見 ADR-002） |
| `notify-send`、`DBUS_SESSION_BUS_ADDRESS` | 存在／已設定 | Linux 桌面通知可實作 |
| `DISPLAY=:0`、`WAYLAND_DISPLAY=wayland-0`、`XDG_SESSION_TYPE=wayland` | 有 | 桌面圖示與瀏覽器啟動可行 |
| 預設瀏覽器 | `com.google.Chrome.desktop`；`firefox`、`google-chrome`、`xdg-open` 皆在 | 一鍵啟動以 `xdg-open` 開啟 |
| `~/.local/share/applications`、`~/桌面` | 存在且可寫（前者權限 `700`，屬目前使用者） | 可安裝桌面圖示 |
| `/etc/machine-id` | 可讀，33 bytes（含換行） | 機器指紋可行 |
| `npm`／`npx` | 可用（Node v24.21.0）；`wrangler` 未安裝 | Worker 測試走 `node --test`，不強制 `wrangler` |
| 磁碟 | `/` 可用 36G | 充足 |

外部端點實測（2026-09-24，逾時 8–20 秒，存證見 `docs/workflow/evidence/twse-probe/twse-endpoints.json`）：

| 端點 | 結果 | 對設計的影響 |
| --- | --- | --- |
| Binance `klines`／`exchangeInfo` | `200`、CORS `*` | 加密貨幣來源確認可用 |
| TWSE `STOCK_DAY`（2330，2024-07） | `200`、21 筆、民國年日期與千分位數字 | 台股日線來源確認可用 |
| TWSE `STOCK_DAY_ALL` | `200`、1,380 筆（JSON 陣列，含代號與中文名） | 商品搜尋清單來源確認可用 |
| TWSE `t187ap03_L`（上市公司基本資料） | `200`、1,095 筆 | 商品目錄輔助來源 |
| TWSE `holidaySchedule` | `200`、27 筆（115 年市場開休市日期） | 交易日曆來源確認可用 |
| TWSE `TWT49U`（除權息） | **`startDate`／`endDate` 參數可用**：2024-07 全月 449 筆，含除權息前收盤價、除權息參考價、權值+息值；`strDate`／`endDate` 回誤導性錯誤；`date=` 被忽略只回當日 | **修正報告結論**：官方歷史除權息來源確認可用，方案 B（完整還原）可行（見 ADR-003） |
| Twelve Data（無金鑰） | `401` 並附申請說明 | 端點可達；金鑰由使用者自填 |
| PyPI、`bootstrap.pypa.io`、npm registry | `200` | 依賴安裝與 `npx` 可用 |
| `cloudflare.com`、`api.cloudflare.com` | `200`／`400`（裸 GET 預期） | Cloudflare 連線可行；`one.one.one.one` 在本機 DNS 無記錄，與設計無關 |

- 需要的服務與環境變數名稱（不填秘密值）：`EDIAAD_HOME`（資料根目錄，預設 `~/.local/share/ediaad`）、`EDIAAD_PORT`（預設 `8787`）、`EDIAAD_LICENSE_URL`（授權服務位址）、`EDIAAD_UPDATE_URL`（manifest 位址）、`TWELVEDATA_API_KEY`（可選；正式來源為 `$EDIAAD_HOME/keys.json`）
- 隔離測試資料／清理方式：測試一律使用 `tmp_path` 與合成 OHLC 序列；外部網路以注入的假 HTTP 客戶端與假資料來源替代；`docs/workflow/evidence/twse-probe/twse-endpoints.json` 為一次性實測存證，不作為測試輸入
- 必須通過的最終檢查：`ocaievo/` 下 `.venv/bin/python -m pytest -q`（exit 0）、專案根 `python3 .project-workflow/scripts/validate_workflow.py .`（exit 0）、`ocaievo/cloudflare/` 下 `node --test`（exit 0）
- 既有失敗及影響：無（全新專案，尚無程式）

## 版本標記（checked_version）的計算慣例

TDD／Review 紀錄的 `checked_version` 一律記為 `<snap 標籤> sha256:<原始碼樹雜湊>`，其中「原始碼樹」為排除 `.gitignore` 所列產物後的 `ocaievo/` 檔案清單：

```bash
cd ocaievo
find . -type f -not -path "./.venv/*" -not -path "./.cache/*" \
  -not -path "./.pytest_cache/*" -not -path "*/__pycache__/*" \
  | sort | xargs sha256sum | sha256sum
```

- 可重算性：同一份樹重跑上式必須得到相同雜湊；TASK-011 起適用。
- 逐檔 sha256：交付檔另記 `sha256sum <file>` 的前 8 碼於 Task 的「執行紀錄與證據位置」與 TDD 紀錄，這一層**任何時候都可重算**，是主要校驗依據。
- 已知歷史瑕疵：TASK-001～TASK-010 的樹雜湊標籤以未記載的方式算出，以六種候選方法皆無法重現；那些標籤視為歷史標記，不作為校驗值（詳見 `docs/workflow/tdd/TASK-011.md` 末節）。

## 確認與授權

- 目前模式：**實作（implement）**；產品實作授權已於 2026-09-24 記錄
- 已確認 Spec 版本／Task 範圍／測試邊界：SPEC-001 v0.4（ready）、37 張 Task（TASK-001～TASK-037）、SPEC 第 7 節的測試公開邊界——使用者於 2026-09-24 逐項回覆「1-正確、2-同意、3-開始實作」
- 使用者確認或授權原意、來源與日期：
  - 2026-09-24（第一階段）：使用者指示「參考 <https://github.com/itmanapp/skills-agent-spec> 先建立工作流程的文件，目標任務於文件檔（`ENGINEERING-REPORT.md`）」。→ 先交付工作流程文件，不實作產品。
  - 2026-09-24（範圍）：使用者選擇「本工作區 `EveryDayIsAmazingDay`，從零重建」與「範圍：全部（Web G1–G11 ＋ 多市場 ＋ 授權 ＋ 更新 ＋ 通知 ＋ Cloudflare 後端）」。→ 本專案不沿用 v0.2 程式碼；Spec 涵蓋報告第 3、4、5、6、7 章全部功能。
  - 2026-09-24（**實作授權**）：使用者對「SPEC-001 v0.4 範圍與 66 項 AC 是否正確／測試公開邊界是否同意／是否授權開始實作」回覆「**1-正確、2-同意、3-開始實作，並且將所有實作及程式碼放在子資料夾 ocaievo**」。→ 授權逐張以 TDD 實作並完成交付；同時指定程式碼一律置於 `ocaievo/`（見上方「程式碼位置」）。授權範圍仍不含任何對外動作。
- 允許自行決定的範圍：技術棧細節、模組切法、測試夾具、命名與檔案配置、資料來源參數格式（已以實測確認）、`ocaievo/` 內的目錄配置。核心行為、資料不可逆變動與範圍擴張仍須使用者確認
- commit／push／Issue／合併／部署等對外動作：**一律未授權**。目前未 `git init`、未建立遠端、未部署 Cloudflare Worker、未發布任何版本；需要時另行取得明確指示
- 已知的未授權／未驗證邊界：Cloudflare 後端只能在本機以 `node --test` 驗證純函式與假的 D1 轉接層，**無法**驗證真實帳號、真實 D1 或實際部署；macOS／Windows 桌面通知與路徑無法在本機實機驗證（開發機為 Linux）

更新此處時保留既有授權依據；範本預設值不會撤銷使用者已給的明確指示。
