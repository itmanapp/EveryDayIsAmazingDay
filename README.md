# EveryDayIsAmazingDay — ediaad

**ediaad** 是一套**完全在本機執行**的市場規律偵測與監控提醒工具：把使用者心中「熟悉的型態」形式化成相對門檻（ATR 倍數、band 倍數、K 線根數），在歷史序列上滑動掃描，命中時主動提醒，並附上一套只負責**版本記錄與授權**的 Cloudflare 後端。

本倉庫是依 `prework/docs/architecture/ENGINEERING-REPORT.md` 的架構設計**從零重建**的成果，並以 `prework/` 內的完整工作流程文件（需求訪談 → Spec → Task → 逐張 TDD → Review → 交付）留下可追溯的證據。

- 交付狀態：**完成**（SPEC-001 v0.4、37 張 Task 全部 `done`、66 項 active 驗收條件全數對應）
- 已驗證：Python 測試 **1007 passed**、Cloudflare Worker 測試 **82 passed**
- 詳細交付報告：[`prework/docs/workflow/DELIVERY.md`](prework/docs/workflow/DELIVERY.md)

---

## 目錄結構

```text
.
├── README.md                 本文件
├── ocaievo/                  產品程式碼（使用者指定一律放在此子資料夾）
│   ├── ediaad/               主套件（特徵、相似度、掃描、規律、監控、授權、更新、Web）
│   │   ├── markets/          多市場資料來源（Binance、TWSE、Twelve Data、自訂 CSV）
│   │   ├── notify/           通知管道（網頁、瀏覽器原生、桌面通知）
│   │   └── web/              本機網頁服務（路由、SSE、原生前端）
│   ├── cloudflare/           Cloudflare Worker ＋ D1（授權／版本後端，本機以 node --test 驗證）
│   ├── tests/                pytest 測試（36 檔 ＋ 2 個夾具模組）
│   ├── scripts/              環境建置與桌面啟動器
│   ├── requirements*.txt     執行期（numpy、pandas）與開發（pytest）依賴
│   ├── ediaad.desktop        桌面圖示範本
│   └── stop.sh               停止本機服務
└── prework/                  **前置作業文件（全部集中在此獨立資料夾）**
    ├── AGENTS.md             進入點指示
    ├── PROJECT_WORKFLOW.md   專案工作流程規則
    ├── .project-workflow/    工作流程工具包（skills-agent-spec v1.0，含驗證腳本）
    └── docs/
        ├── architecture/ENGINEERING-REPORT.md   需求與架構權威來源（前置輸入）
        └── workflow/                           專案、規格、任務、TDD、Review、證據、交付
```

### 路徑慣例（請注意）

前置作業文件保留當初撰寫時的相對路徑寫法，因此：

- 文件中的 `docs/workflow/…`、`.project-workflow/…` → 相對於 **`prework/`**
- 文件中的 `ocaievo/…`（例如「實作位置 `ediaad/scan.py`」指的是 `ocaievo/ediaad/scan.py`）→ 相對於 **倉庫根目錄**

工作流程驗證指令（於 `prework/` 內執行）：

```bash
cd prework
python3 .project-workflow/scripts/validate_workflow.py .
```

---

## 核心能力

| 面向 | 內容 |
| --- | --- |
| 相似度路線 | 找出與範例「差不多」的歷史片段，輸出連續分數、排行與後續 N 根走勢統計（上漲機率、報酬分佈、樣本數） |
| 規律路線 | 判斷是否符合「盤整 → 假跌破 → 拉回」等規則，輸出布林命中、三個相位索引與信心值 |
| 尺度不變 | 10 維特徵以相對單位表示；價格乘常數或平移後命中位置完全不變，同一輸入永遠得到相同結果（無隨機性） |
| 多市場 | Binance（加密貨幣）、TWSE（台股日線，含除權息還原與交易日曆）、Twelve Data（需自備金鑰）、自訂 CSV |
| 本機網頁 | `127.0.0.1:8787` 的 11 項介面（G1–G11）：一鍵啟動、優雅關閉、監控清單、規律參數即時預覽、範例學習、即時提醒、K 線三相位、歷史回看、系統狀態、版本頁、授權頁 |
| 提醒 | 三管道（網頁內、瀏覽器原生通知、服務端桌面通知），同一事件不重複提醒 |
| 授權 | 簽章租約 ＋ 純 Python Ed25519（RFC 8032）離線驗章、機器指紋、續期／到期停止、撤銷、功能分級、時鐘篡改防護 |
| 更新檢查 | 六項約束的版本檢查（不下載、不自動安裝） |
| Cloudflare 後端 | `/v1/activate`、`/v1/renew`、`/v1/latest`、`/catalog.json`、D1 資料表、後台操作、公開重新申請頁 |

**明確不做**：圖片解析、模型訓練、趨勢預測、自動下單、自動下載安裝更新、對外開放本機服務、Yahoo Finance。

---

## 環境需求

| 項目 | 版本／說明 |
| --- | --- |
| Python | 3.12（實測 3.12.3） |
| 執行期依賴 | `numpy==2.5.3`、`pandas==3.0.6`（其餘全部為標準庫） |
| 開發依賴 | `pytest==9.1.1` |
| Node.js | 24（僅用於 `ocaievo/cloudflare/` 的 `node --test`；無 npm 依賴） |
| 作業系統 | 開發與實機驗證環境為 Linux（Wayland ＋ Chrome）；桌面通知的 macOS／Windows 分支未實機驗證 |

## 安裝

```bash
cd ocaievo
python3 scripts/bootstrap_env.py     # 建立 .venv 並安裝 requirements.txt、requirements-dev.txt
```

## 執行

所有指令的工作目錄為 `ocaievo/`：

```bash
cd ocaievo

# 啟動本機網頁服務（前景，Ctrl-C 結束；只 bind 127.0.0.1）
.venv/bin/python -m ediaad serve --port 8787

# 一鍵啟動（已在執行則只開瀏覽器；否則背景啟動、等就緒、開瀏覽器）
python3 scripts/ediaad_launcher.py
./stop.sh                            # 停止服務

# 相似度路線：在歷史序列中找相似片段並統計後續走勢
.venv/bin/python -m ediaad match --data history.csv --sample sample.csv \
    --top 20 --horizon 10 --out report.json

# 監控輪詢（--once 只跑一輪）
.venv/bin/python -m ediaad monitor --config watchlist.json --once

# 授權
.venv/bin/python -m ediaad license status
.venv/bin/python -m ediaad license activate --key <密鑰>
.venv/bin/python -m ediaad license renew
```

### 環境變數

| 變數 | 用途 | 預設 |
| --- | --- | --- |
| `EDIAAD_HOME` | 資料根目錄（`ediaad.db`、`lease.json`、`settings.json`、`watchlist.json`、`keys.json` 等） | `~/.local/share/ediaad` |
| `EDIAAD_PORT` | 本機服務埠 | `8787` |
| `EDIAAD_LICENSE_URL` | 授權服務位址（啟用／續期需要） | 無 |
| `EDIAAD_LICENSE_PUBLIC_KEY` | 授權簽章公鑰（未設定時以內建佔位值 fail-closed） | 無 |
| `EDIAAD_UPDATE_URL` | 版本 manifest 位址 | 無 |
| `EDIAAD_DEBUG` | 除錯輸出 | 無 |
| `TWELVEDATA_API_KEY` | Twelve Data 金鑰（正式來源為 `$EDIAAD_HOME/keys.json`） | 無 |

## 測試與驗證

```bash
# 1) Python 測試（離線可跑，無需網路）
cd ocaievo && .venv/bin/python -m pytest -q
#    實測：1007 passed

# 2) Cloudflare Worker 測試（node:sqlite 假 D1 ＋ WebCrypto Ed25519）
cd ocaievo/cloudflare && node --test
#    實測：82 passed

# 3) 工作流程文件結構驗證
cd prework && python3 .project-workflow/scripts/validate_workflow.py .
#    實測：exit 0
```

已交付程式碼的樹狀雜湊（依 `prework/docs/workflow/PROJECT.md`「版本標記」的計算慣例）：

```text
ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab   （ocaievo/ 共 122 檔）
```

---

## 已知限制

- **未部署**：Cloudflare Worker、D1、網域皆未建立，`wrangler.toml` 使用佔位值；後端只在本機以假 D1 驗證。啟用／續期需要自備授權服務。
- 未以真實 Cloudflare 帳號／D1／網域驗證，也未以真實 Twelve Data 金鑰連線驗證（需要金鑰）。
- 台股僅支援日線（來源限制）；桌面通知只在 Linux 實機驗證。
- 完整清單見 [`prework/docs/workflow/DELIVERY.md`](prework/docs/workflow/DELIVERY.md) 第 3、4、5 節。

## 授權條款

本倉庫目前**未附任何開源授權條款**（未建立 `LICENSE`）；在權利人補上授權前，預設保留所有權利。若打算讓他人使用，建議擇一加入（例如 MIT、Apache-2.0 或 GPL-3.0）。

本專案的工作流程文件沿用 [itmanapp/skills-agent-spec](https://github.com/itmanapp/skills-agent-spec)（`project-workflow` v1.0）之規則與範本。
