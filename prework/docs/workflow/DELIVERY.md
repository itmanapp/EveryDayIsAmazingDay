# ediaad 交付報告（DELIVERY）

- 交付日期：2026-09-25
- Spec：`SPEC-001 v0.4`（66 項 active AC）
- 任務：TASK-001～TASK-037 **全部 done**（37 張，其中 TASK-025 含在內）
- 驗收快照：`ocaievo/` 檔案樹 sha256 `ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab`（122 個檔案；TASK-036 的 `checked_version`）
- 本報告由 TASK-037 產出。**本張只做唯讀檢查與文件**：未修改任何產品程式碼、未部署任何東西、未執行 `git`／`push`／Issue／合併、未發布版本。

## 1. 最終驗收結果（可重跑的三個命令）

| # | 命令（工作目錄） | exit | 輸出摘要 | 日期 |
| --- | --- | --- | --- | --- |
| 1 | `.venv/bin/python -m pytest -q`（`ocaievo/`）第 1 次 | 0 | `1007 passed, 2 warnings in 180.18s` | 2026-09-25 |
| 2 | `.venv/bin/python -m pytest -q`（`ocaievo/`）第 2 次 | 0 | `1007 passed, 2 warnings in 179.18s` | 2026-09-25 |
| 3 | `.venv/bin/python -m pytest -q`（`ocaievo/`）第 3 次 | 0 | `1007 passed, 2 warnings in 180.45s` | 2026-09-25 |
| 4 | `node --test`（`ocaievo/cloudflare/`） | 0 | `ℹ tests 82 / pass 82 / fail 0`（80 個測試案例＋2 個檔案層級項目） | 2026-09-25 |
| 5 | `python3 .project-workflow/scripts/validate_workflow.py .`（專案根） | 0 | 「通過：流程文件結構與宣告一致」 | 2026-09-25 |
| 6 | `python3 /tmp/check_tasks.py`（專案根；契約檢查） | 0 | 「檢查 37 個 Task 檔；SPEC AC 66 項；索引 37 張；結果：通過」 | 2026-09-25 |
| 7 | 本報告的對照表完整性檢查（見 §7） | 0 | 66 列、每項 AC 恰一次、所有證據與實作路徑存在 | 2026-09-25 |

- **三次全套是刻意的**：TASK-036 期間曾有一個背景執行緒測試在整套測試下間歇性失敗（`test_background_without_an_executor_uses_a_daemon_thread`），修正後（改為 join 具名執行緒並斷言 daemon 性質）連續三次全套皆通過，未再出現（見 §7）。
- 兩個警告來自 pytest 對第三方套件（pandas）的棄用提示，與本專案程式碼無關；沒有 warning 被當成通過的理由或掩蓋。

## 2. AC 對照表（66 項 active AC）

欄位說明：
- **實作位置**：相對 `ocaievo/` 的檔案（公開函式與類別列於各張 Task 的「模組與公開介面」與 TDD 的交付檔案表）。
- **驗證證據**：該 AC 的預期測試／檢查（取自 `TASKS.md` 的規劃欄）＋實際測試檔；人工檢查另行標示。
- **結果**：`通過（自動）`＝有可重跑的自動證據；後綴的人工／實機項目列在 §3 與 §5。
- **證據路徑**：相對 `docs/workflow/` 的 TDD 與 Review 紀錄。

| AC | 負責 Task | 實作位置 | 驗證證據 | 結果 | 證據路徑 |
| --- | --- | --- | --- | --- | --- |
| AC-001 | TASK-001 | `scripts/bootstrap_env.py`、`requirements.txt`、`requirements-dev.txt` | 實跑 bootstrap_env.py 後檢查 venv、依賴與重跑冪等；`（子程序驗證：`bootstrap_env.py` 的 exit code 與 import 檢查）` | 通過（自動） | `tdd/TASK-001.md`、`reviews/TASK-001.md` |
| AC-002 | TASK-002 | `ediaad/data.py`、`ediaad/errors.py` | 合成 CSV 載入後比對欄位順序、UTC ns、升冪與無重複；``tests/test_data.py`` | 通過（自動） | `tdd/TASK-002.md`、`reviews/TASK-002.md` |
| AC-003 | TASK-002 | `ediaad/data.py`、`ediaad/errors.py` | 五種壞輸入各自丟出 DataFormatError 且訊息含欄位或列號；``tests/test_data.py`` | 通過（自動） | `tdd/TASK-002.md`、`reviews/TASK-002.md` |
| AC-004 | TASK-002 | `ediaad/data.py`、`ediaad/errors.py` | load_csv 與 from_rows 同構；快取往返後 dtype 與值不變；``tests/test_data.py`` | 通過（自動） | `tdd/TASK-002.md`、`reviews/TASK-002.md` |
| AC-005 | TASK-003 | `ediaad/features.py` | 手算算例逐維比對，順序等於 FEATURE_NAMES；``tests/test_features.py`` | 通過（自動） | `tdd/TASK-003.md`、`reviews/TASK-003.md` |
| AC-006 | TASK-003 | `ediaad/features.py` | 乘 0.01／0.5／1／1000 與三種平移後特徵不變；退化視窗為有限值；``tests/test_features.py`` | 通過（自動） | `tdd/TASK-003.md`、`reviews/TASK-003.md` |
| AC-007 | TASK-003 | `ediaad/features.py` | extract_matrix 形狀 (181,10) 且與逐窗 extract 相同；``tests/test_features.py`` | 通過（自動） | `tdd/TASK-003.md`、`reviews/TASK-003.md` |
| AC-008 | TASK-004 | `ediaad/similarity.py` | 完全相同候選排名第 1、分數 1.0、值域與同分索引升冪；``tests/test_similarity.py`` | 通過（自動） | `tdd/TASK-004.md`、`reviews/TASK-004.md` |
| AC-009 | TASK-004 | `ediaad/similarity.py` | 三種壞權重 ConfigError；權重整體縮放不改變排序；``tests/test_similarity.py`` | 通過（自動） | `tdd/TASK-004.md`、`reviews/TASK-004.md` |
| AC-010 | TASK-005 | `ediaad/scan.py` | 植入重疊片段檢查寬度、筆數上限與 50% 邊界；``tests/test_scan.py`` | 通過（自動） | `tdd/TASK-005.md`、`reviews/TASK-005.md` |
| AC-011 | TASK-005 | `ediaad/scan.py` | 四種壞參數各自 ConfigError 並指出不合法處；``tests/test_scan.py`` | 通過（自動） | `tdd/TASK-005.md`、`reviews/TASK-005.md` |
| AC-012 | TASK-006 | `ediaad/outlook.py` | 已知後續報酬算例的統計值、尾端排除、空樣本 None；``tests/test_outlook.py`` | 通過（自動） | `tdd/TASK-006.md`、`reviews/TASK-006.md` |
| AC-013 | TASK-006 | `ediaad/outlook.py` | end_attr 分別指向 end_index 與 recovery_index 皆正確；``tests/test_outlook.py`` | 通過（自動） | `tdd/TASK-006.md`、`reviews/TASK-006.md` |
| AC-014 | TASK-007 | `ediaad/patterns.py` | 合法／不合法規格建構結果與 frozen 檢查；``tests/test_patterns_spec.py`` | 通過（自動） | `tdd/TASK-007.md`、`reviews/TASK-007.md` |
| AC-015 | TASK-007 | `ediaad/patterns.py` | JSON round-trip 穩定；缺／多／型別錯誤皆 ConfigError；``tests/test_patterns_spec.py`` | 通過（自動） | `tdd/TASK-007.md`、`reviews/TASK-007.md` |
| AC-016 | TASK-008 | `ediaad/patterns.py` | ATR 算例與植入點後乘 10 的差異小於 1e-12；``tests/test_patterns_detect.py`` | 通過（自動） | `tdd/TASK-008.md`、`reviews/TASK-008.md` |
| AC-017 | TASK-008 | `ediaad/patterns.py` | 植入三相位後斷言四個索引與 confidence 值域；``tests/test_patterns_detect.py`` | 通過（自動） | `tdd/TASK-008.md`、`reviews/TASK-008.md` |
| AC-018 | TASK-008 | `ediaad/patterns.py` | 四種反例皆零命中；``tests/test_patterns_detect.py`` | 通過（自動） | `tdd/TASK-008.md`、`reviews/TASK-008.md` |
| AC-019 | TASK-008 | `ediaad/patterns.py` | 乘常數與平移後命中索引完全相同；``tests/test_patterns_detect.py`` | 通過（自動） | `tdd/TASK-008.md`、`reviews/TASK-008.md` |
| AC-020 | TASK-008 | `ediaad/patterns.py` | 同結構只留最長且依盤整長度降冪；``tests/test_patterns_detect.py`` | 通過（自動） | `tdd/TASK-008.md`、`reviews/TASK-008.md` |
| AC-021 | TASK-009 | `ediaad/patterns.py` | 合成範例推估落在容差內且能命中自身；失敗回 ConfigError；``tests/test_patterns_learn.py`` | 通過（自動） | `tdd/TASK-009.md`、`reviews/TASK-009.md` |
| AC-022 | TASK-010 | `ediaad/monitor.py` | 合法與五種壞設定檔的載入與錯誤位置；``tests/test_monitor.py`` | 通過（自動） | `tdd/TASK-010.md`、`reviews/TASK-010.md` |
| AC-023 | TASK-010 | `ediaad/monitor.py` | 連續三輪提醒次數為 1、0、1；``tests/test_monitor.py`` | 通過（自動） | `tdd/TASK-010.md`、`reviews/TASK-010.md` |
| AC-024 | TASK-010 | `ediaad/monitor.py` | 注入單一商品失敗後其餘仍提醒；程式錯誤上拋；``tests/test_monitor.py`` | 通過（自動） | `tdd/TASK-010.md`、`reviews/TASK-010.md` |
| AC-025 | TASK-010 | `ediaad/monitor.py` | 資料不足計入 skipped 並附 warning；``tests/test_monitor.py`` | 通過（自動） | `tdd/TASK-010.md`、`reviews/TASK-010.md` |
| AC-026 | TASK-010 | `ediaad/monitor.py` | 摘要欄位順序與 JSONL 九欄位附加寫入；``tests/test_monitor.py`` | 通過（自動） | `tdd/TASK-010.md`、`reviews/TASK-010.md` |
| AC-027 | TASK-011 | `ediaad/cli.py`、`ediaad/__main__.py` | match 子程序 exit code 與 report.json 五個頂層鍵；`tests/test_cli_match_monitor.py` | 通過（自動） | `tdd/TASK-011.md`、`reviews/TASK-011.md` |
| AC-028 | TASK-011 | `ediaad/cli.py`、`ediaad/__main__.py` | monitor --once 與常駐的 exit code 與中斷處理；`tests/test_cli_match_monitor.py` | 通過（自動） | `tdd/TASK-011.md`、`reviews/TASK-011.md` |
| AC-029 | TASK-011 | `ediaad/cli.py`、`ediaad/__main__.py` | 10,000 根、視窗 60、top 20 的實際計時紀錄；`tests/test_cli_match_monitor.py` | 通過（自動） | `tdd/TASK-011.md`、`reviews/TASK-011.md` |
| AC-030 | TASK-012 | `ediaad/markets/__init__.py`、`ediaad/markets/base.py`、`ediaad/markets/custom.py` | registry 欄位完整；週期驗證依來源查詢；`tests/test_markets_base.py` | 通過（自動） | `tdd/TASK-012.md`、`reviews/TASK-012.md` |
| AC-031 | TASK-013 | `ediaad/markets/crypto.py`、`ediaad/markets/__init__.py` | 假 HTTP 客戶端計數請求次數與四種快取情境；`tests/test_markets_binance.py` | 通過（自動） | `tdd/TASK-013.md`、`reviews/TASK-013.md` |
| AC-032 | TASK-014 | `ediaad/markets/twse.py`、`ediaad/markets/__init__.py` | TWSE 民國年與千分位樣本的正規化結果；`tests/test_markets_twse.py` | 通過（自動） | `tdd/TASK-014.md`、`reviews/TASK-014.md` |
| AC-033 | TASK-014 | `ediaad/markets/twse.py`、`ediaad/markets/__init__.py` | 以代號與中文名搜尋並限制筆數；`tests/test_markets_twse.py` | 通過（自動） | `tdd/TASK-014.md`、`reviews/TASK-014.md` |
| AC-034 | TASK-015 | `ediaad/markets/adjust.py`、`ediaad/markets/calendar.py` | 還原後除權息日不再命中；未還原會假命中（對照）；`tests/test_markets_twse_adjust.py` | 通過（自動）；除權息前後的命中差異目視核對未執行 | `tdd/TASK-015.md`、`reviews/TASK-015.md` |
| AC-035 | TASK-015 | `ediaad/markets/adjust.py`、`ediaad/markets/calendar.py` | 非交易日不視為連續；市場別預設參數可覆寫；`tests/test_markets_twse_adjust.py` | 通過（自動） | `tdd/TASK-015.md`、`reviews/TASK-015.md` |
| AC-036 | TASK-016 | `ediaad/markets/us.py`、`ediaad/markets/__init__.py` | 無金鑰錯誤訊息；金鑰不出現在 watchlist.json 與日誌；`tests/test_markets_twelvedata.py` | 通過（自動） | `tdd/TASK-016.md`、`reviews/TASK-016.md` |
| AC-037 | TASK-012 | `ediaad/markets/__init__.py`、`ediaad/markets/base.py`、`ediaad/markets/custom.py` | 自訂 CSV 來源沿用 load_csv 契約與錯誤行為；`tests/test_markets_base.py` | 通過（自動） | `tdd/TASK-012.md`、`reviews/TASK-012.md` |
| AC-038 | TASK-017 | `ediaad/markets/catalog.py`、`ediaad/markets/__init__.py` | 版本較新才下載；相同不下載；失敗保留原檔；`tests/test_markets_catalog.py` | 通過（自動） | `tdd/TASK-017.md`、`reviews/TASK-017.md` |
| AC-039 | TASK-018 | `ediaad/store.py` | 真實 SQLite 重啟後同事件不重複提醒；事件可查詢；`tests/test_store.py` | 通過（自動） | `tdd/TASK-018.md`、`reviews/TASK-018.md` |
| AC-040 | TASK-019 | `ediaad/config.py` | 原子寫入；損毀設定不覆蓋原檔並回報；`tests/test_config.py` | 通過（自動） | `tdd/TASK-019.md`、`reviews/TASK-019.md` |
| AC-041 | TASK-020 | `ediaad/paths.py`、`ediaad/app.py`、`ediaad/web/__init__.py` 等 9 項 | 服務只 bind 127.0.0.1；端點回應與錯誤轉譯；`tests/test_web_api.py` | 通過（自動） | `tdd/TASK-020.md`、`reviews/TASK-020.md` |
| AC-042 | TASK-021 | `ediaad/web/sse_hub.py`、`ediaad/web/routes.py`、`ediaad/web/server.py` 等 7 項 | SSE 推播延遲、斷線重連不重複、事件篩選；`tests/test_web_sse.py`、`tests/test_store.py` | 通過（自動）；Chrome 實際互動未執行 | `tdd/TASK-021.md`、`reviews/TASK-021.md` |
| AC-043 | TASK-022 | `ediaad/web/routes.py`、`ediaad/app.py`、`ediaad/markets/custom.py` 等 7 項 | canvas 繪製與三相位標註位置一致（人工核對）；`tests/test_web_chart.py`、`tests/test_markets_base.py` | 通過（自動＋替代目視）；真實 canvas 渲染未檢查 | `tdd/TASK-022.md`、`reviews/TASK-022.md` |
| AC-044 | TASK-023 | `ediaad/web/routes.py`、`ediaad/web/static/params.js`、`ediaad/web/static/learn.js` 等 5 項 | 改參數 1 秒內更新命中次數且可重現；`tests/test_web_preview_learn.py` | 通過（自動）；Chrome 即時預覽未執行 | `tdd/TASK-023.md`、`reviews/TASK-023.md` |
| AC-045 | TASK-023 | `ediaad/web/routes.py`、`ediaad/web/static/params.js`、`ediaad/web/static/learn.js` 等 5 項 | 範例學習頁顯示推估參數與預覽；失敗顯示原因；`tests/test_web_preview_learn.py` | 通過（自動）；Chrome 上傳互動未執行 | `tdd/TASK-023.md`、`reviews/TASK-023.md` |
| AC-046 | TASK-024 | `ediaad/match.py`、`ediaad/cli.py`、`ediaad/web/routes.py` 等 7 項 | 表單化 match 的排行與後續統計；`tests/test_web_match.py`、`tests/test_cli_match_monitor.py` | 通過（自動）；Chrome 表單與表格外觀未檢查 | `tdd/TASK-024.md`、`reviews/TASK-024.md` |
| AC-047 | TASK-025 | `ediaad/web/routes.py`、`ediaad/app.py`、`ediaad/monitor.py` 等 9 項 | 下拉搜尋新增／移除與設定寫入；`tests/test_web_watchlist_status.py` | 通過（自動）；Chrome 下拉搜尋未執行 | `tdd/TASK-025.md`、`reviews/TASK-025.md` |
| AC-048 | TASK-025 | `ediaad/web/routes.py`、`ediaad/app.py`、`ediaad/monitor.py` 等 9 項 | 系統狀態與版本頁欄位；`tests/test_web_watchlist_status.py` | 通過（自動）；Chrome 狀態／版本頁未檢查 | `tdd/TASK-025.md`、`reviews/TASK-025.md` |
| AC-049 | TASK-026 | `ediaad/launcher.py`、`ediaad/app.py`、`ediaad/paths.py` 等 9 項 | 未啟動／已啟動兩種啟動行為與就緒等待；`tests/test_launcher_lifecycle.py` | 通過（自動）；桌面圖示雙擊與瀏覽器開啟未人工檢查 | `tdd/TASK-026.md`、`reviews/TASK-026.md` |
| AC-050 | TASK-026 | `ediaad/launcher.py`、`ediaad/app.py`、`ediaad/paths.py` 等 9 項 | 網頁按鈕與 stop.sh 的優雅結束與埠釋放；`tests/test_launcher_lifecycle.py` | 通過（自動）；Chrome 關閉按鈕未執行 | `tdd/TASK-026.md`、`reviews/TASK-026.md` |
| AC-051 | TASK-027 | `ediaad/notify/__init__.py`、`ediaad/notify/message.py`、`ediaad/notify/web.py` 等 9 項 | 三管道觸發；Linux 實機；跨平台標示未驗證；`tests/test_notify.py` | 通過（自動）；Linux 實機彈出與 macOS／Windows 未驗證 | `tdd/TASK-027.md`、`reviews/TASK-027.md` |
| AC-052 | TASK-030 | `ediaad/license.py`、`ediaad/paths.py` | 啟用流程取得 30 天簽章租約並落地；`tests/test_license_activate.py`、`tests/test_license_startup.py`、`tests/_ed25519_fixture.py` | 通過（自動） | `tdd/TASK-030.md`、`reviews/TASK-030.md` |
| AC-053 | TASK-030 | `ediaad/license.py`、`ediaad/paths.py` | 啟動流程不發出任何網路請求（計數為 0）；`tests/test_license_activate.py`、`tests/test_license_startup.py`、`tests/_ed25519_fixture.py` | 通過（自動） | `tdd/TASK-030.md`、`reviews/TASK-030.md` |
| AC-054 | TASK-029 | `ediaad/license.py` | RFC 8032 官方測試向量全部通過；`tests/test_license_ed25519.py` | 通過（自動） | `tdd/TASK-029.md`、`reviews/TASK-029.md` |
| AC-055 | TASK-028 | `ediaad/license.py` | 指紋穩定且指紋不符時驗證失敗；`tests/test_license_fingerprint.py` | 通過（自動） | `tdd/TASK-028.md`、`reviews/TASK-028.md` |
| AC-056 | TASK-031 | `ediaad/license.py`、`ediaad/paths.py` | 續期重算 30 天、逾期停止、撤銷停止、renew 回 403；`tests/test_license_renew.py`、`tests/test_license_features.py` | 通過（自動） | `tdd/TASK-031.md`、`reviews/TASK-031.md` |
| AC-057 | TASK-031 | `ediaad/license.py`、`ediaad/paths.py` | features 分級與更換密鑰；`tests/test_license_renew.py`、`tests/test_license_features.py` | 通過（自動） | `tdd/TASK-031.md`、`reviews/TASK-031.md` |
| AC-058 | TASK-030 | `ediaad/license.py`、`ediaad/paths.py` | 時間回調時強制線上驗證（issued_at 與 high_water）；`tests/test_license_activate.py`、`tests/test_license_startup.py`、`tests/_ed25519_fixture.py` | 通過（自動） | `tdd/TASK-030.md`、`reviews/TASK-030.md` |
| AC-059 | TASK-032 | `ediaad/update.py`、`ediaad/paths.py`、`ediaad/app.py` 等 6 項 | 六條約束逐條驗證（逾時、不阻塞、靜默、快取、去抖動、可關閉）；`tests/test_update.py` | 通過（自動） | `tdd/TASK-032.md`、`reviews/TASK-032.md` |
| AC-060 | TASK-033 | `cloudflare/schema.sql`、`cloudflare/wrangler.toml`、`cloudflare/package.json` 等 16 項 | node --test 驗證 activate／renew／403／renewals trigger；`tests/test_update.py` | 通過（自動） | `tdd/TASK-033.md`、`reviews/TASK-033.md` |
| AC-061 | TASK-034 | `cloudflare/static/latest.json`、`cloudflare/static/catalog.json`、`cloudflare/worker/src/static.js` 等 5 項 | manifest 與 catalog schema 與可快取性；`tests/test_static_snapshot.py` | 通過（自動） | `tdd/TASK-034.md`、`reviews/TASK-034.md` |
| AC-062 | TASK-035 | `cloudflare/worker/src/admin.js`、`cloudflare/worker/src/reapply.js`、`cloudflare/worker/src/db.js` 等 7 項 | 五張表與後台操作（假 D1）；— | 通過（自動） | `tdd/TASK-035.md`、`reviews/TASK-035.md` |
| AC-063 | TASK-035 | `cloudflare/worker/src/admin.js`、`cloudflare/worker/src/reapply.js`、`cloudflare/worker/src/db.js` 等 7 項 | 過期者可重新申請、黑名單被拒絕；— | 通過（自動） | `tdd/TASK-035.md`、`reviews/TASK-035.md` |
| AC-064 | TASK-036 | `ediaad/cli.py`、`ediaad/launcher.py`、`ediaad/license.py` 等 4 項 | serve 與 license 子命令的 exit code 語意；`tests/test_cli_serve.py`、`tests/test_cli_license.py`、`tests/_cli_helpers.py` 等 6 項 | 通過（自動） | `tdd/TASK-036.md`、`reviews/TASK-036.md` |
| AC-065 | TASK-037 | `（本報告本身：`docs/workflow/DELIVERY.md`；非產品程式碼）` | 全套 pytest 與 node --test 及 AC 對照；`（以三個命令的 exit code、證據路徑存在性與 66 列對照表作為替代驗證）` | 通過（自動） | `tdd/TASK-037.md`、`reviews/TASK-037.md` |
| AC-066 | TASK-025 | `ediaad/web/routes.py`、`ediaad/app.py`、`ediaad/monitor.py` 等 9 項 | 三種授權狀態的頁面呈現、首次啟用表單、剩餘天數、重新申請連結與文字化狀態；`tests/test_web_watchlist_status.py` | 通過（自動）；Chrome 三態畫面未檢查 | `tdd/TASK-025.md`、`reviews/TASK-025.md` |

## 3. 未驗證清單（誠實邊界）

| 項目 | 涉及 | 為什麼未驗證 | 解除條件 |
| --- | --- | --- | --- |
| 真實 Cloudflare 帳號／D1／網域與部署 | TASK-033、TASK-034、TASK-035 | 沒有帳號、`database_id` 與網域，且部署未授權（`PROJECT.md` 的對外動作清單）。**未執行任何 `wrangler` 指令** | 取得帳號與部署授權後：`wrangler d1 execute --file schema.sql`、`wrangler dev` 跑 activate／renew／reapply，再以 CLI 對真實 Worker 做一次端到端 |
| 靜態端點的實際 HTTP 與 CDN 快取 | TASK-034 | 端點由 Pages／R2 或任何靜態主機提供，本機只驗證回應函式與快照（`Cache-Control` 是回應值，CDN 行為未驗證） | 部署後 `curl -I` 檢查兩個端點的標頭與快取狀態 |
| CLI → 真實授權服務的端到端 | TASK-036 | Worker 未部署；本機以 loopback 假服務驗請求契約 | 同第一項；並以 `license activate`／`renew` 對真實端點各跑一次 |
| macOS／Windows 桌面通知（實機） | TASK-027 | 開發機為 Linux；通知命令的組裝有單元測試，但沒有實機 | 在 macOS／Windows 上以 `--serve` 觸發一次命中事件 |
| Linux `notify-send` 實際彈出 | TASK-027 | 自動測試刻意不執行真實通知命令（避免污染桌面） | 在 Linux 桌面以 `--serve` 觸發一次命中事件並目視 |
| Twelve Data 真實金鑰與額度 | TASK-016 | 沒有真實 API key；金鑰存放與來源介面以假來源／假 HTTP 驗證 | 申請免費金鑰後以真實端點抓一次（並確認額度限制的錯誤路徑） |
| 自動下載／安裝新版本 | TASK-032、TASK-034 | **明確 out of scope**（SPEC 第 2 節、報告第 3.3 節）：v0.3 只顯示版本資訊 | 需要新 AC 與簽章驗證設計（下載檔的 `sha256` 校驗、安裝流程） |
| 跨瀏覽器視覺回歸 | AC-041～AC-048、AC-066 | 無瀏覽器自動化工具，且不引入 Node 建置工具鏈（SPEC 第 7 節明訂不做） | 引入 Playwright 等工具（會改變「不引入 Node 工具鏈」的決定，屬新需求） |
| SPEC 第 7 節的四項人工／視覺檢查 | AC-034、AC-042～AC-050、AC-051、AC-066 | 沒有瀏覽器自動化、沒有 macOS／Windows 實機，且工作環境為非互動式 | 依 SPEC 第 7 節逐項在 Chrome（Wayland）與 Linux 桌面完成；替代驗證已記於各張 TDD |
| 長期執行的穩定性 | TASK-025、TASK-032 | 測試只跑單輪輪詢與單次更新檢查；數小時的漂移、狀態老化與執行緒殘留未量測 | 連續執行服務數小時並觀察狀態頁與記憶體 |
| Windows 的訊號語意 | TASK-026、TASK-036 | 只在 Linux 以 SIGINT／SIGTERM 驗證優雅結束 | 在 Windows 上以 `CTRL_BREAK`／終止程序驗證 |

## 4. 已知限制（設計取捨，不是缺陷）

| 限制 | 說明 | 出處 |
| --- | --- | --- |
| 客戶端授權只能防君子 | 改一行程式碼即可繞過驗章／不回報；能防的是「改租約、偽造租約、搬到別台機器」與「沒有新密鑰就拿不到新版」 | 報告第 6.4 節「誠實邊界」表 |
| 統計未處理片段相關性 | 後續走勢統計把各片段視為獨立樣本；重疊片段（`overlap`）會讓樣本彼此相關，機率不是嚴格的信賴區間 | 報告 F-002／TASK-006 |
| 預設規格偏保守 | 內建 `range_fakeout_reversion` 的參數（盤整 20～120 根、假跌破深度 0.2～1.5 帶寬、5 根內回歸）偏向「少而準」；這會漏掉型態不同但概念相同的訊號 | 報告第 4.4 節、`patterns.py` |
| 除權息還原依 TWSE 欄位 | 還原公式以 TWSE 的除權息前收盤價／參考價／權值+息值為依據；其他市場沒有等價處理 | ADR-003、TASK-015 |
| 資料來源失敗是部分成功 | 一個來源失敗時其餘商品照常輪詢（錯誤記在狀態頁），因此「這一輪沒有命中」與「這一輪有商品抓不到」必須分開看 | TASK-013、TASK-025 |
| 密鑰以明文存 D1、activate 無速率限制 | 資料庫外洩時未使用的密鑰可被啟用；`POST /v1/activate` 可被暴力嘗試 | TASK-033 的 A-3／A-6、TASK-035 的 A-2 |
| `license activate --key` 會出現在 shell 歷史與 `ps` | 任務明訂不從 stdin 讀取（避免互動式提示），但參數本身是另一種暴露 | TASK-036 的 A-4 |
| 快照（manifest／catalog）目前是佔位值 | `version=0.0.0`、`released_at=1970-01-01`、`.invalid` 網址、`sha256` 全 0；發行前必須取代，且 `catalog_version` 在 manifest／catalog／`wrangler.toml`／租約四處需同源 | TASK-034 的 A-1／A-2 |
| SSE 的 keep-alive 每秒一幀 | 為了讓瀏覽器與代理不因閒置斷線；代價是每條連線每秒一個小封包 | TASK-021 |
| 通知是 best-effort | 平台不支援／命令不存在／非 0 結束都只記 warning，不影響監控 | TASK-027 |

## 5. 未執行或失敗的檢查（逐項原因與處理）

| 檢查 | 狀態 | 原因 | 處理／解除條件 |
| --- | --- | --- | --- |
| 三個命令（pytest／`node --test`／`validate_workflow.py`） | **全部通過** | — | §1 已記錄輸出與 exit code |
| SPEC 第 7 節人工／視覺檢查（4 項） | **未執行** | 無瀏覽器自動化、無 macOS／Windows 實機、非互動式環境 | 交付後由使用者依 SPEC 第 7 節逐項目視；替代驗證見各張 TDD 的「未執行或受阻」 |
| 真實後端（Cloudflare）驗收 | **未執行** | 無帳號／網域，部署未授權 | §3 第 1～3 項 |
| 歷史失敗 1：TASK-025 的啟用端點預設 HTTP 客戶端 | **已修正** | 預設值是**函式** `http_post`，而核心要的是有 `.post()` 的**物件**；真實路徑會 500，TASK-025 的測試因全部注入假物件而看不到 | TASK-036 加入 `HTTP_CLIENT`、修正 `routes.py`，並補一個「不注入客戶端」的回歸測試（`test_web_watchlist_status.py`） |
| 歷史失敗 2：`load_lease` 的錯誤訊息沒有檔名 | **已修正** | 訊息只有「無法解析租約 JSON」 | TASK-036 在 `load_lease` 加上 `租約檔 <path>：` |
| 歷史失敗 3：內嵌簽章公鑰是 fail-closed 佔位值，導致授權閘門無法放行 | **已修正** | TASK-033 沒有真實金鑰可替換 | TASK-036 新增 `EDIAAD_LICENSE_PUBLIC_KEY`（含格式驗證、不回退） |
| 歷史失敗 4：`test_background_without_an_executor_uses_a_daemon_thread` 間歇性失敗 | **已修正並複核** | 疑似高負載下的執行緒排程（10 秒輪詢 → 30 秒仍偶發，約 5 次全套出現 2 次） | TASK-036 改為 join 具名執行緒＋斷言 daemon 性質；本次驗收**連續三次全套通過**（§1） |
| 歷史失敗 5：TASK-025 的 `monitor_error` 等三處測試自傷、TASK-033 的 `AUTOINCREMENT`、TASK-035 的四個測試錯誤 | **已修正** | 各張 TDD 的「如實記載」有完整紀錄 | 不影響交付；保留紀錄供追溯 |

## 6. 交付範圍與統計

| 項目 | 數量 |
| --- | --- |
| `ocaievo/` 檔案樹 | 122 個檔案（sha256 `ca155909…`） |
| Python 產品模組 | 37 個 `.py`（`ediaad/` 19 ＋ `ediaad/` 子套件 18）＋ 2 個 `scripts/` 啟動腳本；約 9,382 行 |
| Python 測試 | 36 個 `test_*.py` ＋ 2 個夾具（`_ed25519_fixture.py`、`_cli_helpers.py`）；**1,007 個案例** |
| Cloudflare 後端 | `worker/src/` 9 個 `.js`、`schema.sql`、`wrangler.toml`、`package.json`、`static/` 2 個 JSON；測試 8 個 `.test.mjs` ＋ 2 個夾具；**82 個案例**（`node --test`） |
| 工作文件 | 119 個 Markdown：37 張 Task、36 份 TDD、36 份 Review、`PROJECT/BRIEF/CONTEXT/SPEC/TASKS/STATE/DELIVERY`、3 份 ADR、`evidence/` |
| 外部依賴 | numpy 2.5.3、pandas 3.0.6、pytest 9.1.1（皆釘版本）；**Cloudflare 端零 npm 依賴**；無 `cryptography`（Ed25519 為純 Python） |

重跑方式（工作目錄 `ocaievo/`）：

```
.venv/bin/python -m pytest -q          # Python 全套
cd cloudflare && node --test            # 授權後端（不需 wrangler／npm）
cd .. && python3 .project-workflow/scripts/validate_workflow.py .   # 流程文件結構（專案根）
```

## 7. 跨 Task 測試變更與本次驗收的複核

各張 Task 的 `checked_version` 對應它當時的凍結版；後續 Task 為了修正或補強，動過四個測試檔。以單張 Task 檔的 `test_evidence`／`review_evidence` 為權威，摘要如下（**以現行檔案樹重跑才是本報告的驗收依據**）：

| 檔案 | 變更 | 原因 | 複核 |
| --- | --- | --- | --- |
| `tests/test_update.py`（TASK-032） | 背景輪詢上限 10 秒 → 30 秒，之後改為 join 具名執行緒＋daemon 斷言 | 間歇性失敗（見 §5） | 連續三次全套通過；單檔 3/3 |
| `cloudflare/test/router.test.mjs`（TASK-033） | 路由表由「恰兩個端點」改為「恰四個端點」 | TASK-035 依 AC-063 新增 `GET`／`POST /reapply`（這正是該測試要抓的變更） | `node --test` 82/82 |
| `tests/test_web_watchlist_status.py`（TASK-025） | 新增 1 個回歸測試（預設 HTTP 客戶端） | 修好 §5 的歷史失敗 1 後補上防止復發 | 全套通過 |
| `tests/test_notify.py`（TASK-027） | `FakeApp` 替身補上 `problems`／`settings` | `_run_service` 現在會讀這兩個 `Application` 屬性 | 全套通過 |

**對照表完整性檢查**（唯讀腳本 `/tmp/check_delivery.py`，不修改任何檔案）：

- 本檔的 AC 對照表恰有 **66 列**，AC-001～AC-066 各**恰出現一次**（0 缺漏、0 重複）。
- 每一列指向的**證據路徑**（`tdd/TASK-0NN.md`、`reviews/TASK-0NN.md`）都存在，且對應的 Task 檔為 `done` 並帶有 `test_evidence`／`review_evidence`。
- 每一列提到的**實作檔與測試檔**都存在於 `ocaievo/`。
- 腳本 exit 0；輸出摘要記於 `docs/workflow/tdd/TASK-037.md`。

## 8. 授權與對外動作（明確聲明）

- **未**執行 `git init`／`commit`／`push`／開 Issue／合併／發布版本；本專案未初始化 Git，所有版本識別以檔案快照 sha256 表示。
- **未**部署任何 Cloudflare 資源，**未**執行 `wrangler deploy`／`pages deploy`／`d1 execute`；`wrangler.toml` 只有 `REPLACE_WITH…` 佔位值。
- **未**連線任何真實外部服務作為驗收依據；所有自動測試離線可跑（假 HTTP／假來源／假 D1／loopback 服務）。
- 真實端點只在規劃階段以唯讀探測存證（`docs/workflow/evidence/twse-probe/twse-endpoints.json`），未在驗收中使用。
