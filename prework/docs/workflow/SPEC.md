# 專案規格

- Spec ID：SPEC-001
- 版本：0.4
- 狀態：ready
- 需求來源：BRIEF.md
- 確認／授權依據：見 PROJECT.md；使用者已於 2026-09-24 逐項確認「1-正確（範圍與 66 項 AC）、2-同意（測試公開邊界）、3-開始實作」，並指定所有實作與程式碼置於 `ocaievo/`

## 1. 問題與成果

使用者心中有一個熟悉的價格型態（第一號為「區間盤整 → 假跌破 → 快速回到區間均值」），但目前只能靠肉眼翻歷史線圖，無法同時盯多個商品，主觀判斷不可重現，圖表縮放不同看起來就不同，也不確定型態出現後的歷史表現。

本 Spec 交付一套**完全在本機執行的市場規律偵測與監控提醒工具**，外加一套只做版本記錄與授權的 Cloudflare 後端。完成後可觀察到：

- 雙擊桌面圖示 10 秒內看到網頁；關閉網頁後服務仍在背景盯盤，命中時收到桌面通知。
- 在網頁上以中文名或代號搜尋商品、調整白話參數並即時看到「命中幾次」。
- 同一輸入與參數永遠得到相同結果；價格乘常數或平移後命中位置完全不變。
- 歷史回看列出相似片段排行與其後續 H 根統計，並標示樣本數。
- 授權有效期內完全離線可用；逾期未連線則停止服務並提示重新申請。

## 2. 範圍

- In scope：
  - 核心引擎：序列契約與載入、10 維尺度不變特徵、穩健正規化與加權相似度、滑動掃描與重疊抑制、後續走勢統計、`PatternSpec`／`PatternEvent`、ATR、規律偵測、範例學習、監控設定／輪詢／去重／錯誤隔離、提醒輸出、命令列（`match`、`monitor`）。
  - 資料來源：`Source` 介面與 registry、Binance、TWSE（日線、商品搜尋、除權息還原、交易日曆）、Twelve Data、自訂 CSV、版本化 catalog。
  - 本機服務與介面：SQLite 落地、設定原子寫入、HTTP 服務（`127.0.0.1:8787`）、SSE、事件歷史、K 線圖三相位、參數面板即時預覽、範例學習頁、歷史回看頁、監控清單管理、系統狀態與版本頁、授權頁。
  - 啟動與通知：桌面圖示一鍵啟動、PID／埠防護、優雅關閉、網頁／瀏覽器原生／服務端桌面三管道通知。
  - 授權與更新：簽章租約、純 Python Ed25519 驗章、機器指紋、啟用／續期／到期停止／撤銷、功能分級、時鐘篡改防護、更新檢查六約束。
  - Cloudflare 後端：`/v1/activate`、`/v1/renew`、`/v1/latest`、`/catalog.json`、D1 資料表、後台操作、公開重新申請頁。
- Out of scope（報告第 3.3 節「明確不做」＋本專案限制）：
  - 圖片解析、模型訓練、趨勢方向標籤與價格預測、自動下單、對外開放本機服務、自動下載安裝更新、Yahoo Finance、規律參數加密發放。
  - 對外動作：`git push`、開 Issue、合併、部署 Cloudflare Worker、發布版本。
  - 真實 Cloudflare 帳號／D1／網域的連線驗證；macOS 與 Windows 的實機通知驗證。
  - v0.2 既有程式碼的沿用（本專案從零重建，只沿用報告的設計）。

## 3. 角色與主要流程

角色只有一位：**本機使用者**（同時是操作者與資料擁有者）。沒有多租戶、沒有遠端使用者、沒有權限區分；本機服務不對外開放，因此不需認證、HTTPS 或 CSRF 防護。作者（後端營運者）是第二個角色，只在 Cloudflare 後台產生密鑰、撤銷與查看統計，不在本機程式中。

主要流程：

1. **安裝**：`python3 scripts/bootstrap_env.py` → 建立 `.venv`、取得 pip、安裝 numpy／pandas／pytest。
2. **首次啟用**：輸入密鑰 → 取機器指紋 → 線上 `POST /v1/activate` → 取得簽章租約 → 存 `$EDIAAD_HOME/lease.json`。
3. **啟動**：桌面圖示或 `python -m ediaad serve` → 離線驗章 → 啟動監控迴圈與網頁 → 開瀏覽器；已在執行時只開瀏覽器。
4. **設定監控**：網頁搜尋商品（下拉，不需打代號）→ 選週期 → 調整輪詢間隔與規律參數 → 即時預覽命中次數 → 儲存（原子寫入）。
5. **盯盤與提醒**：輪詢各商品 → 長度檢查 → 偵測 → 歷史統計 → 去重 → 提醒（網頁 SSE ＋ 桌面通知）→ 寫入 SQLite。
6. **歷史回看**：選商品與範圍 → 相似片段排行 → 後續統計 → K 線圖標出三相位。
7. **範例學習**：貼上／上傳 CSV → 推估規格 → 顯示參數與命中預覽。
8. **續期與更新**：每次開啟與每 24 小時 → 續租 ＋ 更新檢查 ＋ catalog 更新（皆不阻塞主要流程）。
9. **關閉**：網頁按鈕或 `./stop.sh` → 優雅結束、清 PID、釋放埠。

重要例外：資料不足的商品顯示「無法評估」而非「無命中」；單一商品來源失敗只記 warning；設定檔損毀不覆蓋原檔；系統時間被往回調則強制線上驗證；除權息跳空不產生假跌破訊號。

## 4. 驗收條件

| AC ID | Given 前提 | When 操作 | Then 可觀察結果 | 優先級 | status |
| --- | --- | --- | --- | --- | --- |
| AC-001 | 乾淨環境，無 pip、無法使用 sudo | 執行 `python3 scripts/bootstrap_env.py` | exit code 0；`.venv` 內 numpy／pandas／pytest 可 import；重跑第二次仍 exit 0 且不重複破壞環境 | 高 | active |
| AC-002 | 一份合法 OHLC CSV（欄位 time,open,high,low,close,volume） | 呼叫 `load_csv` | 回傳 Series：欄位與順序固定、`time` 為 UTC `datetime64[ns]` 且升冪、時間無重複 | 高 | active |
| AC-003 | 五種壞輸入：缺欄位、空檔案、非數值、時間無法解析、重複時間戳 | 呼叫 `load_csv` | 各自丟出 `DataFormatError`，訊息指出哪個欄位或哪一列出錯 | 高 | active |
| AC-004 | 同一份資料的 CSV 與資料列兩種形式 | 分別呼叫 `load_csv` 與 `from_rows` | 兩者 dtype（含 `time` 為 ns）與值完全相同；寫入快取再讀回仍完全相同（F-001 回歸） | 高 | active |
| AC-005 | 一段已知的合成 K 線視窗與手算的 10 個特徵值 | 呼叫 `features.extract` | 10 維向量逐維與手算值相符（容差 1e-9），順序等於 `FEATURE_NAMES` | 高 | active |
| AC-006 | 同一視窗 | 對整段價格乘 0.01／0.5／1／1000（4 種），以及加常數做 3 種平移後重抽特徵 | 乘常數後 10 維特徵全部不變（容差 1e-9）；平移後第 3、4、5、6、8、9、10 維不變。第 1、2、7 維（`total_return`、`return_std`、`max_drawdown`）依定義使用價格比值，本來就不具平移不變性（報告第 5.1 節只宣稱「乘上正數 k 後全部不變」），故不列入平移斷言；平移不變性在規律偵測路線上由 AC-019 強制要求。全平坦（high==low）與零量能等退化視窗回傳有限值，無 NaN／Inf | 高 | active |
| AC-007 | 長度 200、視窗 20、步長 1 的序列 | 呼叫 `extract_matrix` | 形狀為 (181, 10)，且每一列與逐窗 `extract` 相同；記憶體佔用不隨視窗長度增加 | 中 | active |
| AC-008 | 候選池中含與範例完全相同的視窗 | 呼叫 `similarity.rank` | 完全相同者排名第 1、分數 1.0；所有分數落在 (0,1]；同分時以索引升冪 | 高 | active |
| AC-009 | 三種壞權重：長度不符、含負值、總和為 0 | 呼叫 `similarity.rank` | 各自丟出 `ConfigError`；權重整體乘 2 後排序完全不變 | 中 | active |
| AC-010 | 序列長度 100、視窗 20，其中植入兩段重疊 60% 與兩段重疊恰好 50% 的候選 | 呼叫 `scan_similar` | 每筆結果寬度等於 20、筆數不超過 top；重疊 60% 者只留高分；恰好 50% 者兩筆都保留 | 高 | active |
| AC-011 | 四種壞參數：範例長度不等於 W、序列短於 W、top 或 step 不合法、序列缺 time 欄位 | 呼叫 `scan_similar` | 各自丟出 `ConfigError`，訊息指出不合法處 | 中 | active |
| AC-012 | 片段清單與已知的後續報酬 | 呼叫 `outlook.forward_stats` | samples、up_probability、mean／median／std（母體 ddof=0）與手算相符；`end+H` 超出序列者被排除；報酬恰為 0 不算上漲；無樣本時 samples=0 且其餘欄位為 None | 高 | active |
| AC-013 | 分別為 `ScanMatch`（`end_index`）與 `PatternEvent`（`recovery_index`） | 以 `end_attr` 指名結束欄位呼叫 `forward_stats` | 兩條路線共用同一函式且都得到正確結果；未指定時預設用 `end_index`（F-002 回歸） | 高 | active |
| AC-014 | 一組欄位與交叉條件 | 建構 `PatternSpec` | 合法規格可建立且不可變（frozen）；不合法（如 `range_bars_min > range_bars_max`、負數、未知 `recovery_target`）在 `__post_init__` 即丟出 `ConfigError`；所有欄位皆為相對單位，無價格欄位 | 高 | active |
| AC-015 | 一組合法的 `PatternSpec` | `to_json` 後 `from_json` 還原 | round-trip 完全相等且輸出鍵序穩定（`sort_keys=True`）；`from_json` 對缺欄位、多欄位、型別不符各自丟出 `ConfigError` | 中 | active |
| AC-016 | 已知 high／low／close 序列與週期 14 | 呼叫 `patterns.atr` | 前 13 個為 NaN、之後與手算 rolling 平均相符；把植入點之後的資料乘 10，`ATR[range_end]` 差異小於 1e-12（不引用未來） | 高 | active |
| AC-017 | 依已知參數植入盤整／跌破／回歸三相位的合成序列 | 呼叫 `patterns.detect` | 回傳事件的四個相位索引、`band`、`breakdown_depth`、`recovery_bars`、`confidence` 皆符合第 5.5 節定義；`confidence` 落在 [0,1] | 高 | active |
| AC-018 | 四種反例：跌破深度不足、深度超過上限、回歸前出現更低低點、回歸逾時 | 呼叫 `patterns.detect` | 四種情境皆回傳空清單（零命中） | 高 | active |
| AC-019 | 同一段含命中的序列 | 整段乘 0.01／0.5／1000 與加常數平移後重跑 `detect` | 命中事件的四個索引完全相同（尺度不變） | 高 | active |
| AC-020 | 同一結構可被多個長度命中 | 呼叫 `patterns.detect` | 同一段結構只保留最長的一次；結果依盤整相位長度由長到短排序 | 中 | active |
| AC-021 | 一段由已知參數合成的範例（至少 12 根） | 呼叫 `patterns.learn` | 推估出的 `PatternSpec` 落在容差內，且用該規格 `detect` 能命中自己的範例；範例無法推估時丟出 `ConfigError` 且不回傳隨意參數；同一範例重跑結果完全相同 | 高 | active |
| AC-022 | 一份合法監控設定與五種壞設定（缺鍵、未知鍵、型別錯、`instruments` 為空、週期不合法） | 呼叫 `monitor.load_config` | 合法者回傳 `Watchlist`；壞設定各自丟出 `ConfigError` 並指出出錯的鍵或索引位置；`pattern_spec` 提供時其 `pattern_id` 必須與頂層一致 | 高 | active |
| AC-023 | 注入的假 fetch 與可控時鐘，同一事件連續三輪 | 連續呼叫 `run_once` 三次 | 提醒次數為 1、0、1；去重鍵為（商品, 週期, 規律 ID, 事件開始時間） | 高 | active |
| AC-024 | 注入的 fetch 對某商品丟出 `SourceError`，另一商品正常 | 呼叫 `run_once` | 失敗商品只記 warning，正常商品仍發出提醒；`RunResult` 的 processed／alerted／skipped／warnings 正確；非領域的程式錯誤向上拋出而非被吞掉 | 高 | active |
| AC-025 | 序列長度小於 `range_bars_min + 1` | 呼叫 `run_once` | 該商品計入 skipped 並附 warning「資料不足」，不與「評估後無命中」混為一談（F-003 回歸） | 高 | active |
| AC-026 | 一次命中事件 | 呼叫 `format_alert` 與 `append_event` | 主控台為單行摘要且欄位順序固定；JSONL 以附加寫入、不改寫既有行，含九個欄位；重複附加不破壞既有行 | 高 | active |
| AC-027 | 一份資料 CSV 與範例 CSV | 執行 `python -m ediaad match --data ... --sample ... --top ... --horizon ... --out report.json` | exit code 0，`report.json` 頂層鍵恰為 sample／params／data_source／matches／outlook；缺檔或參數錯 exit 2；輸出檔不可寫 exit 1 | 高 | active |
| AC-028 | 一份監控設定 | 執行 `python -m ediaad monitor --config ... --once` | 單次執行 exit 0 並輸出摘要；設定錯誤 exit 2；來源失敗 exit 1；常駐模式收到中斷訊號時優雅結束 | 高 | active |
| AC-029 | 10,000 根序列、視窗 60、top 20 | 執行 `match` 並計時 | 在同一台開發機 60 秒內完成（報告基準 3.50 秒），且結果與小資料集的行為一致 | 中 | active |
| AC-030 | 四個來源實作（binance／twse／twelvedata／csv） | 讀取 registry 並查詢各來源的 `supported_intervals` | 每個來源都有 `id`、`display_name`、`supported_intervals`、`needs_api_key`、`search`、`fetch`；設定驗證依來源查詢週期，不存在全域 `ALLOWED_INTERVALS` 作為唯一依據；對來源不支援的週期提出可讀錯誤 | 高 | active |
| AC-031 | 注入的假 HTTP 客戶端，四種快取情境（有效、過期、失敗有舊快取、失敗無快取） | 呼叫 Binance 來源的 `fetch` | 快取有效時請求次數為 0；過期時重取並覆寫；失敗且有舊快取時回傳 `cache-stale`；失敗且無快取丟出 `SourceError`；只用公開端點 | 高 | active |
| AC-032 | TWSE `STOCK_DAY` 的實際回應（民國年、千分位數字） | 呼叫 TWSE 來源的 `fetch` | 回傳符合 Series 契約的日線；民國年轉為西元、千分位字串轉為 float、成交股數映射為 volume；不支援的週期提出可讀錯誤 | 高 | active |
| AC-033 | TWSE `STOCK_DAY_ALL` 與上市公司基本資料回應 | 呼叫 TWSE 來源的 `search` | 可用代號或中文名關鍵字搜尋，回傳含代號與名稱的 `Instrument` 清單並限制筆數 | 中 | active |
| AC-034 | 含除權息事件的期間（實測 2024-07 共 449 筆） | 取得除權息資料並還原股價後呼叫 `detect` | 還原序列在除權息日不產生「向下跌破」命中；未還原序列會產生假命中（作為對照）；事件欄位含除權息前收盤價、除權息參考價、權值+息值 | 高 | active |
| AC-035 | TWSE `holidaySchedule` 回應 | 查詢交易日曆並對台股序列標記交易日 | 非交易日不會被當成連續 K 線；台股與加密貨幣使用不同的規律預設參數（市場別預設），且預設值可被設定覆寫 | 中 | active |
| AC-036 | 無金鑰與有金鑰兩種情況 | 呼叫 Twelve Data 來源的 `fetch` | 無金鑰時丟出可讀錯誤（含申請說明）；有金鑰時回傳 Series；金鑰只存在 `$EDIAAD_HOME/keys.json`，不出現在 `watchlist.json`、網頁輸出或日誌中 | 高 | active |
| AC-037 | 使用者上傳的 CSV 檔案 | 以自訂來源取得序列 | 沿用 `load_csv` 的完全相同契約與錯誤行為 | 中 | active |
| AC-038 | 本地 catalog 與較新版本的 catalog | 比對版本並更新 | 版本較新時下載並原子取代本地快取；版本相同不重複下載；下載失敗保留原檔並記錄狀態 | 中 | active |
| AC-039 | 空 SQLite 資料庫與一次命中 | 寫入事件與提醒狀態後重啟程序再輪詢同一事件 | 重啟後同一事件不重複提醒（跨程序去重）；事件可依商品與時間查詢 | 高 | active |
| AC-040 | 一份合法設定與一份損毀設定 | 透過網頁修改並儲存設定 | 合法者以「暫存檔＋rename」原子寫入；損毀設定不會覆蓋原檔，回報錯誤並保留原內容 | 高 | active |
| AC-041 | 服務已啟動 | 呼叫各 HTTP 端點 | 只 bind `127.0.0.1:8787`；靜態頁與 API 可用；每個操作對應既有核心函式（不重複實作邏輯）；錯誤轉譯為可讀訊息而非 traceback | 高 | active |
| AC-042 | 網頁開著且 SSE 已連線 | 觸發一次命中，並測試斷線重連 | 瀏覽器在 1 秒內收到事件；重連後不重複顯示已去重事件；事件歷史可依商品與時間區間篩選 | 高 | active |
| AC-043 | 一段含命中的序列 | 開啟 K 線圖 | canvas 繪出 OHLC，並以不同標記標出盤整／跌破／回歸三個相位，位置與事件索引一致 | 中 | active |
| AC-044 | 已選商品與週期 | 在參數面板改動任一參數 | 不需存檔即在 1 秒內顯示該商品在此參數下的命中次數；改回原值得到原本次數（無隨機性） | 高 | active |
| AC-045 | 一段範例 CSV（貼上或上傳） | 按「學習」 | 顯示推估參數與命中預覽；無法推估時顯示明確原因 | 中 | active |
| AC-046 | 已選商品與時間範圍 | 使用歷史回看頁 | 以表單方式得到 `match` 的結果：相似片段排行與後續統計，並標示樣本數 | 中 | active |
| AC-047 | 已有監控清單 | 新增／移除商品、改週期、改輪詢間隔 | 下拉搜尋即可選到商品（不需輸入代號）；變更通過驗證後寫入設定並在下一輪生效 | 高 | active |
| AC-048 | 服務運行中 | 開啟系統狀態頁與版本頁 | 顯示最後輪詢時間、各商品資料來源（cache／binance／cache-stale 等）與錯誤訊息；版本頁顯示目前版本、最新版本、發佈日期與說明 | 中 | active |
| AC-049 | 服務未啟動／已啟動兩種情況 | 執行啟動器 | 未啟動時背景啟服務、等就緒（最多 10 秒）、開瀏覽器；已啟動時只開瀏覽器，不啟第二個程序；PID 檔與埠探測可防止重複啟動 | 高 | active |
| AC-050 | 服務運行中 | 按網頁「關閉服務」或執行 `./stop.sh` | 優雅結束、PID 檔被清除、埠 8787 釋放；再次啟動可成功 | 高 | active |
| AC-051 | 一次命中且網頁開著／關著兩種情況 | 觀察三個通知管道 | 網頁內提示、瀏覽器原生通知、服務端桌面通知（Linux 以 `notify-send` 實測）皆能觸發；macOS／Windows 路徑在交付報告標示為未實機驗證 | 中 | active |
| AC-052 | 一組有效密鑰與可連線的授權服務 | 輸入密鑰啟用 | 送出密鑰與機器指紋後取得簽章租約（30 天）並落地；租約欄位符合第 5 節格式 | 高 | active |
| AC-053 | 一張有效租約且無網路 | 啟動服務 | 離線完成驗章、指紋比對、到期與時鐘檢查後啟動；整個啟動流程不發出任何網路請求 | 高 | active |
| AC-054 | RFC 8032 官方測試向量 | 執行驗章 | 所有向量通過；實作為純 Python，`.venv` 不含 `cryptography` 依賴 | 高 | active |
| AC-055 | 可讀的 `/etc/machine-id` | 計算機器指紋 | 得到 sha256 前 16 碼的穩定字串；同一機器重算相同；租約指紋不符時驗證失敗 | 高 | active |
| AC-056 | 有效租約、過期租約、已撤銷密鑰三種情況 | 執行續期與驗證 | 續期成功後重算 30 天；逾期未連線超過 30 天則停止服務並顯示重新申請訊息；撤銷後下次驗證即停止；後端對過期租約的 renew 回 403 | 高 | active |
| AC-057 | 租約 `features` 為 `["start"]` 與 `["start","update"]` 兩種 | 開啟版本頁並嘗試更新檢查 | 缺少 `update` 時更新功能停用但服務仍可用；網頁可輸入新密鑰更換，成功後以新租約為準 | 中 | active |
| AC-058 | 系統時間被調到早於 `issued_at` 減容忍值，或早於本地 `high_water` 減容忍值 | 啟動驗證 | 兩種情況都強制進行線上驗證，不以本地時間延長授權 | 高 | active |
| AC-059 | 可連線與不可連線兩種環境 | 啟動服務並開啟網頁 | 更新檢查逾時上限 5 秒、不阻塞啟動／網頁回應／監控輪詢（獨立執行緒）、失敗靜默只記狀態、網頁先回快取結果、5 分鐘去抖動、可完全關閉；只顯示版本資訊不下載不安裝 | 高 | active |
| AC-060 | 合法密鑰、已撤銷密鑰、過期租約三種請求 | 呼叫 `POST /v1/activate` 與 `POST /v1/renew` | 合法者回傳以私鑰簽章的租約；每次 renew 寫入 `renewals` 並記錄 `trigger`（start／timer／manual）；撤銷者被拒絕；過期租約的 renew 回 403 | 高 | active |
| AC-061 | 靜態資源已部署 | 呼叫 `GET /v1/latest` 與 `/catalog.json` | 回傳凍結 schema 的 manifest（version、released_at、min_supported、notes、catalog_version、catalog_url、url、sha256、size）與 catalog；回應可快取且不依賴 Worker 是否可用 | 中 | active |
| AC-062 | 空的 D1 資料庫 | 執行後台操作 | 建立 `keys`／`devices`／`renewals`／`blacklist`／`audit` 五張表；可批次產生密鑰、查詢清單、撤銷／恢復／延長、統計與稽核；統計以 `count(trigger='start')` 區分啟動次數 | 中 | active |
| AC-063 | 過期者與黑名單指紋 | 使用公開重新申請頁 | 過期者可自助重新申請；黑名單指紋被自動拒絕 | 中 | active |
| AC-064 | 已安裝的專案 | 執行 `python -m ediaad serve` 與 `license status／activate／renew` | 子命令存在且行為與 exit code 語意一致（0 成功、1 執行期失敗、2 輸入或設定錯誤） | 中 | active |
| AC-065 | 所有 Task 完成 | 執行最終整合驗收 | 全套 pytest 與 `node --test` exit 0；每項 active AC 都有實作與驗證證據；DELIVERY 列出已完成、未驗證與已知限制 | 高 | active |
| AC-066 | 三種授權狀態：未啟用、有效期內、已過期或已撤銷 | 開啟授權頁 | 未啟用時顯示首次啟用表單（輸入密鑰）；有效期內顯示授權狀態與剩餘天數；已過期或已撤銷顯示重新申請連結與原因；提供更換密鑰的輸入入口；所有狀態以文字表達，不單靠顏色區分 | 中 | active |

## 5. 模組、資料與公開契約

### 模組責任與邊界

三條設計原則（報告第 4.1 節）是本 Spec 的架構約束：

1. **計算不碰 I/O**：`features`、`similarity`、`scan`、`outlook`、`patterns`、`markets/base` 不讀寫檔案、不連網、不輸出訊息。
2. **外部效果一律可注入**：`monitor.run_once` 的 `fetch`／`emit`／`warn`／`sleep`／`should_stop` 全為參數；時鐘、隨機與網路都不得隱含在核心邏輯中。
3. **錯誤分層**：`EdiaadError` 為基底，`DataFormatError`／`ConfigError` 對應 exit 2，`SourceError` 對應 exit 1；監控迴圈只攔截領域錯誤與來源畸形資料，程式錯誤向上拋出。

依賴方向永遠單向：`cli`／`app`／`web` → `monitor`／`store`／`config`／`license`／`update`／`notify` → `patterns`／`scan`／`similarity`／`outlook`／`features` → `errors`／`data`／`markets`。`outlook` 不匯入 `scan`，以 `Protocol` 描述「有 `end_index` 的物件」。

**路徑慣例**：下表與本 Spec 其他段落中的實作檔案路徑一律**相對 `ocaievo/`**（使用者指示：所有實作與程式碼放在子資料夾 `ocaievo/`）。例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`。工作文件路徑（`docs/workflow/…`）則相對專案根。

| 模組 | 責任 | 對外 API |
| --- | --- | --- |
| `ediaad/errors.py` | 共用例外階層 | `EdiaadError`、`DataFormatError`、`ConfigError`、`SourceError` |
| `ediaad/data.py` | 序列契約與 CSV／資料列載入 | `SERIES_COLUMNS`、`PRICE_COLUMNS`、`TIME_UNIT`、`load_csv`、`from_rows` |
| `ediaad/features.py` | 10 維尺度不變特徵 | `FEATURE_NAMES`、`extract`、`extract_matrix` |
| `ediaad/similarity.py` | 穩健正規化與加權排序 | `Match`、`DEFAULT_WEIGHTS`、`rank` |
| `ediaad/scan.py` | 滑動視窗掃描與重疊抑制 | `ScanMatch`、`scan_similar` |
| `ediaad/outlook.py` | 後續走勢統計 | `OutlookStats`、`forward_stats` |
| `ediaad/patterns.py` | 規律模型、ATR、偵測器、範例學習 | `PatternSpec`、`PatternEvent`、`NAMED_PATTERNS`、`RECOVERY_TARGETS`、`to_json`、`from_json`、`atr`、`detect`、`learn` |
| `ediaad/monitor.py` | 設定、輪詢、去重、錯誤隔離、提醒格式化 | `Instrument`、`Watchlist`、`AlertState`、`RunResult`、`load_config`、`run_once`、`run_forever`、`format_alert`、`append_event`、`event_times` |
| `ediaad/config.py` | 設定解析、驗證與原子寫入 | `load_settings`、`save_settings_atomic`、`DEFAULT_SETTINGS` |
| `ediaad/store.py` | SQLite：事件、提醒狀態、租約快取 | `Store`、`open_store`、`record_event`、`seen_keys`、`mark_alerted`、`query_events` |
| `ediaad/license.py` | 租約模型、Ed25519 驗章、機器指紋、時鐘防護 | `Lease`、`machine_fingerprint`、`verify_lease`、`activate`、`renew`、`ed25519_verify` |
| `ediaad/update.py` | 版本檢查與 catalog 更新 | `check_update`、`UpdateState`、`fetch_catalog` |
| `ediaad/app.py` | 協調：監控迴圈 ＋ Web ＋ 排程 | `Application`、`start`、`stop` |
| `ediaad/cli.py` | 命令列 | `build_parser`、`main` |
| `ediaad/markets/base.py` | `Source` 介面、registry、catalog schema | `Source`、`Instrument`、`register`、`get_source`、`all_sources` |
| `ediaad/markets/crypto.py`／`twse.py`／`us.py`／`custom.py` | 各市場來源實作 | 各來源的 `search`、`fetch` |
| `ediaad/markets/catalog.py` | 版本化來源與商品清單 | `Catalog`、`load_catalog`、`save_catalog`、`catalog_version` |
| `ediaad/markets/calendar.py` | 交易日曆 | `TradingCalendar`、`is_trading_day`、`load_twse_calendar` |
| `ediaad/markets/adjust.py` | 除權息還原 | `ExRightsEvent`、`fetch_ex_rights`、`adjust_series` |
| `ediaad/notify/` | 三管道通知 | `Notifier`、`WebNotifier`、`BrowserNotifier`、`DesktopNotifier` |
| `ediaad/web/` | HTTP ＋ SSE ＋ 靜態資源 | `create_server`、`routes`、`sse_hub` |
| `ediaad/launcher.py` | 一鍵啟動與 PID／埠防護 | `main`、`is_running`、`wait_ready` |
| `cloudflare/worker/src/` | 後端 API 純函式與 D1 轉接 | `handleActivate`、`handleRenew`、`signLease`、`verifyLicenseKey` |

### 資料契約

**Series**：pandas DataFrame，欄位固定且順序固定為 `time`（UTC `datetime64[ns]`，升冪、無重複）、`open`、`high`、`low`、`close`、`volume`（皆 float64）。

**PatternSpec**：`pattern_id`（str）、`range_bars_min`／`range_bars_max`（int）、`band_atr_multiple_max`（float）、`atr_period`（int）、`breakdown_bars_max`（int）、`breakdown_depth_band_min`／`breakdown_depth_band_max`（float）、`recovery_bars_max`（int）、`recovery_target`（str，目前只有 `range_mean`）。全部為相對單位，無價格欄位；frozen 且於建構時驗證。

內建 `range_fakeout_reversion` 預設值：`range_bars_min=20`、`range_bars_max=120`、`band_atr_multiple_max=3.0`、`atr_period=14`、`breakdown_bars_max=2`、`breakdown_depth_band_min=0.2`、`breakdown_depth_band_max=1.5`、`recovery_bars_max=5`、`recovery_target="range_mean"`。

**PatternEvent**：`pattern_id`、`range_start_index`、`range_end_index`、`breakdown_index`、`recovery_index`、`confidence`、`band`、`breakdown_depth`、`recovery_bars`。

**其他結構**：`Match`（index、score、feature_distance）、`ScanMatch`（start_index、end_index、score、time_start、time_end）、`OutlookStats`（samples、up_probability、mean_return、median_return、std_return）、`Instrument`（symbol、interval、source_id、display_name）、`Watchlist`（poll_interval_seconds、events_path、cache_dir、pattern_id、pattern_spec、horizon、instruments）、`RunResult`（processed、alerted、skipped、warnings）、`AlertState`（`seen` ＋ `should_alert`／`mark_alerted`）、`Catalog`（catalog_version、sources、instruments）、`Lease`（key_id、machine、issued_at、expires_at、features、catalog_version、sig）。

**租約格式**（簽章涵蓋除 `sig` 外的所有欄位）：

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

### 輸入／輸出、驗證與錯誤格式

- `load_csv` 驗證：解碼容忍 BOM → 欄位名正規化 → 必要欄位齊全 → 型別可轉換 → 時間可解析並轉 UTC `ns` → 無重複時間 → 依時間升冪排序。違反者 `DataFormatError`，訊息含欄位名或列號。
- `load_config`／`load_settings` 驗證：缺鍵、未知鍵、型別錯誤、`instruments` 為空、週期不合法 → `ConfigError`，訊息指出鍵名或索引位置。
- CLI exit code：0 成功、1 執行期失敗（來源失敗、輸出檔不可寫）、2 輸入或設定錯誤。
- HTTP：本機服務回傳 JSON；錯誤以 `{"error": {"code": ..., "message": ...}}` 形式回傳可讀訊息，不洩漏 traceback。

### 資料生命週期、權限與狀態轉移

- 產物位置（實作路徑相對 `ocaievo/`）：`.venv/`（安裝後長期）、`<cache_dir>/<symbol>_<interval>.csv`（由 `max_age` 控制）、`events_path`（預設 `.cache/events.jsonl`，永久累積不自動清理）、`$EDIAAD_HOME/`（`ediaad.db`、`lease.json`、`keys.json`、`settings.json`、`catalog.json`）。
- `keys.json` 權限 `0600`，且**絕不出現在** `watchlist.json`、網頁輸出或日誌中。
- Task 狀態機：draft → ready → in_progress → in_review → done，另有 blocked 與 cancelled；取消不重用 ID。
- 授權狀態：未啟用 → 已啟用（有效期內）→ 已過期（停止服務並導流重新申請）→ 已撤銷（下次驗證停止）。

### 外部依賴與失敗處理

| 依賴 | 用途 | 失敗處理 |
| --- | --- | --- |
| Binance 公開端點 | 加密貨幣 K 線與商品清單 | 快取回退（`cache-stale`）；無快取則 `SourceError` |
| TWSE 官方端點 | 台股日線、商品清單、除權息、交易日曆 | 同上；除權息失敗時保留未還原序列並在系統狀態標記 |
| Twelve Data | 美股日線 | 無金鑰或額度用盡時回可讀錯誤；不影響其他商品 |
| Cloudflare 授權服務 | 啟用與續期 | 續期失敗不影響有效期內使用；逾期停止服務 |
| Cloudflare 更新服務 | 版本與 catalog | 5 秒逾時、失敗靜默、用快取 |

### 相容性／遷移

全新專案，無既有程式與資料需遷移，因此**不重建報告第 4.3／6.1 節的 `ediaad/sources/` 舊介面**（`OHLCVClient`、`sources.binance.fetch_ohlcv`）：報告保留它是因為 v0.3 建構在既有 v0.2 程式碼上（報告 6.1「保留（0 改動）」），而本專案依 ADR-001 從零重建，沒有需要相容的呼叫端。Binance 只有一條實作路徑 `ediaad/markets/crypto.py`，`Source` 介面取代舊的專屬簽名；保留兩條路徑會重現 F-001 的風險（同一份資料經不同路徑產生不同結構）。`fetch_ohlcv` 的 `data_source` 回報（`cache`／`binance`／`cache-stale`）由該來源實作提供，契約不變。

資料檔層級的相容性仍保留：v0.2 的 `events.jsonl` 與 `watchlist.json` 格式可讀（`monitor` 子命令仍支援），SQLite 為新增的權威儲存；首次啟動時若存在舊 `events.jsonl` 則匯入一次並記錄。

## 6. 品質需求

- **效能**：`match` 於 10,000 根、視窗 60、top 20 在開發機 60 秒內完成；`detect` 於 1,000 根序列 2 秒內完成；網頁快取類操作回應 200 毫秒內；參數預覽與 SSE 推播 1 秒內；啟動就緒等待上限 10 秒。
- **安全**：服務只 bind `127.0.0.1`；不連接券商、不持有交易金鑰；`keys.json` 權限 `0600` 且不進日誌／網頁；租約以 Ed25519 簽章保護到期日與指紋；不引入對稱加密發放規律參數；所有外部輸入（CSV、設定、HTTP、租約）都必須驗證。
- **可靠性**：單一商品失敗不得中斷其他商品；設定與 catalog 以原子寫入避免半寫狀態；事件去重跨程序有效；更新檢查不得阻塞主要流程；核心運算模組不得有隱含網路或時鐘依賴。
- **可及性**：網頁表單元件具備 label 與鍵盤可操作；通知與狀態不得只依賴顏色；K 線圖以形狀／文字標註相位，並提供文字摘要作為替代。
- **可測試性**：所有自動測試離線可跑；網路、時鐘、隨機、檔案路徑與程序控制皆可注入；測試以公開函式介面、CLI 子程序與 HTTP 端點為觀察邊界。
- **可重現性**：同一輸入與參數必須得到位元相同的結果；不使用隨機；排序在同分時以索引升冪。

## 7. 測試策略

| 公開觀察邊界 | 對應 AC | 測試層級／方式 | 測試資料與依賴 | 選擇理由 |
| --- | --- | --- | --- | --- |
| `python3 scripts/bootstrap_env.py` 子程序與 `.venv`（工作目錄 `ocaievo/`） | AC-001 | 整合（實跑腳本） | 真實網路取得 `get-pip.py` 與 PyPI wheel；重跑一次驗證冪等 | 環境建置沒有可先寫的行為 Red，改用實際執行與重跑作為驗證 |
| `ediaad.data` 公開函式 | AC-002～AC-004 | 單元 ＋ 快取往返整合 | `tmp_path` 合成 CSV；同一資料的兩種來源路徑 | 契約（欄位、dtype、排序）是最容易默默退化的地方，需逐項斷言 |
| `ediaad.features` 公開函式 | AC-005～AC-007 | 單元 ＋ 性質測試（尺度不變） | 手算算例 ＋ 合成序列；乘常數與平移 | 尺度不變是本專案最重要的性質，必須以性質測試強制 |
| `ediaad.similarity`／`ediaad.scan` | AC-008～AC-011 | 單元 ＋ 人工植入片段 | 合成序列與植入的重疊片段 | 重疊抑制的邊界（恰好 50%）只能用人工植入驗證 |
| `ediaad.outlook` | AC-012～AC-013 | 單元 | 已知報酬算例；`ScanMatch` 與 `PatternEvent` 兩種輸入 | 兩條路線共用同一函式，需驗證契約一致（F-002 回歸） |
| `ediaad.patterns` 公開函式 | AC-014～AC-021 | 單元 ＋ oracle 植入 ＋ 反例 | 依已知參數植入三相位的合成序列；四種反例；乘常數與平移 | 規律路線可解釋性最高，能以合成 oracle 精確斷言相位邊界 |
| `ediaad.monitor` 公開函式 | AC-022～AC-026 | 單元（注入假 fetch／emit／sleep／時鐘） | 假資料來源、假時鐘、`tmp_path` 事件檔 | 監控的所有外部效果可注入，因此完全離線可測且可控制時間 |
| `python -m ediaad` 子程序 | AC-027～AC-029 | 端到端子程序測試 ＋ 計時 | 合成 CSV；`report.json` 結構；10,000 根效能資料 | 只有子程序層能驗證 exit code 與報表契約 |
| `ediaad.markets.*` 公開函式 | AC-030～AC-038 | 單元（假 HTTP 客戶端）＋ 實測存證 | 假 HTTP 回應（含 TWSE 民國年與千分位樣本）；`docs/workflow/evidence/twse-probe/` 的實測存證作對照 | 來源格式不穩，需以固定樣本驗證解析，避免測試依賴網路 |
| `ediaad.store`、`ediaad.config` | AC-039～AC-040 | 整合（真實 SQLite 暫存檔、真實檔案系統） | `tmp_path` 的真實 SQLite 與設定檔；損毀檔案樣本 | 持久化與原子寫入不能只對 mock 宣稱通過 |
| HTTP 端點與 SSE | AC-041～AC-048、AC-066 | 整合（標準庫 client 對真實服務）＋ 少量瀏覽器人工檢查 | 真實服務實例、合成資料、假來源 | 網頁是主要介面；API 可用自動化驗證，視覺與互動以人工檢查補足 |
| 啟動器與停止腳本 | AC-049～AC-050 | 整合（子程序 ＋ 埠探測） | 真實程序與 PID 檔；`tmp_path` 的 PID 位置 | 程序生命週期只能用真實程序驗證 |
| 通知模組 | AC-051 | 單元（假通知後端）＋ Linux 實機人工檢查 | 假後端；Linux 以 `notify-send` 實測 | 桌面通知無法在 CI 驗證；macOS／Windows 標示未實機驗證 |
| `ediaad.license`／`ediaad.update` | AC-052～AC-059 | 單元 ＋ RFC 8032 向量 ＋ 假時鐘與假 HTTP | 官方測試向量、合成租約、假時鐘、假 HTTP 客戶端 | 授權邏輯必須確定性；時間與網路皆需可控 |
| `cloudflare/worker` 純函式 | AC-060～AC-063 | 單元（`node --test`，假 D1 轉接層） | 合成密鑰／租約／黑名單；假 D1 | 無真實帳號與部署授權，只能驗證純函式與轉接介面 |
| CLI 子命令 | AC-064 | 端到端子程序測試 | 合成設定與假來源 | exit code 語意需在子程序層驗證 |
| 全套整合 | AC-065 | 整合（pytest ＋ node --test ＋ validate_workflow.py） | 全部合成資料 | 交付前必須在同一版本上跑完整套件 |

- 現有測試先例：無（全新專案）。既有 `~/桌面/DSH/ediaad` 的 185 個案例可作**設計參考**，但本專案從零重建，不複製其程式碼，也不以其通過代替本專案驗證。
- 必要的人工／視覺檢查：
  1. 三個相位的 K 線圖標註與偵測結果目視一致（AC-043）。
  2. 網頁在 Chrome（Wayland）下的實際互動：下拉搜尋、參數即時預覽、SSE 提醒、關閉服務按鈕（AC-042～AC-050）。
  3. Linux 桌面通知實際彈出（AC-051）。
  4. 台股除權息還原前後的命中差異目視核對（AC-034）。
- 不適用的方式及原因：無瀏覽器自動化工具（不引入 Node 建置工具鏈），故不做跨瀏覽器視覺回歸；macOS／Windows 無實機，故不做跨平台通知驗收；Cloudflare 無部署授權，故不做線上端到端驗收。

## 8. 假設、未決與風險

- **blocking（僅對 implement 階段）**：Q-015 產品實作授權尚未記錄。SPEC 內容與測試邊界經使用者確認、並在 PROJECT.md 記下授權原意與日期後，才進入 ready 與 implement。規劃與文件交付不受阻。
- **assumption（已授權自行決定，記錄理由與驗證方式）**：
  - Q-004 技術棧採報告第 6.3 節決策（標準庫 HTTP、SSE、原生前端、canvas）；驗證方式為 AC-041～AC-046 的整合測試與人工檢查。
  - Q-005 Ed25519 以純 Python 實作；驗證方式為 AC-054 的 RFC 8032 官方向量。
  - Q-011 Cloudflare 帳號／網域／D1 不存在，以佔位設定實作並只做本機測試；部署另行取得授權。
  - Q-012 除權息還原公式以 TWSE 欄位（除權息前收盤價、除權息參考價、權值+息值）為依據；驗證方式為 AC-034。
  - Q-016 不 `git init`，以檔案快照雜湊作 TDD／Review 基準；若使用者同意可改為 Git SHA。
- **deferred（明確不在本版）**：Q-013 Twelve Data 真實金鑰與額度；Q-014 macOS／Windows 實機通知。
- **風險**：
  1. 預設規格偏保守（報告實測 4,000 根只命中 1 筆）→ 以參數面板即時預覽（AC-044）與範例學習（AC-045）降低門檻，並在交付報告標明預設值為保守取向。
  2. 統計未處理片段相關性 → 交付時揭露樣本數與片段時間範圍，不宣稱獨立性。
  3. 單一範例學習可能過擬合 → 容差朝「更容易命中範例」放寬並在網頁顯示推估參數供使用者檢視。
  4. 授權只能防君子（純 Python 可被改）→ 控制力放在「更新」；交付報告明列此誠實邊界。
  5. 股票市場「連續等距 K 線」假設不成立 → 以交易日曆與市場別預設參數處理（AC-035）。
  6. 範圍大（66 項 AC、37 張 Task）→ 以相依順序分批實作，每張 Task 獨立可驗證；必要時依使用者指示縮減批次。

## 9. 變更紀錄

| 版本 | 變更與理由 | 受影響 AC／Task | 確認依據 |
| --- | --- | --- | --- |
| 0.1 | 初版：依 `docs/architecture/ENGINEERING-REPORT.md` 從零重建，涵蓋報告第 3、4、5、6、7 章全部功能；依 2026-09-24 實測修正報告的台股除權息結論（`startDate`／`endDate` 可用） | 全部 | 使用者 2026-09-24 選擇「本工作區、從零重建、全部範圍」 |
| 0.2 | 規劃交付前的自我複核：把報告第 3.2 節的功能清單（F1–F14、G1–G20）逐條對照 AC 表，發現 **G11 授權頁**只有「更換密鑰」與「功能分級」（AC-057）而沒有頁面顯示需求，補上 AC-066（授權狀態、剩餘天數、重新申請連結、首次啟用表單）並歸給 TASK-025；v0.1 的 65 項 AC 內容與文字不變 | AC-066、TASK-025、TASK-037 | 規劃交付前的自我複核（報告 3.2 G11 對照），尚未經使用者確認 |
| 0.3 | 規劃交付前的自我複核（模組契約）：報告第 4.3／6.1 節的 `ediaad/sources/base.py`、`ediaad/sources/binance.py` 是為「v0.3 建構在既有 v0.2 程式碼上」而保留的向後相容層；本專案依 ADR-001 從零重建，沒有需要相容的呼叫端，保留會讓 Binance 取得出現兩條路徑並重現 F-001 的資料結構不一致風險。移除這兩個模組，`ediaad/markets/crypto.py` 成為唯一實作；連帶把 TASK-012／TASK-013 的相容層工作移出範圍。AC 集合不變（66 項，無新增、刪除或改號） | TASK-012、TASK-013；SPEC 第 5 節模組表與相容性段落 | 規劃交付前的自我複核（報告 4.3／6.1 對照 ADR-001），尚未經使用者確認 |
| 0.4 | 實作 TASK-003 前逐維推導 AC-006 時，發現 v0.1 寫下的敘述不可能成立：把整段價格**加常數平移**後，`total_return`＝`close[-1]/close[0]-1`、`return_std`（逐根**比值**報酬的標準差）與 `max_drawdown`（`close` 對累積最高的**比值**）依定義必然改變。報告第 5.1 節只宣稱特徵「**乘上正數 k 後全部不變**」；平移不變性是報告第 2.11 節對**規律判定**的要求，已由 AC-019 涵蓋。修正 AC-006 為「乘常數 → 10 維全部不變；平移 → 第 3、4、5、6、8、9、10 維不變（共 7 維）」，並在 AC 文字中明列不具平移不變性的三維與理由。AC ID 與其他 AC 內容不變 | AC-006、AC-019、TASK-003 | 實作 TASK-003 前的規格複核；此為修正我方建立 Spec 時的過度要求（使需求與報告一致），已於 2026-09-24 進度報告中告知使用者，尚未收到反對 |

# 附錄 A：需求來源對照（報告功能清單 → AC）

這張表是「報告的每一項功能都有人負責」的查核依據，供確認範圍時逐條核對。報告的章節與編號直接引用 `docs/architecture/ENGINEERING-REPORT.md`。

## A.1 報告第 3.1 節：v0.2 已交付功能（F1–F14）

| 報告條目 | 功能 | 對應 AC | 負責 Task |
| --- | --- | --- | --- |
| F1 | 環境安裝（bootstrap_env.py） | AC-001 | TASK-001 |
| F2 | 資料載入（load_csv／from_rows） | AC-002、AC-003、AC-004 | TASK-002 |
| F3 | 多維形態特徵抽取（extract／extract_matrix） | AC-005、AC-006、AC-007 | TASK-003 |
| F4 | 相似度排序（rank） | AC-008、AC-009 | TASK-004 |
| F5 | 滑動視窗掃描（scan_similar） | AC-010、AC-011 | TASK-005 |
| F6 | 後續走勢統計（forward_stats） | AC-012、AC-013 | TASK-006 |
| F7 | 規律模型與具名規律（PatternSpec／NAMED_PATTERNS） | AC-014、AC-015 | TASK-007 |
| F8 | 規律偵測（detect） | AC-016、AC-017、AC-018、AC-019、AC-020 | TASK-008 |
| F9 | 由範例學習（learn） | AC-021 | TASK-009 |
| F10 | 監控清單設定（load_config） | AC-022 | TASK-010 |
| F11 | 監控迴圈與提醒（run_once／run_forever） | AC-023、AC-024、AC-025 | TASK-010 |
| F12 | 提醒輸出（format_alert／append_event） | AC-026 | TASK-010 |
| F13 | 資料來源（Binance） | AC-031 | TASK-013 |
| F14 | 命令列介面（match／monitor） | AC-027、AC-028、AC-029 | TASK-011 |

## A.2 報告第 3.2 節：v0.3 規劃功能（G1–G20）

| 報告條目 | 功能 | 對應 AC | 負責 Task |
| --- | --- | --- | --- |
| G1 | 一鍵啟動 | AC-049 | TASK-026 |
| G2 | 優雅關閉 | AC-050 | TASK-026 |
| G3 | 監控清單管理（下拉搜尋） | AC-047 | TASK-025 |
| G4 | 規律參數面板即時命中預覽 | AC-044 | TASK-023 |
| G5 | 範例學習（上傳／貼上 CSV） | AC-045 | TASK-023 |
| G6 | 即時提醒與事件歷史清單 | AC-042 | TASK-021 |
| G7 | K 線圖三相位標註 | AC-043 | TASK-022 |
| G8 | 歷史回看（表單化 match） | AC-046 | TASK-024 |
| G9 | 系統狀態 | AC-048 | TASK-025 |
| G10 | 版本頁 | AC-048 | TASK-025 |
| G11 | 授權頁（狀態、剩餘天數、更換密鑰、重新申請） | AC-066、AC-057 | TASK-025、TASK-031 |
| G12 | 首次啟用 | AC-052 | TASK-030 |
| G13 | 離線可用 | AC-053 | TASK-030 |
| G14 | 自動續期 | AC-056 | TASK-031 |
| G15 | 到期停止 | AC-056 | TASK-031 |
| G16 | 更換密鑰 | AC-057 | TASK-031 |
| G17 | 撤銷 | AC-056 | TASK-031 |
| G18 | 功能分級（features） | AC-057 | TASK-031 |
| G19 | 更新檢查（只顯示不下載） | AC-059 | TASK-032 |
| G20 | 來源清單更新（catalog） | AC-038 | TASK-017 |

## A.3 報告第 4、6、7 章的架構與子系統

| 報告條目 | 內容 | 對應 AC | 負責 Task |
| --- | --- | --- | --- |
| 4.1 | 三條設計原則（計算不碰 I/O、外部效果可注入、錯誤分層） | AC-004、AC-013、AC-024、AC-025 | TASK-002、TASK-006、TASK-010 |
| 4.2／4.3 | 分層與依賴方向、模組清單 | 由 SPEC 第 5 節約束；以 Review 檢查，無獨立 AC。**例外**：報告 4.3 的 `ediaad/sources/` 舊介面不重建（見 SPEC 第 5 節「相容性／遷移」與 ADR-001） | 全部 |
| 4.4 | 資料契約（Series／PatternSpec／PatternEvent／OutlookStats 等） | AC-002、AC-004、AC-014、AC-015、AC-017 | TASK-002、TASK-007、TASK-008 |
| 4.6 | 快取與存放位置（`.cache/`、`~/.local/share/ediaad/`） | AC-031、AC-039、AC-040 | TASK-013、TASK-018、TASK-019 |
| 6.1／6.2 | 元件圖、服務生命週期與啟動器 | AC-049、AC-050 | TASK-026 |
| 6.3 | 網頁層技術決策（標準庫 HTTP／SSE／原生前端／canvas／127.0.0.1） | AC-041、AC-042、AC-043 | TASK-020、TASK-021、TASK-022 |
| 6.4 | 租約格式、三個觸發點、撤銷導流、時鐘防護、Ed25519 | AC-052、AC-053、AC-054、AC-055、AC-056、AC-058 | TASK-028、TASK-029、TASK-030、TASK-031 |
| 6.5 | 更新 manifest 與六條架構約束 | AC-059、AC-061 | TASK-032、TASK-034 |
| 6.6 | 通知子系統（三管道） | AC-051 | TASK-027 |
| 6.7 | Cloudflare 後端（Worker／靜態／D1／後台／申請頁） | AC-060、AC-061、AC-062、AC-063 | TASK-033、TASK-034、TASK-035 |
| 7.1 | Source 介面與 registry（廢除全域 ALLOWED_INTERVALS） | AC-030 | TASK-012 |
| 7.2 | 目錄清單（可透過更新攜帶） | AC-038 | TASK-017 |
| 7.3 | 加密貨幣／台股／美股／自訂四來源 | AC-031、AC-032、AC-033、AC-036、AC-037 | TASK-013、TASK-014、TASK-016 |
| 7.4 | 除權息處理、交易日曆、為何由本機 Python 抓資料 | AC-034、AC-035 | TASK-015 |
| 8.2 | 已知限制（7 項） | SPEC 第 8 節風險逐項對應；由 AC-065 在 DELIVERY 揭露 | TASK-037 |
| 附錄 A／B | 實測環境與資料來源結論 | 由本次實測修正並記入 `PROJECT.md` 與 `adr/ADR-003.md`；無獨立 AC | — |

## A.4 對照結果

- 報告 F1–F14、G1–G20 全部有對應 AC 與負責 Task，無遺漏（G11 於 SPEC-001 v0.2 補上 AC-066）。
- 報告第 4、6、7 章的架構與子系統全部落在 SPEC 第 5 節契約或 AC 中；僅「依賴方向」與「模組責任」屬架構約束，以 Review 逐張檢查而非獨立 AC（已在此表標明）。
- 報告中與實測不符的敘述（台股除權息無可用來源、環境無 curl）已在 `PROJECT.md` 實測表與 `adr/ADR-003.md` 修正，並以存證檔保留證據。
