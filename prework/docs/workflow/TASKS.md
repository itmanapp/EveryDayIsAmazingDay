# 任務索引

- 依據 Spec：SPEC-001 v0.4（ready）
- 整體實作授權：**已記錄**（2026-09-24 使用者回覆「1-正確、2-同意、3-開始實作」，並指定所有實作與程式碼置於 `ocaievo/`）。見 `docs/workflow/PROJECT.md`
- 路徑慣例：本檔與各張 Task 的實作檔案路徑一律相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`

每張 Task 的詳細檔案是狀態權威來源，本檔維持同步摘要。Task ID 不重用。

## 執行清單

| ID／詳細檔案 | 交付行為 | 類型 | depends_on | 狀態 |
| --- | --- | --- | --- | --- |
| TASK-001 tasks/TASK-001.md | 可重現的 venv、pip 取得與依賴安裝腳本 | setup | [] | done |
| TASK-002 tasks/TASK-002.md | OHLC 序列契約、CSV 與資料列載入及錯誤回報 | feature | [TASK-001] | done |
| TASK-003 tasks/TASK-003.md | 10 維尺度不變特徵抽取與批次矩陣 | feature | [TASK-002] | done |
| TASK-004 tasks/TASK-004.md | 穩健正規化、加權距離與相似度排序 | feature | [TASK-003] | done |
| TASK-005 tasks/TASK-005.md | 滑動視窗掃描與重疊抑制 | feature | [TASK-004] | done |
| TASK-006 tasks/TASK-006.md | 後續走勢統計與雙路線共用介面 | feature | [TASK-002] | done |
| TASK-007 tasks/TASK-007.md | 規律規格模型、驗證與序列化 | feature | [TASK-002] | done |
| TASK-008 tasks/TASK-008.md | ATR 與規律偵測器（相位、反例、去重、尺度不變） | feature | [TASK-007] | done |
| TASK-009 tasks/TASK-009.md | 由範例學習規律參數 | feature | [TASK-008] | done |
| TASK-010 tasks/TASK-010.md | 監控設定、輪詢、提醒去重、錯誤隔離與提醒輸出 | feature | [TASK-008] | done |
| TASK-011 tasks/TASK-011.md | match／monitor 子命令、JSON 報表與效能門檻 | feature | [TASK-005, TASK-006, TASK-010] | done |
| TASK-012 tasks/TASK-012.md | Source 介面、registry 與自訂 CSV 來源 | refactor | [TASK-002] | done |
| TASK-013 tasks/TASK-013.md | Binance 來源與四種快取情境 | feature | [TASK-012] | done |
| TASK-014 tasks/TASK-014.md | TWSE 日線來源與商品搜尋 | feature | [TASK-012] | done |
| TASK-015 tasks/TASK-015.md | TWSE 除權息還原與交易日曆 | feature | [TASK-008, TASK-014] | done |
| TASK-016 tasks/TASK-016.md | Twelve Data 來源與金鑰存放隔離 | feature | [TASK-012] | done |
| TASK-017 tasks/TASK-017.md | 版本化 catalog 與更新攜帶 | feature | [TASK-012] | done |
| TASK-018 tasks/TASK-018.md | SQLite 落地與跨程序提醒去重 | feature | [TASK-010] | done |
| TASK-019 tasks/TASK-019.md | 設定解析與原子寫入 | feature | [TASK-010] | done |
| TASK-020 tasks/TASK-020.md | Web 服務骨架與 API 對應核心函式 | feature | [TASK-011, TASK-018, TASK-019] | done |
| TASK-021 tasks/TASK-021.md | SSE 即時提醒與事件歷史篩選 | feature | [TASK-020] | done |
| TASK-022 tasks/TASK-022.md | K 線圖與三相位標註 | feature | [TASK-020, TASK-008] | done |
| TASK-023 tasks/TASK-023.md | 規律參數即時預覽與範例學習頁 | feature | [TASK-020, TASK-008, TASK-009] | done |
| TASK-024 tasks/TASK-024.md | 歷史回看頁（表單化 match） | feature | [TASK-020, TASK-011] | done |
| TASK-025 tasks/TASK-025.md | 監控清單管理、系統狀態、版本與授權頁 | feature | [TASK-020, TASK-019, TASK-012, TASK-031] | done |
| TASK-026 tasks/TASK-026.md | 桌面一鍵啟動、重複啟動防護與優雅關閉 | feature | [TASK-020] | done |
| TASK-027 tasks/TASK-027.md | 網頁、瀏覽器原生與服務端桌面三管道通知 | feature | [TASK-018, TASK-020] | done |
| TASK-028 tasks/TASK-028.md | 機器指紋與租約模型 | feature | [TASK-001] | done |
| TASK-029 tasks/TASK-029.md | 純 Python Ed25519 驗章（RFC 8032 向量） | feature | [TASK-001] | done |
| TASK-030 tasks/TASK-030.md | 啟用、離線啟動驗證與時鐘篡改防護 | feature | [TASK-028, TASK-029] | done |
| TASK-031 tasks/TASK-031.md | 續期、到期停止、撤銷與功能分級 | feature | [TASK-030] | done |
| TASK-032 tasks/TASK-032.md | 更新檢查子系統與六條約束 | feature | [TASK-001] | done |
| TASK-033 tasks/TASK-033.md | Cloudflare Worker 啟用與續租 API | feature | [TASK-001] | done |
| TASK-034 tasks/TASK-034.md | 靜態 manifest 與 catalog 端點 | feature | [TASK-033] | done |
| TASK-035 tasks/TASK-035.md | D1 資料模型、後台操作與重新申請頁 | feature | [TASK-033] | done |
| TASK-036 tasks/TASK-036.md | CLI serve 與 license 子命令 | feature | [TASK-011, TASK-020, TASK-030, TASK-032] | done |
| TASK-037 tasks/TASK-037.md | 整合驗收、AC 對照與 DELIVERY | docs | [TASK-001, TASK-002, TASK-003, TASK-004, TASK-005, TASK-006, TASK-007, TASK-008, TASK-009, TASK-010, TASK-011, TASK-012, TASK-013, TASK-014, TASK-015, TASK-016, TASK-017, TASK-018, TASK-019, TASK-020, TASK-021, TASK-022, TASK-023, TASK-024, TASK-025, TASK-026, TASK-027, TASK-028, TASK-029, TASK-030, TASK-031, TASK-032, TASK-033, TASK-034, TASK-035, TASK-036] | done |

## AC 覆蓋

每項 AC 的實作位置與實測結果會在 TASK-037 交付時填入 `docs/workflow/DELIVERY.md`。下表為規劃對照；「最終整合驗證負責 Task」一律為 TASK-037。

| AC | 負責 Task | 預期測試／檢查 | 最終整合驗證負責 Task |
| --- | --- | --- | --- |
| AC-001 | TASK-001 | 實跑 bootstrap_env.py 後檢查 venv、依賴與重跑冪等 | TASK-037 |
| AC-002 | TASK-002 | 合成 CSV 載入後比對欄位順序、UTC ns、升冪與無重複 | TASK-037 |
| AC-003 | TASK-002 | 五種壞輸入各自丟出 DataFormatError 且訊息含欄位或列號 | TASK-037 |
| AC-004 | TASK-002 | load_csv 與 from_rows 同構；快取往返後 dtype 與值不變 | TASK-037 |
| AC-005 | TASK-003 | 手算算例逐維比對，順序等於 FEATURE_NAMES | TASK-037 |
| AC-006 | TASK-003 | 乘 0.01／0.5／1／1000 與三種平移後特徵不變；退化視窗為有限值 | TASK-037 |
| AC-007 | TASK-003 | extract_matrix 形狀 (181,10) 且與逐窗 extract 相同 | TASK-037 |
| AC-008 | TASK-004 | 完全相同候選排名第 1、分數 1.0、值域與同分索引升冪 | TASK-037 |
| AC-009 | TASK-004 | 三種壞權重 ConfigError；權重整體縮放不改變排序 | TASK-037 |
| AC-010 | TASK-005 | 植入重疊片段檢查寬度、筆數上限與 50% 邊界 | TASK-037 |
| AC-011 | TASK-005 | 四種壞參數各自 ConfigError 並指出不合法處 | TASK-037 |
| AC-012 | TASK-006 | 已知後續報酬算例的統計值、尾端排除、空樣本 None | TASK-037 |
| AC-013 | TASK-006 | end_attr 分別指向 end_index 與 recovery_index 皆正確 | TASK-037 |
| AC-014 | TASK-007 | 合法／不合法規格建構結果與 frozen 檢查 | TASK-037 |
| AC-015 | TASK-007 | JSON round-trip 穩定；缺／多／型別錯誤皆 ConfigError | TASK-037 |
| AC-016 | TASK-008 | ATR 算例與植入點後乘 10 的差異小於 1e-12 | TASK-037 |
| AC-017 | TASK-008 | 植入三相位後斷言四個索引與 confidence 值域 | TASK-037 |
| AC-018 | TASK-008 | 四種反例皆零命中 | TASK-037 |
| AC-019 | TASK-008 | 乘常數與平移後命中索引完全相同 | TASK-037 |
| AC-020 | TASK-008 | 同結構只留最長且依盤整長度降冪 | TASK-037 |
| AC-021 | TASK-009 | 合成範例推估落在容差內且能命中自身；失敗回 ConfigError | TASK-037 |
| AC-022 | TASK-010 | 合法與五種壞設定檔的載入與錯誤位置 | TASK-037 |
| AC-023 | TASK-010 | 連續三輪提醒次數為 1、0、1 | TASK-037 |
| AC-024 | TASK-010 | 注入單一商品失敗後其餘仍提醒；程式錯誤上拋 | TASK-037 |
| AC-025 | TASK-010 | 資料不足計入 skipped 並附 warning | TASK-037 |
| AC-026 | TASK-010 | 摘要欄位順序與 JSONL 九欄位附加寫入 | TASK-037 |
| AC-027 | TASK-011 | match 子程序 exit code 與 report.json 五個頂層鍵 | TASK-037 |
| AC-028 | TASK-011 | monitor --once 與常駐的 exit code 與中斷處理 | TASK-037 |
| AC-029 | TASK-011 | 10,000 根、視窗 60、top 20 的實際計時紀錄 | TASK-037 |
| AC-030 | TASK-012 | registry 欄位完整；週期驗證依來源查詢 | TASK-037 |
| AC-031 | TASK-013 | 假 HTTP 客戶端計數請求次數與四種快取情境 | TASK-037 |
| AC-032 | TASK-014 | TWSE 民國年與千分位樣本的正規化結果 | TASK-037 |
| AC-033 | TASK-014 | 以代號與中文名搜尋並限制筆數 | TASK-037 |
| AC-034 | TASK-015 | 還原後除權息日不再命中；未還原會假命中（對照） | TASK-037 |
| AC-035 | TASK-015 | 非交易日不視為連續；市場別預設參數可覆寫 | TASK-037 |
| AC-036 | TASK-016 | 無金鑰錯誤訊息；金鑰不出現在 watchlist.json 與日誌 | TASK-037 |
| AC-037 | TASK-012 | 自訂 CSV 來源沿用 load_csv 契約與錯誤行為 | TASK-037 |
| AC-038 | TASK-017 | 版本較新才下載；相同不下載；失敗保留原檔 | TASK-037 |
| AC-039 | TASK-018 | 真實 SQLite 重啟後同事件不重複提醒；事件可查詢 | TASK-037 |
| AC-040 | TASK-019 | 原子寫入；損毀設定不覆蓋原檔並回報 | TASK-037 |
| AC-041 | TASK-020 | 服務只 bind 127.0.0.1；端點回應與錯誤轉譯 | TASK-037 |
| AC-042 | TASK-021 | SSE 推播延遲、斷線重連不重複、事件篩選 | TASK-037 |
| AC-043 | TASK-022 | canvas 繪製與三相位標註位置一致（人工核對） | TASK-037 |
| AC-044 | TASK-023 | 改參數 1 秒內更新命中次數且可重現 | TASK-037 |
| AC-045 | TASK-023 | 範例學習頁顯示推估參數與預覽；失敗顯示原因 | TASK-037 |
| AC-046 | TASK-024 | 表單化 match 的排行與後續統計 | TASK-037 |
| AC-047 | TASK-025 | 下拉搜尋新增／移除與設定寫入 | TASK-037 |
| AC-048 | TASK-025 | 系統狀態與版本頁欄位 | TASK-037 |
| AC-049 | TASK-026 | 未啟動／已啟動兩種啟動行為與就緒等待 | TASK-037 |
| AC-050 | TASK-026 | 網頁按鈕與 stop.sh 的優雅結束與埠釋放 | TASK-037 |
| AC-051 | TASK-027 | 三管道觸發；Linux 實機；跨平台標示未驗證 | TASK-037 |
| AC-052 | TASK-030 | 啟用流程取得 30 天簽章租約並落地 | TASK-037 |
| AC-053 | TASK-030 | 啟動流程不發出任何網路請求（計數為 0） | TASK-037 |
| AC-054 | TASK-029 | RFC 8032 官方測試向量全部通過 | TASK-037 |
| AC-055 | TASK-028 | 指紋穩定且指紋不符時驗證失敗 | TASK-037 |
| AC-056 | TASK-031 | 續期重算 30 天、逾期停止、撤銷停止、renew 回 403 | TASK-037 |
| AC-057 | TASK-031 | features 分級與更換密鑰 | TASK-037 |
| AC-058 | TASK-030 | 時間回調時強制線上驗證（issued_at 與 high_water） | TASK-037 |
| AC-059 | TASK-032 | 六條約束逐條驗證（逾時、不阻塞、靜默、快取、去抖動、可關閉） | TASK-037 |
| AC-060 | TASK-033 | node --test 驗證 activate／renew／403／renewals trigger | TASK-037 |
| AC-061 | TASK-034 | manifest 與 catalog schema 與可快取性 | TASK-037 |
| AC-062 | TASK-035 | 五張表與後台操作（假 D1） | TASK-037 |
| AC-063 | TASK-035 | 過期者可重新申請、黑名單被拒絕 | TASK-037 |
| AC-064 | TASK-036 | serve 與 license 子命令的 exit code 語意 | TASK-037 |
| AC-065 | TASK-037 | 全套 pytest 與 node --test 及 AC 對照 | TASK-037 |
| AC-066 | TASK-025 | 三種授權狀態的頁面呈現、首次啟用表單、剩餘天數、重新申請連結與文字化狀態 | TASK-037 |

## 相依檢查

- 不存在的 ID／自我相依／循環：無。37 張 Task 的 `depends_on` 只引用存在的較小 ID，方向一致為由基礎到應用，無循環。
- 每個 in-scope AC 皆有負責 Task：是。AC-001 至 AC-066 全部由未取消的 Task 承接，且最終整合驗證一律由 TASK-037 負責。
- 取消的 Task：無。
- 下一張可領取 Task：**無**（37 張全部 done）。最終驗收結果與未驗證清單見 `docs/workflow/DELIVERY.md`。
- 目前阻擋：無。實作授權已於 2026-09-24 記錄。
- 交付狀態：**已交付**（TASK-001～TASK-037 共 37 張全部 done；66 項 active AC 皆有實作與證據）。交付報告：`docs/workflow/DELIVERY.md`。未驗證項與已知限制見該報告 §3～§5。
