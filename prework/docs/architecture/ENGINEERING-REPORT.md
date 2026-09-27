# ediaad 軟體功能與架構設計報告

> **本文件的讀者設定**：假設你是一位從 0 開始接手的軟體工程師，不熟悉這個專案，也不熟悉金融市場。
> 因此第 2 章先建立領域概念，第 3 章說明軟體做什麼，第 4 章之後才是架構與演算法設計。
> 本文件只敘述**功能**與**架構設計**，不涉及開發流程、專案管理或排程規劃。

- 報告日期：2026-09-24
- 對應程式版本：Git tag `V1.0`（commit `4e6c2a7`），程式快照 `snap-2026-09-24-1ba6761235c8ac84`
- 涵蓋範圍：v0.2（已交付）與 v0.3（已定案、尚未實作）的功能與架構

---

# 1. 軟體定位

## 1.1 一句話

**ediaad 是一套在個人電腦上執行的市場規律偵測與監控提醒工具**：使用者給它一段「範例走勢」或一組參數，它會持續監控指定商品的價格，在出現相同規律時主動提醒，並統計歷史上出現同樣規律之後的走勢。

## 1.2 它解決什麼問題

| 使用者的困難 | ediaad 的做法 |
| --- | --- |
| 心中有一個「熟悉的型態」（例如區間盤整後假跌破又拉回），但只能靠肉眼一檔一檔翻歷史線圖 | 把型態形式化成**可計算的相對門檻**，在序列上滑動掃描 |
| 無法同時盯多個商品 | 監控清單 + 常駐輪詢 + 命中時提醒 |
| 主觀判斷不穩定、無法重現 | 同一輸入與參數永遠得到相同結果（無隨機性） |
| 圖表縮放不同，看起來就不一樣 | **所有門檻使用相對單位**，價格乘常數或平移後命中位置完全不變 |
| 不確定這個型態過去有沒有效 | 統計命中事件之後 N 根 K 線的上漲機率與報酬分佈 |
| 不想學指令、不想寫設定檔 | （v0.3）網頁操作 + 桌面圖示一鍵啟動 |

## 1.3 它明確不是什麼

不是下單系統（不連接券商、不持有金鑰、不執行任何交易）、不是預測模型（不訓練神經網路、不輸出價格預測或買賣建議）、不是雲端服務（v0.2 完全離線；v0.3 只有三種連線：市場資料、更新檢查、授權驗證）、不是圖片辨識工具（早期版本曾規劃解析 K 線截圖，已於 v0.2 移除）。

---

# 2. 領域概念（讀懂架構的前置知識）

這一章建立後面章節會用到的所有名詞。若你已熟悉金融資料，可略過。

## 2.1 K 線（Candle）與 OHLC

金融市場的價格資料通常以「一段時間的摘要」呈現，稱為 **K 線**。每根 K 線記錄四個價格：

| 欄位 | 意義 |
| --- | --- |
| **open（開）** | 這個時間區間開始時的價格 |
| **high（高）** | 區間內的最高價 |
| **low（低）** | 區間內的最低價 |
| **close（收）** | 區間結束時的價格 |
| **volume（量）** | 區間內的成交量 |

四個價格合稱 **OHLC**。程式用 `high - low` 描述「這根 K 線的振幅」，用 `close - open` 描述「這根是漲還是跌」。收盤價高於開盤價稱為**陽線／上漲**，反之稱為**陰線／下跌**。

## 2.2 時間週期（Interval）

同一份價格資料可以切成不同粗細的 K 線。本專案支援的週期為：

```
('1m', '5m', '15m', '1h', '4h', '1d')
 分鐘  分鐘  分鐘  小時  小時  日
```

**週期不同，同一段歷史的「根數」就不同**：100 根 1 小時 K 線約等於 4 天，100 根日線則約等於 5 個月。這個事實會在後面「規律參數」與「多市場支援」兩處造成重要影響。

## 2.3 規律（Pattern / 型態）

**規律**是指一段可命名的價格行為結構。本專案的第一號規律叫 `range_fakeout_reversion`，中文描述是：

> **「價格在一個區段持續一段時間，突然價格往下後馬上又回到區段的平均價格」**

這是技術分析中常見的「假跌破」（bear trap / spring）。它由三個連續的**相位**組成。

## 2.4 相位（Phase）

相位是規律內部的連續段落。`range_fakeout_reversion` 有三個：

```
收盤價
  │      ┌─ 盤整相位（價格在區間內來回）─┐
  │   ┌──┴───────────────────────────┐  │
  │   │  ~~~~~ 區間上緣 ~~~~~         │  │
  │   │  ~~~~~ 區間均值 ~~~~~         │  │  ┌─ 回歸相位
  │   │  ~~~~~ 區間下緣 ~~~~~         │  └──┤   收盤回到均值之上
  │   └──────────────────────────────┘     │
  │              ↓ 跌破相位                 │
  │           低點穿破區間下緣              │
  └────────────────────────────────────────────→ 時間
```

程式中每個相位都用**索引**表示（`range_start_index`、`range_end_index`、`breakdown_index`、`recovery_index`），因為索引可以精確斷言，也方便換算成時間。

## 2.5 ATR（平均真實區間）

**ATR** 衡量「最近每根 K 線平均波動多大」。它比單純的 `high - low` 更完整，因為它也考慮跳空：

```
真實區間 TR[i] = max( high[i] - low[i],
                     |high[i] - close[i-1]|,
                     |low[i]  - close[i-1]| )

ATR[i] = TR[i-period+1 .. i] 的平均值     （period 預設 14）
```

**ATR 在本專案的角色**：它是「把絕對價格換算成相對單位」的尺。例如「區間帶寬不超過 3 倍 ATR」這句話，在比特幣（價格 8 萬）和台積電（價格 1000）上都有相同的意義。

⚠️ **關鍵設計約束**：`ATR[i]` 只能使用索引 `i`（含）以前的資料。若用到未來的 K 線，就會產生「偷看未來」的資料洩漏，讓回測結果失真。

## 2.6 區間帶寬（band）

一個盤整區間內 **最高價與最低價的差距**：

```
band = max(high[區間內]) - min(low[區間內])
```

band 用來衡量「這個盤整區間有多寬」，也是「跌破深度」的基準：跌破深度 = `(區間最低價 - 跌破低點) / band`，所以深度是「跌破區間下緣多少個區間高度」。

## 2.7 視窗（Window）、候選池（Pool）、掃描（Scan）

| 名詞 | 定義 |
| --- | --- |
| **視窗** | 從序列中切出、長度固定為 W 的連續 K 線區間 |
| **候選池** | 拿來與範例比對的所有視窗集合。以步長 1 滑動時，長度 L 的序列會產生 `L - W + 1` 個候選 |
| **掃描** | 對候選池中每一個視窗計分並排序的過程 |

## 2.8 特徵向量（Feature Vector）與相似度分數

直接比較兩段價格序列會有問題：比特幣的 8 萬和 8 萬 1 的差異，與台積電的 1000 和 1001 的差異，數字上完全不同，但「形狀」可能一樣。

因此本專案先把每個視窗**壓縮成 10 個數字**（見 5.1），再比較這 10 個數字。這 10 個數字的組合叫**特徵向量**。

**相似度分數**是 0 到 1 的數字，越高越像，1 代表特徵完全相同。它由特徵距離轉換而來：`分數 = 1 / (1 + 距離)`。

## 2.9 重疊抑制（Overlap Suppression）

如果在一段行情上滑動掃描，同一段行情會被多個相鄰視窗命中（例如起點 0、1、2 的視窗高度重疊）。若不去重，排行榜會被同一段行情佔滿。

**重疊抑制**的規則：兩個候選片段的時間重疊比例超過門檻（預設 50%）時，只保留分數較高的那一個。

⚠️ **注意區分**：重疊抑制處理「同一段行情被多個視窗命中」；**提醒去重**（2.13）處理「同一事件被多輪輪詢重複命中」。兩者目的類似但層次不同。

## 2.10 後續走勢（Forward Path）與 horizon

某個命中片段**結束之後**緊接的 H 根 K 線，稱為該片段的**後續走勢**，H 稱為 horizon。

用途：如果歷史上這個規律出現 30 次，其中 18 次之後 20 根是上漲的，那上漲機率就是 60%。**這是本專案唯一提供的「統計」資訊，不是預測。**

## 2.11 尺度不變（Scale Invariance）—— 本專案最重要的性質

> **把整段序列的所有價格同乘一個正數 k，或加上一個常數，規律的判定結果與命中位置必須完全不變。**

為什麼重要：
- 價格量級不同（BTC 8 萬 vs DOGE 0.1）不該影響判定
- 圖表縮放不同不該影響判定（這正是使用者提出的原始需求）
- 週期不同、市場不同也不該影響判定

**如何達成**：所有特徵與門檻都使用**比值**或**以自身波動度正規化**的量，完全不使用絕對價格點位。這條性質由自動測試強制驗證（乘 0.01／0.5／1／1000 倍與三種平移）。

## 2.12 租約（Lease）、機器指紋（Machine Fingerprint）、features（v0.3 概念）

| 名詞 | 定義 |
| --- | --- |
| **密鑰（License Key）** | 使用者向作者申請的一組授權字串 |
| **啟用（Activate）** | 使用者輸入密鑰，軟體向伺服器換取一張**租約** |
| **租約** | 一份有到期日、有簽章的授權憑證，存在使用者電腦上。有效期內**完全離線可用** |
| **機器指紋** | 由 `/etc/machine-id` 等穩定來源算出的雜湊，用來讓一張租約只在一台機器有效 |
| **features** | 租約內的功能清單，例如 `["start","update"]`。可發「只能啟動、不能更新」的密鑰 |
| **簽章（Signature）** | 伺服器用私鑰對租約內容簽章，客戶端用內嵌的公鑰驗證。防止使用者篡改到期日 |

## 2.13 詞彙對照表

| 中文 | 程式中的名稱 | 說明 |
| --- | --- | --- |
| 序列 | `Series` | pandas DataFrame，欄位固定為 time/open/high/low/close/volume |
| 視窗 | `window` | 候選片段長度 W |
| 特徵 | `features` / `FEATURE_NAMES` | 10 維向量 |
| 相似片段 | `ScanMatch` | 掃描結果，含索引、分數與時間 |
| 規律規格 | `PatternSpec` | 一組可序列化的相對門檻 |
| 規律事件 | `PatternEvent` | 一次命中，含四個相位索引與信心值 |
| 後續統計 | `OutlookStats` | 樣本數、上漲機率、報酬統計 |
| 監控清單 | `Watchlist` | 要監控的商品與週期 |
| 提醒 | alert | 主控台一行摘要 + JSONL 事件 |
| 提醒去重鍵 | dedup key | (商品, 週期, 規律 ID, 事件開始時間) |

---

# 3. 功能

## 3.1 v0.2 已交付的功能

### F1. 環境安裝（`scripts/bootstrap_env.py`）

| 項目 | 內容 |
| --- | --- |
| 輸入 | 無（讀 `requirements.txt`、`requirements-dev.txt`） |
| 處理 | 建立 `.venv`（`venv --without-pip`）→ 下載 `get-pip.py` 取得 pip → 安裝依賴 |
| 輸出 | 可用的 `.venv`；exit code 0 表成功 |
| 設計要點 | 目標環境**沒有 sudo、沒有預裝 pip、沒有 curl**，因此不能依賴系統套件或 curl。流程必須可重複執行（冪等） |

### F2. 資料載入（`ediaad.data.load_csv`）

| 項目 | 內容 |
| --- | --- |
| 輸入 | OHLC CSV 檔案路徑（欄位 time, open, high, low, close, volume） |
| 處理 | 解碼（容忍 BOM）→ 欄位名正規化 → 驗證必要欄位 → 型別轉換 → 時間轉 UTC 並統一解析度 → 檢查重複時間 → 依時間升冪排序 |
| 輸出 | 符合欄位契約的 `Series`（pandas DataFrame） |
| 錯誤 | 缺欄位、空檔案、非數值、無法解析的時間、重複時間戳 → `DataFormatError` |

另有 `from_rows()` 供外部資料來源（如交易所 API 回應）建立序列，套用**完全相同**的驗證規則。

### F3. 多維形態特徵抽取（`ediaad.features.extract`）

將一個視窗壓縮成 10 維尺度不變向量（詳見 5.1）。另有批次版本 `extract_matrix(series, window, step)` 供掃描使用，輸出形狀為 `(候選數, 10)`，記憶體不隨視窗長度成長。

### F4. 相似度排序（`ediaad.similarity.rank`）

| 項目 | 內容 |
| --- | --- |
| 輸入 | 範例特徵向量、候選池矩陣 `(M, 10)`、權重向量（預設全 1） |
| 處理 | 以候選池的中位數與 IQR 做穩健正規化 → 計算加權 L1 距離 → 轉成分數 |
| 輸出 | 依分數由高到低排序的 `Match` 清單（同分以索引升冪） |
| 錯誤 | 權重長度不符、含負值、總和為 0 → `ConfigError` |

### F5. 滑動視窗掃描（`ediaad.scan.scan_similar`）

| 項目 | 內容 |
| --- | --- |
| 輸入 | 序列、範例（長度須等於 window）、window、top、step、overlap 門檻 |
| 處理 | 抽出全部候選特徵 → 計分排序 → 依分數順序貪婪接受互不衝突者 → 取前 N 筆 |
| 輸出 | `ScanMatch` 清單（含起訖索引、分數、起訖時間） |
| 錯誤 | 範例長度不符、序列短於視窗、top/step/overlap 不合法、缺 time 欄位 → `ConfigError` |

### F6. 後續走勢統計（`ediaad.outlook.forward_stats`）

| 項目 | 內容 |
| --- | --- |
| 輸入 | 片段清單、序列、horizon、`end_attr`（指名「片段結束」的欄位名） |
| 處理 | 逐片段計算 `close[end+H]/close[end] - 1`；`end+H` 超出序列者排除 |
| 輸出 | `OutlookStats`：樣本數、上漲機率（報酬嚴格大於 0）、平均／中位數報酬、母體標準差。樣本為 0 時其餘欄位為 `None` |

`end_attr` 的存在是為了讓兩條路線共用同一個函式：相似度掃描的 `ScanMatch` 用 `end_index`（預設），規律偵測的 `PatternEvent` 用 `recovery_index`。

### F7. 規律模型與具名規律（`ediaad.patterns`）

- `PatternSpec`：frozen dataclass，**在 `__post_init__` 就驗證所有欄位**，因此不合法的規格無法被建構出來
- `NAMED_PATTERNS`：內建具名規律，第一號為 `range_fakeout_reversion`
- `to_json` / `from_json`：序列化與還原（`sort_keys=True` 讓輸出穩定；`from_json` 拒絕缺欄位、多欄位與型別不符）

### F8. 規律偵測（`ediaad.patterns.detect`）

在整份序列上找出所有符合規格的事件（詳見 5.5）。回傳依「盤整相位長度由長到短」排序的 `PatternEvent` 清單，且同一段結構只保留最長的一次命中。

### F9. 由範例學習（`ediaad.patterns.learn`）

由一段數值範例推估出可用的 `PatternSpec`（詳見 5.7）。推估不出來時明確報錯，不回傳隨意參數。

### F10. 監控清單設定（`ediaad.monitor.load_config`）

讀入 JSON 設定檔並驗證，回傳 `Watchlist`。頂層鍵固定為：

```json
{
  "poll_interval_seconds": 60,
  "events_path": ".cache/events.jsonl",
  "cache_dir": ".cache/ohlcv",
  "pattern_id": "range_fakeout_reversion",
  "pattern_spec": null,
  "horizon": 20,
  "instruments": [{"symbol": "BTCUSDT", "interval": "1h"}]
}
```

`pattern_spec` 為 `null` 時使用內建規律；提供時以它為準，且其 `pattern_id` 必須與 `pattern_id` 一致（避免同一份設定出現兩個矛盾的身分）。缺鍵、未知鍵、型別錯誤、`instruments` 為空、週期不合法都會**指出出錯的鍵或索引位置**。

### F11. 監控迴圈與提醒（`ediaad.monitor.run_once` / `run_forever`）

| 項目 | 內容 |
| --- | --- |
| 輸入 | `Watchlist`、可注入的 `fetch`、`emit`、`warn`、`sleep`、`should_stop` |
| 處理 | 逐商品取得資料 → 檢查長度是否足夠 → 偵測 → 計算歷史統計 → 對**未提醒過**的事件發出提醒 |
| 輸出 | `RunResult`（processed / alerted / skipped / warnings） |
| 容錯 | 單一商品失敗只記 warning 並繼續；程式錯誤向上拋出，不被吞掉 |

**提醒去重鍵** = `(商品, 週期, 規律 ID, 事件開始時間)`。用時間而非索引，因為不同輪詢的序列長度可能改變。

### F12. 提醒輸出（`format_alert` / `append_event`）

- 主控台：單行摘要 `[ALERT] <symbol> <interval> <pattern_id> <start>..<end> confidence=<c> history_up_prob=<p> samples=<n>`
- 事件檔：JSONL，一行一個 JSON 物件，**附加寫入、永不改寫既有行**。九個欄位：symbol、interval、pattern_id、event_start_time、event_end_time、confidence、detected_at、history_up_probability、history_samples

### F13. 資料來源（`ediaad.sources.binance`）

以 Binance 公開端點取得 K 線並寫入本地快取。快取策略：

| 情況 | 行為 | `data_source` |
| --- | --- | --- |
| 快取仍在有效期內 | 直接讀快取，**不發出請求** | `cache` |
| 快取過期或不存在 | 重新取得並覆寫快取 | `binance` |
| 取得失敗但有過期快取 | 使用過期快取 | `cache-stale` |
| 取得失敗且無快取 | 丟出 `SourceError` | — |

**只用公開端點，不接觸任何金鑰或私有 API。**

### F14. 命令列介面（`ediaad.cli`）

```bash
python -m ediaad match  --data <csv> --sample <csv> --top N --horizon H --out report.json
python -m ediaad monitor --config <json> [--once]
```

| exit code | 意義 |
| --- | --- |
| 0 | 成功 |
| 1 | 執行期失敗（例如輸出檔不可寫、來源失敗） |
| 2 | 輸入或設定錯誤 |

`match` 輸出 JSON 報表，頂層鍵固定為 `sample`、`params`、`data_source`、`matches`、`outlook`。

## 3.2 v0.3 規劃的功能

### 網頁操作（取代命令列成為主要介面）

| 功能 | 說明 |
| --- | --- |
| G1 一鍵啟動 | 雙擊桌面圖示 → 服務背景啟動 → 自動開啟預設瀏覽器；已在執行時只開瀏覽器 |
| G2 優雅關閉 | 網頁上的「關閉服務」按鈕與 `stop.sh` |
| G3 監控清單管理 | 新增／移除商品（**下拉搜尋，不需打代號**）、選週期、調整輪詢間隔 |
| G4 規律參數面板 | 白話參數 + **即時命中預覽**（改參數馬上看到「這檔商品會命中幾次」） |
| G5 範例學習 | 上傳／貼上 CSV → 按「學習」→ 顯示推估參數與命中預覽 |
| G6 即時提醒 | 網頁內提示 + 事件歷史清單（可依商品／時間篩選） |
| G7 K 線圖 | 瀏覽器 `<canvas>` 繪製，**標出盤整／跌破／回歸三個相位** |
| G8 歷史回看 | 表單化的 `match`：選商品與範圍 → 相似片段排行與後續統計 |
| G9 系統狀態 | 最後輪詢時間、各商品資料來源、錯誤訊息 |
| G10 版本頁 | 目前版本、最新版本、發佈日期、說明 |
| G11 授權頁 | 授權狀態、剩餘天數、更換密鑰、重新申請連結 |

### 多市場資料來源

| 市場 | 來源 | 特殊處理 |
| --- | --- | --- |
| 加密貨幣 | Binance | 無 |
| 台股 | TWSE 官方 | **除權息處理**、交易日曆、民國年日期轉換 |
| 美股 | Twelve Data | 使用者自行申請金鑰並填入 |
| 自訂 | 使用者上傳 CSV | 沿用 v0.2 的 `load_csv` |

### 授權與更新

| 功能 | 說明 |
| --- | --- |
| G12 首次啟用 | 輸入密鑰 + 機器指紋 → 向伺服器換取簽章租約（30 天） |
| G13 離線可用 | 租約到期前完全離線運行 |
| G14 自動續期 | 每次開啟、每 24 小時自動連線驗證；成功即重算 30 天 |
| G15 到期停止 | 超過 30 天未連線 → 停止服務並顯示重新申請訊息 |
| G16 更換密鑰 | 網頁可隨時輸入新密鑰 |
| G17 撤銷 | 作者撤銷後，使用者下次驗證即停止 |
| G18 功能分級 | 以 `features` 區分「可啟動」與「可更新」 |
| G19 更新檢查 | 每次開啟與每 24 小時檢查版本，**只顯示不下載** |
| G20 來源清單更新 | 市場來源與商品清單可透過更新攜帶（見 7.2） |

### 通知

| 管道 | 適用時機 |
| --- | --- |
| 網頁內提示 | 網頁開著 |
| 瀏覽器原生通知（三平台同一套） | 網頁開著、可縮到背景 |
| 服務端桌面通知（Linux／macOS／Windows） | **網頁關閉但服務仍在執行** |

## 3.3 明確不做

圖片解析（截圖不進入程式）｜模型訓練｜趨勢方向標籤與價格預測｜自動下單｜區網或網際網路存取｜自動下載安裝更新｜Yahoo Finance｜規律參數加密發放

---

# 4. 架構設計

## 4.1 三條設計原則

### 原則 1：計算不碰 I/O

**數值計算模組不讀寫檔案、不連網、不輸出任何訊息。** 檔案存取集中在 `data`、`sources`、`store`；網路集中在 `sources`；使用者輸出集中在 `cli` 與 `monitor`。

這條原則的直接效益：v0.3 要新增整個網頁介面、授權、多市場資料，而**核心運算 0 行改動**。因為新介面只是換一組注入實作，不需要碰計算邏輯。

### 原則 2：外部效果一律可注入

`monitor.run_once(watchlist, fetch, emit, state, warn)` 的所有外部效果都是參數：

| 參數 | CLI 版的實作 | 網頁版的實作（v0.3） |
| --- | --- | --- |
| `fetch` | Binance API | 依使用者選的來源分派 |
| `emit` | 印到 stdout + 寫 JSONL | 推 SSE 給瀏覽器 + 桌面通知 + 寫 SQLite |
| `warn` | 印到 stderr | 顯示在網頁的系統狀態頁 |
| `sleep` / `should_stop` | `time.sleep` / 永遠 False | 可被網頁的「停止」按鈕中斷 |

這讓監控邏輯**完全離線可測**（185 個測試中沒有一個連網）。

### 原則 3：錯誤分層與可預期性

| 例外 | 意義 | CLI exit code |
| --- | --- | --- |
| `EdiaadError`（基底） | 所有可預期錯誤的父類別 | — |
| `DataFormatError` | 輸入資料格式或內容不合法 | 2 |
| `ConfigError` | 設定、參數或規格不合法 | 2 |
| `SourceError` | 外部來源取得失敗 | 1 |

監控迴圈只攔截 `(EdiaadError, KeyError, IndexError)`——前三者是領域錯誤，後兩者是來源轉接器回傳畸形資料框架。**其他例外（程式錯誤）一律向上拋出**，避免缺陷被 warning 掩蓋。

## 4.2 分層與依賴方向

```
                    ┌──────────────────────────────┐
   I/O 與協調層      │  cli      monitor    (v0.3)  │
                    │                      web/    │
                    │                      app.py  │
                    │                      store.py│
                    │                      notify/ │
                    └───────────┬──────────────────┘
                                │ 只能往下依賴
                    ┌───────────▼──────────────────┐
   領域邏輯層        │  patterns   ← 規律模型與偵測   │
                    │  scan  similarity  outlook    │
                    │  features                     │
                    └───────────┬──────────────────┘
                                │
                    ┌───────────▼──────────────────┐
   基礎層            │  errors   data   sources/     │
                    └──────────────────────────────┘
```

**依賴方向永遠單向**：`cli` → `monitor` → `patterns` → `errors`。沒有循環依賴。`outlook` 刻意不匯入 `scan`（改用 `Protocol` 描述「有 `end_index` 的物件」），避免兩者互相依賴。

## 4.3 模組清單

| 模組 | 行數 | 職責 | 對外 API |
| --- | --- | --- | --- |
| `errors.py` | 25 | 共用例外階層 | `EdiaadError`、`DataFormatError`、`ConfigError`、`SourceError` |
| `data.py` | 103 | 序列契約與 CSV／資料列載入 | `SERIES_COLUMNS`、`PRICE_COLUMNS`、`TIME_UNIT`、`load_csv`、`from_rows` |
| `features.py` | 129 | 10 維尺度不變特徵 | `FEATURE_NAMES`、`extract`、`extract_matrix` |
| `similarity.py` | 102 | 穩健正規化與加權排序 | `Match`、`DEFAULT_WEIGHTS`、`rank` |
| `scan.py` | 86 | 滑動視窗掃描與重疊抑制 | `ScanMatch`、`scan_similar` |
| `outlook.py` | 86 | 後續走勢統計 | `OutlookStats`、`forward_stats` |
| `patterns.py` | 451 | 規律模型、ATR、偵測器、範例學習 | `PatternSpec`、`PatternEvent`、`NAMED_PATTERNS`、`RECOVERY_TARGETS`、`to_json`、`from_json`、`atr`、`detect`、`learn` |
| `sources/base.py` | 25 | 來源介面宣告 | `OHLCVClient`、`ALLOWED_INTERVALS` |
| `sources/binance.py` | 114 | Binance 取得與快取 | `BASE_URL`、`ALLOWED_INTERVALS`、`DEFAULT_CACHE_DIR`、`cache_path`、`fetch_ohlcv` |
| `monitor.py` | 329 | 設定、輪詢、去重、錯誤隔離、提醒輸出 | `Instrument`、`Watchlist`、`AlertState`、`RunResult`、`load_config`、`run_once`、`run_forever`、`format_alert`、`append_event`、`event_times`、`ALLOWED_INTERVALS` |
| `cli.py` | 218 | 命令列 | `build_parser`、`main` |
| `__main__.py` | 8 | `python -m ediaad` 入口 | — |

**1,695 行總計**，其中 904 行是純計算（`errors`、`features`、`similarity`、`scan`、`outlook`、`patterns`、`sources/base`）。

## 4.4 資料契約

這些結構是模組之間的介面，理解它們就理解了一半的架構。

### Series（序列）

```
pandas DataFrame，欄位固定且順序固定：
  time    datetime64[ns, UTC]   升冪、無重複
  open    float64
  high    float64
  low     float64
  close   float64
  volume  float64
```

**時間解析度明定為 `ns`**：這不是隨便選的。曾經有一個缺陷（F-001）是「交易所路徑產生 ms、CSV 路徑產生 us」，導致同一份資料經過快取往返後 dtype 改變、快取不再透明。統一解析度是契約的一部分。

### PatternSpec（規律規格）

```
pattern_id                 str     規律識別名
range_bars_min             int     盤整相位最短根數
range_bars_max             int     盤整相位最長根數
band_atr_multiple_max      float   區間帶寬上限（ATR 倍數）
atr_period                 int     ATR 週期
breakdown_bars_max         int     跌破必須在盤整結束後幾根內出現
breakdown_depth_band_min   float   跌破深度下限（band 倍數）
breakdown_depth_band_max   float   跌破深度上限（band 倍數）
recovery_bars_max          int     回歸必須在跌破後幾根內完成
recovery_target            str     回歸目標，目前只有 "range_mean"
```

**全部是相對單位，沒有任何價格欄位**——這是尺度不變在資料結構層的保證。`__post_init__` 驗證所有欄位（含交叉檢查，如 `min <= max`）。

內建 `range_fakeout_reversion` 的預設值：

```
range_bars_min=20, range_bars_max=120, band_atr_multiple_max=3.0,
atr_period=14, breakdown_bars_max=2,
breakdown_depth_band_min=0.2, breakdown_depth_band_max=1.5,
recovery_bars_max=5, recovery_target="range_mean"
```

### PatternEvent（規律事件）

```
pattern_id          str
range_start_index   int     盤整相位起始
range_end_index     int     盤整相位結束
breakdown_index     int     跌破相位
recovery_index      int     回歸相位（事件的結束位置）
confidence          float   0~1
band                float   實測帶寬
breakdown_depth     float   實測跌破深度
recovery_bars       int     實際回歸根數
```

### 其他結構

| 結構 | 欄位 |
| --- | --- |
| `Match` | index、score、feature_distance |
| `ScanMatch` | start_index、end_index、score、time_start、time_end |
| `OutlookStats` | samples、up_probability、mean_return、median_return、std_return |
| `Instrument` | symbol、interval |
| `Watchlist` | poll_interval_seconds、events_path、cache_dir、pattern_id、pattern_spec、horizon、instruments |
| `RunResult` | processed、alerted、skipped、warnings |
| `AlertState` | `seen` 集合 + `should_alert()` / `mark_alerted()` |

## 4.5 三條資料流

### 資料流 A：歷史回看（`match`）

```
CSV ─load_csv→ Series
                │
範例 CSV ─load_csv→ 範例視窗（長度須等於 window）
                │
                ├─ features.extract(範例)            → 範例特徵向量
                │
                └─ features.extract_matrix(序列, W, step) → 候選池 (M, 10)
                                    │
                          similarity.rank(範例特徵, 候選池, 權重)
                                    │
                          scan 的重疊抑制（貪婪）
                                    │
                          outlook.forward_stats(命中片段, 序列, H)
                                    │
                          JSON 報表（五個頂層鍵）
```

### 資料流 B：監控提醒（`monitor`）

```
Watchlist ──→ 逐商品
                │
          fetch(symbol, interval)  ←── Binance 或本地快取
                │
          長度檢查（< range_bars_min+1 → 跳過並記 warning）
                │
          patterns.detect(序列, spec) → [PatternEvent]
                │
          outlook.forward_stats(事件, 序列, H, end_attr="recovery_index")
                │
          逐事件：去重鍵 = (symbol, interval, pattern_id, 事件開始時間)
                │
          未提醒過 → emit() → 主控台摘要 + JSONL 事件
```

### 資料流 C：範例學習（`learn`）

```
範例序列
   │
投影片段偵測（以滾動中位數 TR 為尺，由嚴到鬆找最長區間）
   │
盤整相位 → 其後的極低點＝跌破相位 → 之後第一根收盤回到均值＝回歸相位
   │
把三個相位的實測相對量放寬成容差區間
   │
PatternSpec（可直接餵給 detect）
```

## 4.6 快取與存放位置

| 產物 | 位置 | 生命週期 |
| --- | --- | --- |
| 虛擬環境 | `.venv/` | 安裝後長期 |
| K 線快取 | `<cache_dir>/<symbol>_<interval>.csv` | 由 `max_age` 控制新鮮度 |
| 事件檔 | `events_path`（預設 `.cache/events.jsonl`） | 永久累積、不自動清理 |
| （v0.3）SQLite | `~/.local/share/ediaad/` | 事件、提醒狀態、租約 |

三者都在 `.gitignore` 中。

---

# 5. 核心演算法設計

這一章是整個專案技術含量最高的部分。

## 5.1 10 維特徵（`features.extract`）

設視窗有 N 根 K 線。**所有特徵都是比值或正規化量，因此乘上正數 k 後全部不變。**

| # | 名稱 | 公式 | 直覺 |
| --- | --- | --- | --- |
| 1 | `total_return` | `close[-1] / close[0] - 1` | 這段期間整體漲跌多少 |
| 2 | `return_std` | 逐根報酬 `(close[i]-close[i-1])/close[i-1]` 的母體標準差 | 波動程度 |
| 3 | `mean_body_ratio` | `mean( \|close-open\| / (high-low) )` | 平均實體佔全距的比例（趨勢感） |
| 4 | `mean_upper_shadow_ratio` | `mean( (high - max(open,close)) / (high-low) )` | 平均上影線比例（上方賣壓） |
| 5 | `mean_lower_shadow_ratio` | `mean( (min(open,close) - low) / (high-low) )` | 平均下影線比例（下方支撐） |
| 6 | `bull_ratio` | `count(close > open) / N` | 上漲根數比例 |
| 7 | `max_drawdown` | `1 - min(close / 累積最高收盤)` | 最大回撤（正值） |
| 8 | `ma_slope_normalized` | 收盤對索引做最小平方迴歸的斜率 ÷ 收盤母體標準差 | 趨勢方向與陡度（已正規化） |
| 9 | `volume_ratio` | `mean(後半量能) / mean(前半量能)`，前半為 0 時取 0 | 量能增減 |
| 10 | `close_position` | `(close[-1] - min(low)) / (max(high) - min(low))` | 收盤位在區間中的位置 |

**退化情境一律回傳有限值而非 NaN**：所有除法都使用 `np.divide(..., where=分母 != 0)` 或先檢查分母。例如全平坦的視窗（`high == low`）會得到實體比 0、影線比 0、斜率 0、位置 0。

**為什麼選這 10 個**：它們涵蓋「方向、波動、K 線內部結構、量能、相對位置」五個面向，且全部尺度不變。這組特徵用於**相似度路線**（找出「差不多」的片段）；**規律路線**不依賴這組特徵，而是直接檢查閾值條件（見 5.5）。兩條路線刻意分開，因為「像不像」與「是否符合規則」是兩種不同的問題。

## 5.2 相似度計算（`similarity.rank`）

**問題**：10 個特徵的單位與尺度差異很大（報酬是 0.01 級、量能比可能是 3.0），不能直接相加。

**解法：以候選池自身的統計量做穩健正規化。**

```
候選池 P 形狀 (M, 10)

1. 對每一維 j 計算：
     median[j] = 中位數(P[:, j])
     IQR[j]    = 第 75 百分位 - 第 25 百分位

2. 正規化（IQR 為 0 的維度退化為 0，避免除以零）：
     z(x)[j] = (x[j] - median[j]) / IQR[j]    若 IQR[j] ≠ 0
             = 0                                若 IQR[j] = 0

3. 加權 L1 距離（權重正規化，所以權重的絕對尺度不影響結果）：
     d = Σ w[j] · |z(範例)[j] - z(候選)[j]|  /  Σ w[j]

4. 轉成分數：
     score = 1 / (1 + d)          ∈ (0, 1]
```

**為什麼用中位數與 IQR 而不是平均數與標準差**：中位數與 IQR 對離群值不敏感。價格資料常有一兩根極端 K 線，用平均數會讓整組統計被單點拉歪。

**排序穩定性**：使用 `np.lexsort` 先依分數降冪、再依索引升冪，因此同分時的順序唯一且可重現（這對「同一輸入必須得到相同結果」的品質要求是必要的）。

## 5.3 掃描與重疊抑制（`scan.scan_similar`）

```
輸入：序列（長度 L）、範例（長度 = W）、W、top、step、overlap

1. 驗證：範例長度 == W、L >= W、top >= 1、step >= 1、0 <= overlap < 1、序列有 time 欄位
2. 抽範例特徵：extract(範例)
3. 抽全部候選特徵：extract_matrix(序列, W, step) → (M, 10)
4. 候選起始索引：starts = range(0, L - W + 1, step)
5. rank(...) 取得分數由高到低的順序
6. 依序貪婪接受：
     對每個候選，檢查它與「已接受的所有片段」的重疊比例
     重疊比例 = max(0, min(e1,e2) - max(s1,s2) + 1) / W
     若與任何已接受者的重疊比例 > overlap → 丟棄
     接受後，累計達 top 筆即停止
7. 為每筆補上時間界線（time_start、time_end）
```

**為什麼用貪婪而不是全域最佳化**：貪婪是 O(M·K)、結果可預期、且第一版不需要「最大化總分」這種目標。這個取捨的代價是可能不是理論最佳解，但換來可預測性。

**「恰好等於門檻」必須保留**：比較使用嚴格大於（`> overlap`），所以重疊恰好 50% 的兩個候選都會被保留。這是刻意的邊界定義，並有專門測試。

**效能設計**：候選特徵矩陣形狀為 `(M, 10)`，**不隨視窗長度成長**。以 10,000 根、視窗 60 為例，矩陣是 `(9941, 10)`，而非 9941 份長度 60 的副本。

## 5.4 ATR 的實作技巧（`patterns.atr`）

```
previous_close[0] = close[0]
TR[i] = max( high[i]-low[i],
             |high[i] - previous_close[i]|,
             |low[i]  - previous_close[i]| )

ATR[i] = TR[i-period+1 .. i] 的平均     (i >= period-1)
       = NaN                            (i <  period-1)
```

**滾動平均以 `cumsum` 實作**，讓每個索引的 ATR 都是 O(1) 而非 O(period)：

```
cumulative = cumsum(insert(TR, 0, 0))          # 長度 n+1
ATR[period-1:] = (cumulative[period:] - cumulative[:-period]) / period
```

**「不引用未來」是硬性要求**：`ATR[i]` 只用到索引 `i`（含）以前的 TR。這條被測試強制驗證——把植入位置之後的資料乘 10，`ATR[range_end]` 的差異必須在 1e-12 內。

## 5.5 規律偵測（`patterns.detect`）—— 本專案的核心演算法

### 判定條件（完整定義）

給定序列與 `PatternSpec`，尋找滿足以下六條的結構：

**① 盤整相位**：連續區間 `[i, j]`
- 長度落在 `[range_bars_min, range_bars_max]`
- `band = max(high[i..j]) - min(low[i..j])`
- 要求 `band <= band_atr_multiple_max × ATR[j]`（**ATR 只用 j 以前的資料**）

**② 假跌破**：`k`，滿足 `j < k <= j + breakdown_bars_max`
- `low[k] < min(low[i..j])`（低點穿破區間下緣）
- `depth = (min(low[i..j]) - low[k]) / band` 落在 `[breakdown_depth_band_min, breakdown_depth_band_max]`

**③ 回歸**：`m`，滿足 `k <= m <= k + recovery_bars_max`
- `close[m] >= mean(close[i..j])`（收盤回到區間均值之上）

**④ 反例防護**：回歸之前若出現比 `low[k]` 更低的低點，該次跌破不成立

**⑤ 信心值**：三個條件滿足度的平均（見 5.6）

**⑥ 去重**：同一段結構被多個長度命中時，只保留最長的一次

### 實作上的兩個關鍵技巧

**技巧 1：用二分搜尋找最長合法區間，而不是逐一列舉**

對固定的 `j`，`band` 是「起始索引 `i` 越小則單調不減」的函數（視窗變大，最大值不減、最小值不增）。因此「`band <= limit` 的最長區間」等價於「最小的合法 `i`」，可以用二分搜尋：

```
對每個 j：
  left  = max(0, j - range_bars_max + 1)
  right = j - range_bars_min + 1        # 最短視窗的起始索引
  若 band(right, j) > limit → 沒有合法區間，跳過
  二分搜尋最小的 i 使得 band(i, j) <= limit
```

這把複雜度從 O(range_bars_max²) 降到 O(log(range_bars_max) × range_bars_max)，是模組能處理 10,000 根序列的關鍵。

**技巧 2：取最長區間而非最緊區間**

`detect` 的語意是「最長可行區間」。副作用是：若區間邊界外剛好有一根仍在門檻內的 K 線，`range_start_index` 會往外擴一格。這是刻意的取捨（可預期、不需複雜的區間切割），但**測試夾具必須據此設計**——作者在開發時就踩過這個坑（見附錄的缺陷紀錄）。

### 為什麼 `detect` 與相似度是兩條獨立路線

| | 相似度路線（`rank` + `scan`） | 規律路線（`detect`） |
| --- | --- | --- |
| 問題 | 「這段像不像那段」 | 「這段符不符合規則」 |
| 輸入 | 範例 + 相似度門檻 | 具名規律或學習來的規格 |
| 輸出 | 連續分數 + 排行 | 布林命中 + 相位索引 + 信心值 |
| 可解釋性 | 較低（分數是黑盒距離） | 高（每個條件都可單獨檢查） |
| 誤報控制 | 靠門檻排序 | 靠四種反例防護 |
| 用途 | 探索、找出「差不多」 | 監控提醒 |

兩者共用 `features`（相似度用）與 `atr`（規律用），但不互相依賴。

## 5.6 信心值（`_confidence`）

```
band_score     = 1 - min(band / limit, 1)                     帶寬越窄越好
depth_score    = 1 - |depth - 中點| / (深度範圍/2)             深度越接近範圍中點越好
                 中點 = (depth_min + depth_max) / 2
                 深度範圍為 0 時取 1
recovery_score = 1 - recovery_bars / recovery_bars_max         回歸越快越好

confidence = clip(mean([band_score, depth_score, recovery_score]), 0, 1)
```

**這不是機率**，只是三個條件滿意度的平均，用來讓使用者排序與篩選。

## 5.7 範例學習（`patterns.learn`）

**問題**：使用者不想自己猜門檻。他手上有一段「滿意的走勢」，希望軟體推出參數。

**演算法**：

```
1. 長度檢查（至少 12 根）；計算「真實區間的滾動中位數」mtr
2. 找盤整相位：
     門檻階梯 = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0) 倍 mtr
     由嚴到鬆，取「第一個能找到合法區間」的門檻
     在該門檻下，用與 detect 相同的二分搜尋取最長區間
3. 跌破相位 = 盤整區間之後的最低點；若未低於區間下緣 → ConfigError
4. 回歸相位 = 跌破之後第一根收盤回到區間均值；若找不到 → ConfigError
5. 把實測相對量放寬成容差：
     range_bars_min = round(實際根數 × 0.5)
     range_bars_max = round(實際根數 × 1.5)
     band_atr_multiple_max = clip(實際 band / ATR × 1.2, 1.0, 6.0)
     breakdown_depth_band_min = max(0.05, 實際深度 × 0.7)
     breakdown_depth_band_max = min(3.0,  實際深度 × 1.3)
     recovery_bars_max = 實際回歸根數 + 2
```

**為什麼用「滾動中位數」而不是平均 ATR 當尺**：這是開發中修掉的缺陷之一。範例裡若有一根振幅極大的 K 線（例如前綴的趨勢段），平均 ATR 會被單點拉高，讓緊鄰它的一段短視窗被誤判為「窄區間」。中位數對單點極值不敏感。

**容差全部朝「更容易命中範例」的方向放寬**，確保推估出的規格一定能命中自己的範例。

## 5.8 後續走勢統計（`outlook.forward_stats`）

```
對每個片段：
  end    = 依 end_attr 取得的索引（ScanMatch 用 end_index，PatternEvent 用 recovery_index）
  若 end + H >= 序列長度 → 排除（不足 H 根）
  報酬 = close[end + H] / close[end] - 1

彙總：
  samples        = 納入的片段數
  up_probability = mean(報酬 > 0)        ← 注意：恰好為 0 不算上漲
  mean_return    = 平均
  median_return  = 中位數
  std_return     = 母體標準差（ddof=0）
  無樣本時 → samples=0，其餘欄位為 None（而非 0）
```

**「不足 H 根就排除」很重要**：若把尾端納入，會系統性偏向某些結果（因為最近的片段還沒走完）。

**`None` 而非 0**：0 會被誤讀為「報酬為 0」，`None` 明確表示「沒有樣本」。

**已知的統計偏誤**：相似片段之間可能時間相近、高度相關，使上漲機率被重複計數影響。第一版只揭露樣本數與片段時間範圍，不做獨立性處理。

## 5.9 提醒去重（`monitor.AlertState`）

```
去重鍵 = (symbol, interval, pattern_id, str(事件 range_start_index 對應的時間))

run_once 對每個事件：
  若 state.should_alert(key) 為真：
      state.mark_alerted(key)
      emit(...)
```

**為什麼用時間而不是索引**：不同輪詢取得序列的長度可能不同（新 K 線陸續進來），索引會位移，時間不會。

**v0.2 的限制**：`AlertState` 只在記憶體，程式重啟後同一事件會再提醒一次。v0.3 會改為 SQLite 落地。

---

# 6. v0.3 目標架構

## 6.1 元件圖

```
┌─ 使用者桌面（全部在本機） ──────────────────────────────────────┐
│                                                                  │
│  桌面圖示 (ediaad.desktop)                                        │
│     └→ 啟動器：已在執行？→ 開瀏覽器                                │
│                 否      → 啟服務 → 等就緒 → 開瀏覽器              │
│                                                                  │
│  ┌─ ediaad 服務（Python，bind 127.0.0.1:8787）────────────────┐  │
│  │                                                             │  │
│  │  ┌─ 新增（v0.3）───────────────────────────────────────┐   │  │
│  │  │  app.py       協調：監控迴圈 + Web + 排程            │   │  │
│  │  │  web/         HTTP + SSE + 靜態資源（原生 HTML/JS）  │   │  │
│  │  │  license.py   租約、Ed25519 驗章、機器指紋、時鐘防護  │   │  │
│  │  │  update.py    版本檢查（讀 manifest）                │   │  │
│  │  │  notify/      網頁 + 桌面三平台通知                   │   │  │
│  │  │  markets/     幣安 / TWSE / Twelve Data / 自訂 CSV   │   │  │
│  │  │  store.py     SQLite：事件、提醒狀態、租約快取        │   │  │
│  │  │  config.py    設定解析 + 驗證 + 原子寫入              │   │  │
│  │  └─────────────────────────────────────────────────────┘   │  │
│  │                                                             │  │
│  │  ┌─ 保留（0 改動）──────────────────────────────────────┐   │  │
│  │  │  patterns  features  similarity  scan  outlook  data  │   │  │
│  │  │  errors                                               │   │  │
│  │  └───────────────────────────────────────────────────────┘  │  │
│  │                                                             │  │
│  │  ┌─ 重構（向後相容）────────────────────────────────────┐   │  │
│  │  │  monitor.py  AlertState 落地、append_event 移出、      │   │  │
│  │  │              load_config 拆分                          │   │  │
│  │  │  cli.py      保留，新增 serve 與 license 子命令        │   │  │
│  │  └───────────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
         │                      │                    │
    ①市場資料              ②更新檢查           ③授權驗證
         ▼                      ▼                    ▼
┌─ Cloudflare（只做版本記錄與更新服務 + 授權服務）─────────────────┐
│  Pages/R2   GET /v1/latest        版本 manifest（靜態、可快取）   │
│  Pages/R2   GET /catalog.json     市場來源與商品清單（可更新）     │
│  Worker     POST /v1/activate     啟用換租約                      │
│  Worker     POST /v1/renew        續租（寫 renewals 紀錄）        │
│  Worker     公開申請頁             過期者自助重新申請（黑名單除外） │
│  D1         keys / devices / renewals / blacklist / audit        │
│  後台       批次產生、清單、撤銷、統計、黑名單、稽核               │
│  Secret     Ed25519 簽章私鑰                                     │
└──────────────────────────────────────────────────────────────────┘
```

## 6.2 服務生命週期與啟動器

```
使用者雙擊桌面圖示
  ├─ 已在執行？（PID 檔 + 埠探測）── 是 → 直接 xdg-open（不啟第二個）
  └─ 否 → 背景啟動服務（bind 127.0.0.1:8787）
           ├─ 等就緒（health check，最多 10 秒）
           ├─ xdg-open http://127.0.0.1:8787
           └─ 頁面載入 → 觸發更新檢查與授權驗證
關閉：網頁「關閉服務」按鈕 或 stop.sh（優雅結束、清 PID）
```

取代「登入自動常駐」後，架構反而更單純：不需要 systemd 單元、不需要處理 linger 與開機順序。要自己做的是 PID 檔、埠佔用偵測、重複啟動防護、就緒等待與優雅關閉。

## 6.3 網頁層

| 技術決策 | 選擇 | 理由 |
| --- | --- | --- |
| HTTP 伺服器 | 標準庫 `ThreadingHTTPServer` | **零新增依賴**，維持「一次安裝」的極簡性 |
| 即時推播 | Server-Sent Events（SSE） | 單向推播足夠、比 WebSocket 簡單、標準庫可實作 |
| 前端 | 原生 HTML / CSS / JS | 不引入 Node 建置工具鏈；離線可用 |
| K 線圖 | 瀏覽器 `<canvas>` | 從 JSON 繪製，**不需要 matplotlib**，`ediaad/` 的依賴維持乾淨 |
| 綁定位址 | `127.0.0.1` only | 已確認使用者就在同一台機器上操作 → 不需認證、不需 HTTPS、不需 CSRF 防護 |

網頁的每個操作都對應一個既有的核心函式，網頁層只做參數解析、錯誤轉譯與呈現，**不重實作任何邏輯**。

## 6.4 授權子系統

### 租約格式

```json
{
  "key_id": "EDIAAD-2026-0001",
  "machine": "<machine-id 的 sha256 前 16 碼>",
  "issued_at": "2026-09-24T12:00:00Z",
  "expires_at": "2026-10-24T12:00:00Z",
  "features": ["start", "update"],
  "catalog_version": "2026-10-01",
  "sig": "<Ed25519 簽章>"
}
```

### 三個觸發點與各自的驗證方式

| 觸發 | 驗證方式 | 需要連線 |
| --- | --- | --- |
| 首次啟用 | 線上：密鑰 + 機器指紋 → 換回租約 | 要 |
| **每次啟動** | **離線**：驗簽章 + 指紋相符 + 未過期 + 時鐘合理 | **不要** |
| 每次開啟／每 24 小時 | 線上：續租 + 更新檢查 + 目錄更新 | 要 |

**這個設計的關鍵**：更新檢查本來就要連線，所以續租是「順便」的，不增加任何額外連線；而啟動完全不碰網路，因此「完全本地運行」成立。

### 撤銷與導流

- **撤銷立即生效**：下次驗證（開啟或 24 小時）失敗即停止服務
- **過期後必須重新申請新金鑰**（不自動續期）→ 導流到網站
- **後端必須拒絕已過期租約的 `renew`**（回 403），否則軟體恢復連線時直接續租，導流就被繞過
- **重新申請頁對已撤銷的機器指紋自動拒絕**，否則被撤銷者只要再申請就復活

### 時鐘篡改防護

1. **簽章內的 `issued_at`**：系統時間 < `issued_at` − 容忍值 → 強制線上驗證（綁在簽章裡，是真正的防線）
2. **本地 `high_water`**：系統時間 < 歷史最高時間 − 容忍值 → 同樣強制線上驗證（可被刪檔繞過，只是提高門檻）

### Ed25519 驗章：純 Python

| 評估項 | 結果 |
| --- | --- |
| 需要的標準庫能力 | `hashlib.sha512`、任意精度整數（皆可用） |
| 效能 | 2000 次模逆運算 0.206 秒 → 單次驗章充裕 |
| 測試依據 | **RFC 8032 官方測試向量**（公開、確定性） |
| 分工 | **Worker 用 WebCrypto 簽**（私鑰留伺服器），**客戶端用純 Python 驗** |
| 後備方案 | `cryptography` 已實測有現成 wheel（4.7MB、免編譯）可隨時替換 |

### 這個架構的誠實邊界

| 想防的行為 | 有效嗎 |
| --- | --- |
| 改租約到期日 | ✅ 簽章保護 |
| 偽造租約 | ✅ 沒有私鑰簽不出 |
| 搬到別台用 | ✅ 指紋在簽章內 |
| 改系統時間 | ⚠️ 提高門檻 |
| **完全不回報使用狀況** | ❌ 改一行程式碼即可繞過 |
| **撤銷後繼續用舊版** | ❌ 同上 |
| 取得新版 | ✅ **伺服器不發就拿不到** |

**客戶端授權只能防君子**，這是架構層級的事實而非實作缺陷：驗章程式在使用者機器上，而專案是純 Python，`.py` 檔可直接修改。因此**控制力應該放在「更新」**——那一關是伺服器說了算。

**為什麼不做「規律參數加密發放」**：原則是「任何客戶端能解密的東西，客戶端就一定能取出」。對稱加密（金鑰內嵌）、非對稱加密（私鑰必然在磁碟）、白箱混淆都只是提高時間成本。唯一有效的是「伺服器端運算」，但那會摧毀「完全本地運行」與離線可用性。

## 6.5 更新子系統

`GET /v1/latest` 回傳靜態 manifest：

```json
{
  "schema": 1,
  "version": "0.4.0",
  "released_at": "2026-10-01T00:00:00Z",
  "min_supported": "0.3.0",
  "notes": "新增台股來源與桌面通知",
  "catalog_version": "2026-10-01",
  "catalog_url": "https://<網域>/ediaad/catalog.json",
  "url": "https://<網域>/ediaad/ediaad-0.4.0.tar.gz",
  "sha256": "...",
  "size": 1048576
}
```

**v0.3 只顯示，不下載不安裝**，但格式先凍結。分成兩個端點的理由：manifest 是靜態可快取的，`renew` 是動態的；Worker 掛掉時 manifest 仍可讀。

**六條架構約束**（因為軟體必須「完全本地運行」）：

1. 逾時上限 5 秒
2. **絕不阻塞啟動、絕不阻塞網頁回應、絕不阻塞監控輪詢**（獨立執行緒）
3. 失敗一律靜默，只記狀態
4. 網頁載入時立即回傳快取結果，實際檢查在背景跑
5. 去抖動 5 分鐘
6. 可完全關閉

## 6.6 通知子系統

| 管道 | 實作 | 適用時機 |
| --- | --- | --- |
| 網頁內提示 | 頁面上的提示條／卡片 | 網頁開著 |
| 瀏覽器原生通知 | `Notification` API。`http://127.0.0.1` 屬**安全來源**，可用；顯示為**作業系統原生通知**，三平台同一套程式碼 | 網頁開著、可縮到背景 |
| 服務端桌面通知 | Linux：`notify-send`；macOS：`osascript -e 'display notification'`；Windows：PowerShell + WinRT toast | **網頁關閉但服務仍在執行** |

**設計**：沿用 v0.2 已預留的可注入 `emit`，新增 `notify/` 模組作為另一種 emitter 實作。**引擎 0 改動。**

⚠️ macOS 與 Windows 的路徑**未在實機驗證**（開發機為 Linux）。

## 6.7 Cloudflare 後端

| 元件 | 內容 |
| --- | --- |
| Worker API | `POST /v1/activate`、`POST /v1/renew` |
| 靜態 | `GET /v1/latest`、`/catalog.json` |
| D1 資料表 | `keys`（密鑰、狀態、features、到期）、`devices`（指紋、平台、版本）、`renewals`（每次驗證一筆，含 `trigger`）、`blacklist`（已撤銷指紋）、`audit`（後台操作） |
| 公開申請頁 | 過期者自助重新申請（黑名單除外） |
| 後台 | 批次產生密鑰、清單與搜尋、撤銷／恢復／延長、統計、黑名單、稽核 |
| Secret | Ed25519 簽章私鑰 |

**`renewals` 表的設計重點**：每次驗證都寫一筆，並記錄 `trigger`（`start` / `timer` / `manual`）。這讓「使用者開過幾次軟體」= `count(trigger='start')`，與 24 小時定時的那筆區分開。因為租約是 30 天滾動，**任何在用的人最多 30 天一定回報一次**，所以「過去 30 天有 renew 的 distinct key_id」幾乎等於真實活躍使用者數——不需要「同時在線」這種得不到的指標。

---

# 7. 市場資料模組架構

## 7.1 Source 介面

v0.2 的 `fetch_ohlcv(symbol, interval, limit, cache_dir, client, max_age)` 是 Binance 專屬簽名。v0.3 抽象成通用介面：

```python
class Source(Protocol):
    id: str                                      # "binance" / "twse" / "twelvedata" / "csv"
    display_name: str                            # 顯示給使用者的名稱
    supported_intervals: tuple[str, ...]         # 每個來源不同！
    needs_api_key: bool
    def search(self, keyword: str, limit: int) -> list[Instrument]: ...
    def fetch(self, symbol: str, interval: str, limit: int) -> pd.DataFrame: ...
```

**關鍵影響**：目前的全域常數 `ALLOWED_INTERVALS` 必須廢除，改為**依來源查詢 `supported_intervals`**。這會連帶改動設定驗證（`load_config` 現在用它驗證設定檔）與監控迴圈的 fetch 分派。

## 7.2 目錄清單（可透過更新攜帶）

```
ediaad/markets/
  base.py       Source 介面、registry、Catalog schema
  catalog.py    版本化來源／商品清單
  crypto.py     【模組 1】加密貨幣：Binance
  twse.py       【模組 2】台股：TWSE 官方
  us.py         【模組 3】美股：Twelve Data
  custom.py     自訂：使用者上傳 CSV
  calendar.py   交易日曆
  adjust.py     除權息處理
```

`catalog.py` 內含一份**帶版本的來源與商品清單**（例如 `catalog_version: 2026-10-01`）。更新 manifest 可攜帶 `catalog_url`，有新版時下載取代本地快取。

**這個設計的效益**：「新增一個市場來源」或「修正某個商品代號」不需要改程式、不需要重新安裝，只要發一份新 catalog——而取得新 catalog 需要通過授權驗證，形成自然的更新誘因。

## 7.3 各來源設計

| 市場 | 來源 | 實測結果 | 金鑰 | 特殊處理 |
| --- | --- | --- | --- | --- |
| 加密貨幣 | Binance | ✅ `200`，CORS `*`，`exchangeInfo` 有 3,670 個交易對 | 不需要 | 無 |
| 台股 | TWSE 官方 | ✅ `STOCK_DAY_ALL` `200`，1,380 檔含中文名；⚠️ 日期為**民國年**需轉換 | 不需要 | 除權息、交易日曆、**只有日線** |
| 美股 | Twelve Data | ✅ 端點可達（無金鑰回 `401` 並附申請說明） | **使用者自行申請並填入** | 需處理金鑰儲存 |
| 自訂 | 使用者上傳 CSV | ✅ v0.2 已有 | 不需要 | 無 |

**放棄 Yahoo Finance**：實測 `429 Too Many Requests`（含瀏覽器 UA），且為非官方端點、無 CORS、使用條款不允許再散佈。

**金鑰型來源的取捨**：金鑰內嵌客戶端可被取出、經作者代理會破壞「完全本地運行」。選擇「使用者自行申請」最乾淨——額度歸使用者，作者不承擔條款風險。金鑰必須存在獨立檔案（如 `~/.local/share/ediaad/keys.json`），**不可寫進 `watchlist.json`**（該檔會在網頁顯示、也可能被匯出）。

## 7.4 股票市場的特殊處理（真正有技術含量的部分）

### 除權息（必須處理，否則會產生假訊號）

除權息當天價格會直接跳空（例如配股 10% → 價格掉 10%）。未還原的價格序列會讓偵測器把**除權息跳空誤判為「向下跌破」**。

**實測**：TWSE 的除權息端點 `TWT49U` **四種參數組合全部失敗**（西元／民國、單月／區間），都回誤導性的「查詢結束日期小於查詢開始日期」。**目前沒有確認可用的官方除權息資料來源。**

三個層次的處理方案：

| 方案 | 做法 | 評價 |
| --- | --- | --- |
| **A. 事件排除**（建議） | 只需除權息**日期**（不需權值／息值），在那些日期附近的 K 線標記為不可用於規律判定 | **解決主要風險、實作最簡單**。日期來源待確認 |
| B. 完整還原股價 | 取得權值／息值回推還原價 | 正確但複雜（多次除權息），來源未確認 |
| C. 跳空偵測（保底） | 單日跳空超過門檻且與大盤方向無關 → 標記疑似除權息並排除 | 零依賴、啟發式，能擋大部分假訊號 |

### 交易日曆

**「盤整 20 根」在加密貨幣是 20 小時，在台股日線是 20 個交易日 ≈ 4 週——語意完全不同。** 且股票有週末、國定假日、停牌，v0.2 的核心假設「連續等距的 K 線」在股票市場不成立。因此需要 `calendar.py`，且**規律參數應按市場給不同預設值**。

### 為什麼市場資料必須由本機 Python 抓，不能由瀏覽器 JS 抓

**因為關掉分頁就沒有監控。** 產品的核心是持續盯盤與主動提醒，瀏覽器一關就停。此外多數來源沒有 CORS。

（Binance 與 TWSE 剛好都給 `Access-Control-Allow-Origin: *`，因此可以作為「互動式預覽」的加分項，但**不能當作主路徑**。）

---

# 8. 設計取捨與已知限制

## 8.1 主要設計取捨

| 取捨 | 選擇 | 理由 |
| --- | --- | --- |
| 相似度 vs 規則 | **兩條路線並存且不互相依賴** | 「像不像」與「符不符合規則」是不同問題；規則可解釋、相似度可探索 |
| 距離度量 | 加權 L1 + 穩健正規化 | 對離群值不敏感、可解釋；權重可調 |
| 重疊抑制 | 貪婪 | 可預期、O(M·K)；代價是可能非全域最佳 |
| 區間選擇 | 最長可行區間 | 可預期、可用二分搜尋加速；代價是邊界可能外擴一格 |
| 覆蓋率 vs 誤報 | **不誤報優先** | 誤報直接消耗使用者信任；代價是預設偏保守 |
| Web 技術 | 標準庫 | 維持「一次安裝、零新增依賴」的核心優勢 |
| 授權 | 客戶端驗簽章（L2） | 防住「改檔案」；接受「改程式碼」可繞過 |
| 更新 | 伺服器控制 | 唯一真正有效的控制點 |

## 8.2 已知限制（現況）

1. 提醒去重狀態只在記憶體，跨程序重複執行 `--once` 會重複提醒
2. 事件檔與快取檔不會自動清理
3. 預設規格偏保守：4,000 根真實 K 線（四個商品／週期各 1,000 根）只命中 1 筆，且命中的盤整長度正好是下限 20 根
4. v0.2 假設輸入為連續等距的 K 線（股票市場不成立）
5. 無圖形介面、無授權機制、只有單一資料來源
6. 統計未處理片段之間的相關性（相似片段可能時間相近、彼此相關）
7. 單一範例學習可能過擬合（容差圍繞那一段範例設計）

## 8.3 實作期間修過的三個缺陷（新手容易踩的坑）

| ID | 症狀 | 根因 | 教訓 |
| --- | --- | --- | --- |
| F-001 | 快取往返後 dtype 改變，同一份資料兩次讀取不相等 | 交易所路徑產生 `datetime64[ms]`、CSV 路徑產生 `[us]` | **多個來源路徑必須產出完全相同的資料結構**，否則「快取透明」不成立 |
| F-002 | 監控路徑第一次執行就 AttributeError | `forward_stats` 讀 `end_index`，但 `PatternEvent` 用 `recovery_index` | 兩個模組各自演化後，**在整合點才暴露契約不一致**；這正是需要端到端測試的原因 |
| F-003 | 資料不足的商品被回報為「已處理且無命中」 | `detect` 對過短序列正確地回傳空清單，但監控層無法區分「無法評估」與「評估後沒中」 | **「沒有結果」與「無法得到結果」必須在架構上區分** |

三個都由「先寫測試」在實作階段抓到，並各補上能捕捉它們的回歸測試。

---

# 附錄 A：實測環境數據

| 檢查 | 結果 |
| --- | --- |
| Python / Node | 3.12.3 / v24.21.0 |
| 無 sudo、無預裝 pip、無 curl | 是 → 安裝只能走 `venv --without-pip` + `get-pip.py` |
| 桌面環境 | `DISPLAY=:0`、Wayland、`firefox` / `google-chrome` / `xdg-open` |
| 預設瀏覽器 | `com.google.Chrome.desktop` |
| `~/.local/share/applications` | 存在且可寫 |
| `~/桌面` | 存在且可寫 |
| `/etc/machine-id` | 可讀（32 字元）→ 機器指紋可行 |
| `notify-send` | 存在；`DBUS_SESSION_BUS_ADDRESS` 已設定 |
| 標準庫 Web 能力 | `http.server`、`socketserver`、`ssl`、`sqlite3`、`asyncio`、`wsgiref` 全可用 |
| 第三方 Web 框架 | flask / fastapi / uvicorn **全未安裝** |
| HTTPS 到 Cloudflare | `200 OK`、`CF-Ray: TPE`、公開 CA 憑證、標準庫可驗證 |
| 逾時可控性 | 對不可達位址 3.0 秒後 `URLError` |
| `hashlib` | sha256 / sha512 / blake2b 皆可用 |
| `cryptography` wheel | 有現成 wheel（4.7MB、`cp311-abi3` manylinux、免編譯） |
| Binance `klines` / `exchangeInfo` | `200`、CORS `*`、3,670 個交易對 |
| Yahoo `v8/chart` / `v1/search` | **`429`**、無 CORS |
| Stooq CSV | `200` 但回傳 JS 機器人驗證頁 |
| TWSE `STOCK_DAY` / `STOCK_DAY_ALL` | `200`、CORS `*`、1,380 檔含中文名 |
| TWSE `TWT49U`（除權息） | ❌ 四種參數組合皆失敗 |
| Twelve Data `time_series`（無金鑰） | `401` 並附申請說明 → 端點可達 |

# 附錄 B：資料來源結論

| 市場 | 第一版來源 | 狀態 |
| --- | --- | --- |
| 加密貨幣 | Binance | ✅ 確認可用 |
| 台股 | TWSE 官方 | ✅ 行情確認可用；⚠️ 除權息來源待確認 |
| 美股 | Twelve Data（使用者自填金鑰） | ✅ 端點確認可達 |
| 自訂 | 使用者上傳 CSV | ✅ 已有功能 |
| ~~Yahoo Finance~~ | — | ❌ 放棄（429 + 非官方 + 條款不允許） |

# 附錄 C：程式碼規模

| 分類 | 行數 |
| --- | --- |
| 純計算（`errors`、`features`、`similarity`、`scan`、`outlook`、`patterns`、`sources/base`） | 904 |
| I/O 與協調（`data`、`sources/binance`、`monitor`、`cli`、`__main__`） | 791 |
| **產品程式合計** | **1,695** |
| 測試（14 個檔案 / 185 個案例） | 2,268 |
| 工作流程文件（SPEC、BRIEF、TDD 與 Review 證據、DELIVERY） | 3,557 |

**執行期依賴**：僅 `numpy 2.5.3`、`pandas 3.0.6`（開發再加 `pytest 9.1.1`）。
