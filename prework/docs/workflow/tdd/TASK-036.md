# TASK-036 測試紀錄

- task_id：TASK-036
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-cli-serve-license sha256:ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab
- alternative_reason：**部分替代**——`serve` 啟動後的真實瀏覽器互動屬 TASK-020～TASK-026（本張只驗子程序層的 exit code、就緒與優雅結束）；真實授權服務未部署，`activate`／`renew` 以測試內啟動的 **loopback 假授權服務**（`127.0.0.1:0`、TASK-030 的公開測試向量簽章）驗證，全程不連外網。真實 Cloudflare Worker／D1 的端到端由 TASK-037 的 DELIVERY 明列為未驗證。
- Task／Spec 版本：TASK-036 / SPEC-001 v0.4
- 測試邊界：（1）子程序 `subprocess.run([sys.executable, "-m", "ediaad", …])` 觀察 exit code 與 stdout／stderr；（2）`build_parser()` 驗證子命令與參數樹（不用私有函式）；（3）`serve` 的就緒以 TCP 探測、結束以訊號與埠釋放驗證；（4）授權命令以 loopback 假服務驗證請求契約與落地結果；（5）啟動時的離線授權驗證以合成租約（簽章用測試夾具）驗證拒絕／放行情境。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-035 與 TASK-025 的交付物（`serve`／`license` 子命令尚未存在），Python 全套 **971 passed**、Node **82 passed**（本張完成後為 Python **1007 passed**、Node **82 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `45876364bc01a9749bb4597dcbd6f98453525f31b72ac3b2710a0d5dc4ff78f5`（119 個檔案，即 TASK-035 的 `checked_version`）。
- TDD 不適用的理由與替代驗證（若有）：見「未執行或受阻」第 1 點（真實授權服務與瀏覽器互動）。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/cli.py` | `d0dcc0a2` | 修改：新增 `serve`（`--port` 預設 `EDIAAD_PORT`／8787、`--home`，只 bind `127.0.0.1`，本體交給 `launcher.serve_main`）與 `license status／activate --key／renew --trigger`；錯誤分層補上 `EdiaadError` → 1 與未知例外的一行訊息（`EDIAAD_DEBUG=1` 才給堆疊） |
| `ediaad/launcher.py` | `8f43da1b` | 修改：`_run_service` 加入**啟動時的離線授權驗證**（TASK-030 的 `check_lease`，公鑰可由環境變數覆寫）、`features` 分級（租約沒有 `update` 就停用更新檢查）與設定檔問題的警告（仍啟動） |
| `ediaad/license.py` | `aa609934` | 修改：新增 `UrllibHttpClient`／`HTTP_CLIENT`（核心要的是**物件** `http.post(...)`，模組層 `http_post` 是函式）、`PUBLIC_KEY_ENV`／`public_key_from_env`（可覆寫簽章公鑰，格式錯誤一律 `ConfigError`）；`load_lease` 的解析錯誤現在會**指出檔名** |
| `ediaad/web/routes.py` | `ef01c2f9` | 修改：`POST /api/license/activate` 的預設客戶端由函式改為 `HTTP_CLIENT`（修正 TASK-025 遺留的 `AttributeError`／500） |
| `tests/test_cli_serve.py` | `a8573484` | 新增：17 個子程序測試 |
| `tests/test_cli_license.py` | `b3d524f8` | 新增：18 個子程序測試（含公鑰設定） |
| `tests/_cli_helpers.py` | `8f0e81d5` | 新增：測試夾具（loopback 假授權服務、合成租約、子程序執行器、就緒探測） |
| `tests/test_web_watchlist_status.py` | `4b2ab6ce` | 修改（TASK-025 的測試）：新增 1 個回歸測試——啟用端點在**沒有注入** `license_http` 時必須用預設物件客戶端 |
| `tests/test_notify.py` | `8f942fe4` | 修改（TASK-027 的測試）：`FakeApp` 替身補上 `problems`／`settings`，鏡射 `_run_service` 實際使用的 `Application` 介面 |
| `tests/test_update.py` | `91eb6f4b` | 修改（TASK-032 的測試）：`test_background_without_an_executor_uses_a_daemon_thread` 改為 **join 背景執行緒並斷言 daemon 性質**（原本用輪詢，整套測試下曾間歇性失敗），見「如實記載」第 4 點 |

## Cycle 1：`serve` 的子命令、就緒與優雅結束（5 個測試）

- 測試：`build_parser()` 認得 `serve --port --home`；`--help`／`serve --help`／`license --help`／`license activate --help` 都 exit 0；未佔用的埠可以在 10 秒內就緒（`/api/health` 回 `status: ok`）、PID 檔存在、SIGINT 後 exit 0、埠被釋放且 PID 檔移除；埠被佔用 → exit 1 且訊息可讀、不含 traceback；`EDIAAD_PORT` 的值成為 `--port` 預設，但值不合法時 exit 2 並指出 `EDIAAD_PORT`。
- 實作：`cli.build_parser`／`_run_serve`／`_require_port_env`／`_default_port`，服務本體完全交給 `launcher.serve_main`（TASK-026 的 A-4：同一條路徑）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_cli_serve.py -q` | 1 | `invalid choice: 'serve'`（子命令尚未註冊）／13 failed | 尚未實作／2026-09-25 |
| Green | 同上 | 0 | `13 passed in 11.49s`（實作後）→ 凍結版 `17 passed` | snap-2026-09-24-ocaievo-cli-serve-license／2026-09-25 |

## Cycle 2：啟動時的離線授權驗證（7 個測試）

- 測試：**沒有租約**仍啟動（未啟用是合法狀態，使用者才進得了網頁的啟用表單）並在輸出說明「尚未啟用」；**已過期** → exit 2＋「過期」＋「重新申請」且不佔用埠；**別台機器** → exit 2＋指紋訊息；**已撤銷**（`revoked.json` 標記）→ exit 2＋「撤銷」；**租約檔損毀** → exit 2＋檔名＋不覆寫原檔；**時鐘被往回調**（`issued_at` 在未來）且線上驗證不可用 → exit 1＋「時間異常」；`--home` 必須完整決定資料目錄（租約與時鐘水位都跟著它，不受 `EDIAAD_HOME` 影響）。
- 實作：`launcher._run_service` 的 `check_lease(...)` 呼叫、`license.public_key_from_env`、`load_lease` 的檔名訊息。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `.venv/bin/python -m pytest tests/test_cli_serve.py -q` | 0 | `17 passed` |

- **exit code 的分層是有意義的**：租約存在但無效 → 2（狀態／設定錯誤，使用者要重新申請）；時鐘異常且**線上驗證不可用** → 1（執行期失敗，使用者要確認網路）。前者用 `verdict.force_online` 區分，不靠訊息字串比對。
- **未啟用不是錯誤**：報告第 6.4 節的「每次啟動離線驗章」與 AC-066 的「未啟用顯示首次啟用表單」需要同時成立——沒有租約時服務仍要啟動，否則使用者永遠進不了啟用頁；「有租約但無效」才是必須停下來的導流情境。
- **設定檔損毀仍然啟動**（與 TASK-036.md 測試計畫第 5 點的寫法不同）：TASK-020 明訂「使用者的唯一介面就是這個網頁，起不來就沒得修」，因此 `serve` 只把問題印出來並讓它出現在系統狀態頁；**租約**損毀則必須拒絕啟動（沒有修復介面，且驗章不可能通過）。

## Cycle 3：`license status`（5 個測試）

- 測試：無租約 → exit 2＋「尚未啟用」；有效租約 → exit 0＋「有效期內」＋到期日（逐字）＋剩餘天數＋功能清單，而且**把服務網址指向關閉的埠仍然成功**（證明完全不連網）；已過期／已撤銷 → exit 2＋原因＋「重新申請」；租約檔損毀 → exit 2＋檔名。
- 實作：`_run_license_status`（`load_lease` ＋ `lease_status`，唯讀）。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `.venv/bin/python -m pytest tests/test_cli_license.py -q` | 0 | `18 passed` |

## Cycle 4：`license activate`（6 個測試）

- 測試：缺 `--key` → argparse exit 2；沒有 `EDIAAD_LICENSE_URL` → exit 2 且訊息指名副檔名；成功 → exit 0、印出到期日、`lease.json` 落地且**等於伺服器簽發的那一份**、請求帶 `machine`；假服務回 403 → exit 2 且**不落地**；服務不可達 → exit 1；伺服器回**簽章無效**的租約 → exit 2 且不落地。
- 實作：`_run_license_activate`（`activate(..., http=HTTP_CLIENT, public_key=public_key_from_env())`）。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `.venv/bin/python -m pytest tests/test_cli_license.py -q` | 0 | `18 passed` |

## Cycle 5：`license renew`（7 個測試）

- 測試：成功 → exit 0、`lease.json` 換成延長後的租約、請求欄位恰為 `{key, machine, trigger}` 且**預設 `trigger=manual`**；三種 trigger 各自原樣送出；`--trigger cron` → argparse exit 2；後端對**過期**租約回 403 → exit 2＋「重新申請」且租約檔一位元都沒變；403 且指出 `revoked` → exit 2＋落地撤銷標記；服務不可達 → exit 1 且租約不變；**沒有租約** → exit 2 且**完全不發出請求**。
- 實作：`_run_license_renew`、`license.renew`（既有）。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `.venv/bin/python -m pytest tests/test_cli_license.py -q` | 0 | `18 passed` |

## Cycle 6：`features` 分級與公鑰設定（3 個測試）

- 測試：租約只有 `start` ＋ `EDIAAD_UPDATE_URL` 有設 → 服務起來後 `/api/version` 的 `update_enabled` 為 `False` 且訊息含「已關閉」；租約含 `update` → 維持 `True`；`public_key_from_env` 未設定回內嵌常數、設定值解析成 32 位元組、非十六進位與長度不對都丟 `ConfigError` 且訊息分別指出「十六進位」／「32 位元組」。
- 實作：`launcher._run_service` 的 `has_feature` 分級（只改記憶體，不動使用者的設定檔）、`license.public_key_from_env`。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `.venv/bin/python -m pytest tests/test_cli_serve.py tests/test_cli_license.py -q` | 0 | `35 passed in 25.97s` |

- **公鑰必須可設定**：內嵌的 `LICENSE_PUBLIC_KEY` 是 fail-closed 的 32 位元組佔位值（TASK-029），TASK-033 沒有真實金鑰可替換。若沒有 `EDIAAD_LICENSE_PUBLIC_KEY`，任何租約都驗不過、`serve` 永遠拒絕啟動——授權閘門會變成「產品無法使用」。環境變數讓自架授權服務（以及測試）能指向自己的公鑰，同時保留「預設不信任任何簽章」的性質。
- **AC-057 的接線**（TASK-032 的 A-3）：租約缺少 `update` 時，啟動路徑把記憶體中的 `update_enabled` 設為 `False`（**不覆寫** `settings.json`），因此「缺少功能 → 更新停用」在執行期真的生效。

## Red → Green 的實際順序

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_cli_license.py -q` | 1 | `16 failed, 1 passed`（`invalid choice: 'license'`） |
| Red | `.venv/bin/python -m pytest tests/test_cli_serve.py -q` | 1 | `13 failed`（`invalid choice: 'serve'`） |
| Green 1（CLI 實作後） | `.venv/bin/python -m pytest tests/test_cli_license.py -q` | 1 | `17 passed`（含修正 `load_lease` 的路徑與預設客戶端）→ 之後 `18 passed` |
| Green 2（serve 實作後） | `.venv/bin/python -m pytest tests/test_cli_serve.py -q` | 0 | `13 passed` → 補測試後 `17 passed` |
| Green 3（凍結版） | `.venv/bin/python -m pytest tests/test_cli_serve.py tests/test_cli_license.py -q` | 0 | `35 passed in 25.97s` |

## 變異測試（凍結版）

- 工具：`/tmp/mutate_task036.py`（整行／整段替換、`count(frm) == 1` 才套用、每輪逾時 600 秒、跑完立即還原並比對 sha256、`flock` 鎖單一行程、`SIGTERM`／`SIGINT`／`atexit` 會還原；收集失敗也算「抓到」）。
- 矩陣：**24 個變異**（`cli.py` 12、`launcher.py` 8、`license.py` 3、`routes.py` 1），涵蓋兩個子命令的分派、`status` 的三種狀態與兩個輸出欄位、`renew` 的租約檢查與公鑰、`activate` 的公鑰與網址檢查、`EDIAAD_PORT` 的預設與驗證、啟動閘門的四個決策點（未啟用放行、無效拒絕、強制線上、features 分級）、設定問題的警告、三個路徑參數（`lease_path`／`high_water_path`／公鑰）必須跟著 `--home`、公鑰設定的兩個驗證分支、`load_lease` 的檔名訊息，以及啟用端點的預設客戶端。
- **第一階段沒有存活者**（`status`／`renew`／`serve` 的每個分支都有對應的負例），**最終 24／24 全數偵測到（0 存活、0 無效）**；逐輪輸出形如 `30 passed, 1 failed`。
- 矩陣在**最終測試調整之前**執行（`tests/test_update.py` 的 join 改寫，見「如實記載」第 4 點）：該檔不在矩陣的目標檔案內，被變異的四個模組在矩陣後未曾改動，因此結果仍然有效。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `.venv/bin/python -m pytest tests/test_cli_serve.py tests/test_cli_license.py -q` | 0 | `35 passed in 25.97s` |
| `.venv/bin/python -m pytest -q` | 0 | `1007 passed, 2 warnings in 185.26s` |
| `node --test`（工作目錄 `ocaievo/cloudflare/`） | 0 | `ℹ tests 82 / pass 82 / fail 0` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |
| 凍結版檔案樹 | — | sha256 `ca155909c6fb58862c1009d39a42afbbf6250d5bca11abec8db2ca2a7cdeb1ab`（122 個檔案） |

## 如實記載的實作／測試錯誤

1. **TASK-025 遺留的真實缺陷（本張最重要的發現）**：`routes.activate_license` 的預設 `http` 是模組層的 `http_post`——那是**函式**，而 `activate`／`renew` 要的是有 `.post()` 的**物件**。也就是說：真實路徑（沒有注入 `app.license_http` 時）會以 `AttributeError` 收場（HTTP 500），而 TASK-025 的測試因為**每一個都注入 `RecordingHttp`** 而看不到。CLI 第一次跑預設路徑時就撞上（`'function' object has no attribute 'post'`）。已新增 `license.UrllibHttpClient`／`HTTP_CLIENT`、修正 `routes.py` 的預設值，並在 TASK-025 的測試檔補一個**不注入客戶端**的回歸測試。
2. **`load_lease` 的解析錯誤沒有指出檔名**：訊息只有「無法解析租約 JSON：…」，使用者不知道是哪個檔案（`$EDIAAD_HOME/lease.json`？自訂路徑？）。已在 `load_lease` 包一層加上 `租約檔 <path>：`，CLI 與 `serve` 的訊息因此都能指出檔名。
3. **`License` 的公鑰沒有可設定之處**：內嵌常數是 fail-closed 的佔位值，導致 `serve` 的授權閘門永遠拒絕啟動。已新增 `EDIAAD_LICENSE_PUBLIC_KEY`（含格式驗證與「不回退」的理由）。
4. **TASK-032 的背景執行緒測試在整套測試下間歇性失敗**：原本以 10 秒輪詢檔案，改為 30 秒後仍偶發（`1007 passed` 與 `1 failed` 交替出現）。已改成**直接 join 那個具名執行緒**並斷言它是 daemon——這同時讓測試檢查它名稱所宣稱的性質；重跑三次單檔與一次全套皆通過。根因未完全確定（疑似高負載下的執行緒排程），已記於 Review 的 A-9。
5. **`launcher.py` 的 import 區塊被改壞**：重寫 `from .paths import …` 時留下 `), pid_path`，`serve` 一執行就是 `SyntaxError`。已修正（並以 `ast.parse` 確認）。
6. **TASK-027 的 `FakeApp` 替身不完整**：`_run_service` 現在讀 `app.problems`（設定問題警告）與 `app.settings`（features 分級），替身少了這兩個屬性。已讓替身鏡射真正的 `Application` 介面。

## 未執行或受阻

1. **真實授權服務未部署**：`activate`／`renew` 的伺服器端（TASK-033 的 Worker）沒有真實帳號可部署，因此端到端（CLI → 真實 Worker → D1）未驗證；本張以 loopback 假服務固定請求契約與回應處理。真實 `serve` 後的瀏覽器互動屬 TASK-020～TASK-026 的人工檢查項。
2. **`serve` 的背景更新檢查在真實環境未驗證**：本張驗的是「租約缺少 `update` 時停用」「有 `update` 時啟用」，以及 TASK-032 的六條約束；真實 `EDIAAD_UPDATE_URL` 不存在的行為（靜默失敗）由 TASK-032 的測試固定。
3. **沒有 GUI／互動式提示**：密鑰一律以 `--key` 傳入（避免進入 shell 歷史），這也意味著輸入時密鑰會出現在命令列上（`ps` 可見）；這是 TASK-036.md 明訂的取捨。若日後要更安全，可支援從檔案或 `getpass` 讀取，但那需要新的 AC。
4. **跨平台的訊號行為未驗證**：`serve` 的優雅結束在 Linux 上以 SIGINT 驗證；Windows 的 `CTRL_BREAK`／`SIGTERM` 語意未驗證（與 TASK-026 的既有範圍相同）。
