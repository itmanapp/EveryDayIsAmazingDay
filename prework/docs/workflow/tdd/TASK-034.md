# TASK-034 測試紀錄

- task_id：TASK-034
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-static-snapshot sha256:2b1d1b16deec9d682570dd12603643f048129e431b39d8bf2bb78d1de0678a65
- alternative_reason：**部分替代**——部署後的實際 HTTP 標頭、CDN 快取行為與真實網域路由無法驗證（無帳號／網域／D1，且部署未授權）；本張以「純函式產生回應（可斷言 `status`／`headers`／`body`）」＋「快照檔案以 `node:fs` 讀入」＋「**跨語言**：同一份快照再交給 Python 的 `parse_manifest`（TASK-032）與 `load_catalog`（TASK-017）讀一次」驗證。未驗證項由 TASK-037 的 DELIVERY 明列。
- Task／Spec 版本：TASK-034 / SPEC-001 v0.4
- 測試邊界：（1）`validateManifest`／`validateCatalog`／`validateSnapshot`／`manifestResponse`／`catalogResponse` 直接呼叫（不啟動伺服器、不發出任何請求）；（2）`cloudflare/static/*.json` 以 `node:fs` 讀入後餵進上述函式；（3）**跨語言**：`tests/test_static_snapshot.py` 讓 Python 端的客戶讀取同一份快照；（4）以「毒環境」Proxy 與原始碼檢查證明靜態回應不碰 D1／不匯入授權流程。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-033 與 TASK-025 的交付物（`cloudflare/static/` 尚不存在），Python 全套 **966 passed**、Node `node --test` **42 passed**（本張完成後為 Python **971 passed**、Node **54 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `729d545795e5a2158bcd15cfaa77f3a6189b73e50d1206b45e95fbdc40cec362`（110 個檔案，即 TASK-033 的 `checked_version`）。
- TDD 不適用的理由與替代驗證（若有）：見「未執行或受阻」第 1 點（部署與 CDN 快取）。

工作目錄：Node 測試在 `ocaievo/cloudflare/`（`node --test`），Python 測試在 `ocaievo/`（`.venv/bin/python -m pytest -q`）。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `cloudflare/static/latest.json` | `9751e3b4` | 新增：凍結 schema 的 manifest 快照（十個鍵；`version`／`released_at`／`min_supported`／`catalog_version`／兩個網址都是**佔位值**，`sha256` 為 64 個 0、`size` 為 0） |
| `cloudflare/static/catalog.json` | `11efdf95` | 新增：catalog 快照（`catalog_version` 與 manifest 同源；四個來源與八個商品，來源與商品都對得上真實 registry 的 id） |
| `cloudflare/worker/src/static.js` | `67ab011c` | 新增：`MANIFEST_KEYS`／`CATALOG_KEYS`／`CACHE_CONTROL`、`validateManifest`／`validateCatalog`／`validateSnapshot`（回錯誤清單）、`manifestResponse`／`catalogResponse`（回 `{status, headers, body}`，`env` 刻意忽略） |
| `cloudflare/test/static.test.mjs` | `bfc00af9` | 新增：12 個測試（schema、佔位值、版本同源、可快取標頭、毒環境、500 路徑、`wrangler.toml` 對照） |
| `cloudflare/wrangler.toml` | `bcfc6036` | 修改：新增靜態端點的對照區塊（Pages／R2 提供、**刻意不經過 Worker**）與部署前的 `validateSnapshot` 檢查指令；仍只有佔位值 |
| `tests/test_static_snapshot.py` | `c8acadcd` | 新增：5 個測試（同一份快照用 Python 的 `parse_manifest` 與 `load_catalog` 讀、版本同源、佔位網域） |

## Cycle 1：manifest 的凍結 schema（4 個測試）

- 測試：`static/latest.json` 的鍵集合**恰為**十個（比對排序後的鍵）；`validateManifest` 回空陣列；`schema === 1`；欄位形狀（`version` 是 `x.y.z`、`released_at` 是秒級 UTC、`catalog_version` 是 `YYYY-MM-DD`、`sha256` 是 64 個小寫十六進位、`size` 是非負整數、`notes` 是字串、兩個網址是絕對 https）；`url`／`catalog_url` 的主機名稱以 `.invalid` 結尾、`sha256` 全為 0、`size` 為 0（**一眼看得出來是佔位**）。
- 實作：`static.js` 的 `MANIFEST_KEYS`／`validateManifest`、`static/latest.json`。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `node --test test/static.test.mjs` | 1 | `ERR_MODULE_NOT_FOUND`（`worker/src/static.js` 不存在）；Python 端 `4 failed, 1 passed`（`static/latest.json` 不存在） | 尚未有 `static/`／2026-09-25 |
| Green | `node --test test/static.test.mjs` | 0 | `ℹ tests 12 / pass 12 / fail 0` | snap-2026-09-24-ocaievo-static-snapshot／2026-09-25 |

## Cycle 2：catalog 的契約與版本同源（3 個測試）

- 測試：`validateCatalog` 對快照回空陣列；`sources`／`instruments` 非空、每個商品的 `source_id` 都存在於 `sources`；`validateSnapshot` 回空陣列且兩個 `catalog_version` 相等；**刻意讓兩者不同時**（`catalog_version` 改成 `2099-12-31`）必須回非空錯誤且訊息含 `catalog_version`。
- 實作：`validateCatalog`（含「商品的 `source_id` 必須存在」）／`validateSnapshot`、`static/catalog.json`。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/static.test.mjs` | 0 | `12 passed`（含版本錯位的案例） |

- **版本同源是「兩個檔案一份快照」的守門員**：`validateSnapshot` 是公開函式而不是只寫在測試裡，因此部署前可以跑同一條檢查（`wrangler.toml` 的註解就放了那行指令）。變異 `S11`（把一致性判斷改成 `false`）與 `J02`／`J07`（只改其中一個檔案的版本）都被抓到——後兩者同時被 **Python 端**的 `test_snapshots_share_one_catalog_version` 抓到。

## Cycle 3：純靜態回應（3 個測試）

- 測試：兩個回應的 `status === 200`、`content-type` 是 JSON、`cache-control` 同時含 `public`／`max-age=NNN`／`stale-while-revalidate=NNNN`，且 `body` 解析回來等於快照本身；**不需要任何綁定**——以一個「任何屬性都拋錯」的 Proxy 當 `env` 傳入仍成功，且省略 `env` 也成功；原始碼層級斷言 `static.js` 不匯入 `db.js`／`activate.js`／`renew.js`／`router.js` 且不含 `.prepare(`；快照不合法時回 500＋`error.code="invalid_snapshot"`＋錯誤清單，且不含堆疊。
- 實作：`manifestResponse`／`catalogResponse`／`staticResponse`／`CACHE_CONTROL`。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/static.test.mjs` | 0 | `12 passed` |

- **「不經過 Worker」是這一張的架構重點**：報告第 6.5 節的理由是「manifest 靜態可快取、Worker 掛掉時仍可讀」，所以兩個端點由 Pages／R2（或任何靜態主機）提供，Worker 的路由表維持**只有兩個 POST**（TASK-033 已釘住）。毒環境 + 原始碼檢查把「沒有偷偷依賴 D1」變成可測的性質。
- 快取標頭用 `public, max-age=300, stale-while-revalidate=86400`：5 分鐘對齊客戶端的去抖動視窗，`stale-while-revalidate` 讓來源短暫不可用時仍能服務（靜態內容的 resilience）。

## Cycle 4：跨語言驗證（5 個 Python 測試）

- 測試：`ediaad.update.parse_manifest` 讀 `latest.json` 後七個顯示欄位如實；`ediaad.markets.catalog.load_catalog` 讀 `catalog.json` 後版本、來源與商品都成立（且商品的 `source_id` 都在來源清單裡）；兩份快照的 `catalog_version` 相同；兩個網址的主機是 `.invalid`；`parse_manifest` 對非物件仍回 `ConfigError`。
- 實作：測試檔 `tests/test_static_snapshot.py`（產品程式碼未動）。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `.venv/bin/python -m pytest tests/test_static_snapshot.py -q` | 0 | `5 passed in 0.35s` |

- **為什麼要在 Python 端再驗一次**：JS 端說「合法」只證明 JS 的規則；真正會讀這兩個檔案的是客戶端（TASK-017 的 catalog 載入器與 TASK-032 的 manifest 解析）。跨語言各驗一次，才不會出現「JS 說合法、客戶端讀不進去」的分岔（報告 F-001 的形狀）。變異 `J05`（把 `url` 改成真實網域）由**兩邊**同時抓到（Node 11 passed／1 failed；Python 4 passed／1 failed）。

## Cycle 5：部署對照（2 個測試）

- 測試：`wrangler.toml` 記錄了 `/v1/latest` 與 `catalog.json` 的對照、使用 `.invalid`、且不含 32 位十六進位識別碼（後者與 TASK-033 的 schema 測試重疊，屬刻意的雙重防護）。
- 實作：`wrangler.toml` 的註解區塊（含部署前的 `validateSnapshot` 檢查指令）。

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Green | `node --test test/static.test.mjs` | 0 | `12 passed` |

## Red → Green 的實際順序

| 階段 | 命令 | exit | 關鍵輸出 |
| --- | --- | --- | --- |
| Red | `node --test test/static.test.mjs`／`.venv/bin/python -m pytest tests/test_static_snapshot.py -q` | 1 | `ERR_MODULE_NOT_FOUND`（static.js）＋ Python `4 failed, 1 passed`（快照檔不存在） |
| Green 1（實作完成） | `node --test` | 1 | `ℹ tests 54 / pass 50 / fail 4`（catalog 驗證把選填鍵當成必填） |
| Green 2 | `node --test` | 0 | `ℹ tests 54 / pass 54 / fail 0`（52 個測試案例＋2 個 Node 回報的檔案層級項目） |
| Green 3（凍結版） | `node --test` ＋ Python 全套 | 0 | `54 passed`；Python `971 passed` |

## 變異測試（凍結版）

- 工具：`/tmp/mutate_task034.py`（整行／整段替換、`count(frm) == 1` 才套用、每輪逾時 180 秒、跑完立即還原並比對 sha256、`flock` 鎖單一行程、`SIGTERM`／`SIGINT`／`atexit` 會還原；`files` 可混合 Node 測試檔與 `"python"`，兩邊都會跑並合併結果）。
- 矩陣：**32 個變異**（`static.js` 20、`latest.json` 6、`catalog.json` 4、`wrangler.toml` 2），涵蓋鍵集合（少一個、未知鍵）、每一個 schema 檢查（schema／version／released_at／catalog_version／sha256／size／網址／必填鍵）、catalog 的來源／商品／`source_id` 存在性、版本一致性、快取標頭、內容型別、回應主體、500 分支、`sources` 對照集合的計算，以及四個快照欄位的佔位值與 `wrangler.toml` 的佔位值。
- **第一階段沒有存活者**（這一張的驗證函式幾乎每個分支都有對應的負例），**最終 32／32 全數偵測到（0 存活、0 無效）**；逐輪輸出形如 `ℹ pass 11 / fail 1`，跨語言項目為兩邊合併（例如 `S11`：Node `16 passed / 1 failed`）。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `node --test`（工作目錄 `ocaievo/cloudflare/`） | 0 | `ℹ tests 54 / pass 54 / fail 0`（52 個測試案例） |
| `.venv/bin/python -m pytest tests/test_static_snapshot.py -q` | 0 | `5 passed in 0.35s` |
| `.venv/bin/python -m pytest -q` | 0 | `971 passed, 2 warnings in 153.49s` |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |
| 凍結版檔案樹 | — | sha256 `2b1d1b16deec9d682570dd12603643f048129e431b39d8bf2bb78d1de0678a65`（115 個檔案） |

## 如實記載的實作／測試錯誤

1. **選填鍵被當成必填**：第一版 `validateCatalog` 用同一組「四個鍵全部必填」的規則檢查 `sources`，於是快照裡沒有 `needs_api_key` 的三個來源都被判不合法（4 個測試失敗）。已把鍵檢查改為「必填＋選填」兩組：來源只有 `id` 必填，商品 `symbol`／`interval`／`source_id` 必填、`display_name` 選填（與 TASK-017 的載入器一致，但對「上線用的快照」更嚴格一點：商品不該缺 interval）。
2. **`known.size > 0` 的守衛會掩蓋錯誤**：`source_id` 的存在性檢查原本寫成「只有當來源集合非空時才檢查」，而來源集合為空時（來源清單不合法）就會**安靜跳過**——這正好會讓「商品指向不存在的來源」在來源清單壞掉時不被發現。已拿掉該守衛（改為一律檢查），並補一個「商品指向不存在的來源」的負例測試。
3. **測試 helper 的兩處自傷**（TASK-033 的延伸）：見該張紀錄；本張沒有再遇到。
4. **`wrangler.toml` 的檢查指令是單行 shell**：放在註解裡供部署前使用；本張沒有執行它（執行它會是另一條自動化路徑，屬 TASK-037 的整體驗收）。

## 未執行或受阻

1. **部署與 CDN 快取未驗證**：沒有 Cloudflare 帳號／網域／D1，**未執行任何部署指令**（`wrangler deploy`／`wrangler pages deploy` 皆未使用）。因此「部署後 `GET /v1/latest` 的實際標頭」「CDN 是否照 `Cache-Control` 快取」「靜態主機與 Worker 的路由是否真的分開」都無法在此驗證，由 TASK-037 的 DELIVERY 明列。
2. **兩個端點沒有被真的以 HTTP 提供**：本張只交付純函式與快照（測試計畫明訂「不啟動伺服器、不發出任何請求」）；若要在本機端到端複核，需要一個小靜態伺服器（例如以 `static.js` 的回應函式包一個 handler），屬 TASK-037。
3. **manifest 的 `url`／`sha256`／`size` 只做 schema 驗證**：本張不下載、不校驗版本檔（那是發行流程；AC-059 的六條約束屬 TASK-032）。
4. **快照內容是佔位值**：`version` 為 `0.0.0`、`released_at` 為 1970-01-01、兩個網址指向 `.invalid`；發行前必須以實際版本資訊取代（`notes` 已寫明），替換後要重跑 `validateSnapshot` 與兩套測試。
