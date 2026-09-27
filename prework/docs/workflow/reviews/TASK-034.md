# TASK-034 Code Review

- task_id：TASK-034
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-static-snapshot sha256:2b1d1b16deec9d682570dd12603643f048129e431b39d8bf2bb78d1de0678a65
- Task／Spec 版本：TASK-034 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-25，第 1 輪（含「選填鍵被當成必填」與「來源集合為空時安靜跳過檢查」兩處修正）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）；開工前 `ocaievo/` 檔案樹 sha256 `729d545795e5a2158bcd15cfaa77f3a6189b73e50d1206b45e95fbdc40cec362`（110 個檔案，即 TASK-033 的 `checked_version`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `2b1d1b16deec9d682570dd12603643f048129e431b39d8bf2bb78d1de0678a65`（115 個檔案）；本張新增 `cloudflare/static/latest.json` `9751e3b4…`、`cloudflare/static/catalog.json` `11efdf95…`、`cloudflare/worker/src/static.js` `67ab011c…`、`cloudflare/test/static.test.mjs` `bfc00af9…`、`tests/test_static_snapshot.py` `c8acadcd…`；修改 `cloudflare/wrangler.toml` `bcfc6036…`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對
- 納入的檔案：上述六個實作／測試檔案＋本張 TDD／Review 紀錄
- 排除的既有修改及理由：`cloudflare/worker/src/{lease,http,db,activate,renew,router}.js`（TASK-033）本張只**對齊**未修改（router 的路由表刻意維持兩個 POST 端點）；`ediaad/markets/catalog.py`（TASK-017）與 `ediaad/update.py`（TASK-032）只被測試呼叫
- 程式規範來源：`docs/workflow/SPEC.md` AC-061、第 5 節（manifest 與 catalog 的資料契約）、第 7 節測試策略列、第 2 節 out of scope（不部署）；`docs/workflow/tasks/TASK-034.md`；`docs/architecture/ENGINEERING-REPORT.md` 第 6.5 節（manifest schema 全文與「分成兩個端點的理由」）、第 6.1 節元件圖（Pages／R2 提供靜態端點）；`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-061（manifest 鍵集合恰為十個） | `worker/src/static.js` 的 `MANIFEST_KEYS`／`validateManifest`；`test/static.test.mjs` 的鍵集合與缺鍵／多鍵案例 | 符合 | A-1、A-4 |
| AC-061（manifest 的 schema 與欄位格式） | `validateManifest` 的每一條檢查；`static/latest.json` | 符合 | A-1 |
| AC-061（catalog 符合 SPEC 第 5 節契約） | `validateCatalog`；`static/catalog.json`；`tests/test_static_snapshot.py` 的 `load_catalog` 交叉檢查 | 符合 | A-2 |
| AC-061（兩個回應可快取） | `CACHE_CONTROL`（`public, max-age=300, stale-while-revalidate=86400`）；`manifestResponse`／`catalogResponse`；快取標頭測試 | 符合 | A-3、A-6 |
| AC-061（**不依賴 Worker 是否可用**） | 純函式不查 D1、不呼叫 activate／renew；「毒環境」Proxy 測試＋原始碼檢查；`wrangler.toml` 記錄靜態主機對照 | 符合 | A-3、A-5 |
| 快照可被客戶端讀取（跨語言） | `tests/test_static_snapshot.py` 以 `parse_manifest`／`load_catalog` 讀同一份檔案；兩份快照版本同源 | 符合 | A-2、A-7 |

逐條核對（AC-061）：

- **manifest 鍵集合恰為十個、不得多不得缺**：`MANIFEST_KEYS` 是唯一清單，`validateManifest` 以「必填 ∩ 聯集」兩邊檢查；`static/latest.json` 的實際鍵集合以排序後 `deepEqual` 斷言。變異 `S01`（少一個鍵）與 `S19`／`S20`（不檢查缺鍵／未知鍵）都被抓到。符合。
- **catalog 符合 SPEC 第 5 節契約**：`validateCatalog` 檢查 `catalog_version` 格式、`sources`／`instruments` 非空、來源與商品的鍵集合（未知鍵會被抓到）、商品的三個必填欄位、以及**商品的 `source_id` 必須存在於 `sources`**。同一份檔案再以客戶端的 `load_catalog` 讀一次（Python），因此「JS 說合法」與「客戶端讀得進去」都有證據。符合。
- **回應可快取**：兩個回應都帶 `content-type: application/json; charset=utf-8` 與 `cache-control: public, max-age=300, stale-while-revalidate=86400`，且 `body` 解析回來等於快照本身（不多也不少）。變異 `S02`（`no-store`）／`S14`（多一個鍵）／`S15`（`text/plain`）都被抓到。符合。
- **不依賴 Worker 是否可用**：`static.js` 不匯入 `db.js`／`activate.js`／`renew.js`／`router.js`、不含 `.prepare(`（原始碼斷言），且以「任何屬性都拋錯」的 Proxy 當 `env` 傳入仍回 200（**執行時**證明沒有偷偷用綁定）。Worker 的路由表維持只有兩個 POST 端點（TASK-033 的測試釘住），靜態端點由靜態主機提供——這正是報告第 6.5 節「Worker 掛掉時 manifest 仍可讀」的實作方式。符合。
- **版本同源**：`validateSnapshot` 公開一致性檢查，manifest 與 catalog 的 `catalog_version` 相等；刻意錯位時 JS 與 Python **兩邊**都抓到（變異 `S11`／`J02`／`J07`）。符合。

## 品質 Review

- **兩個端點是「純函式 + 快照檔」而不是 Worker 路由（本張最重要的架構決定）**：AC-061 要的是「可快取且不依賴 Worker 是否可用」。把它們掛進 Worker 會讓「Worker 掛掉時仍可讀」變成假的（而且會破壞 TASK-033 已凍結的兩端點路由表）。因此本張交付的是「靜態主機要用的回應函式」與「兩份快照」，並在 `wrangler.toml` 記錄 Pages／R2 的對照與部署前的檢查指令。
- **驗證函式回錯誤清單而不是丟例外**：部署前的檢查需要一次看到所有問題，執行時的回應需要把清單放進 500 的 `details`。兩種用途共用同一份規則，因此「部署前檢查通過」與「執行時不回 500」是同一件事。
- **「必填＋選填」的鍵規則與客戶端一致但更嚴格**：來源只有 `id` 必填、商品 `symbol`／`interval`／`source_id` 必填而 `display_name` 選填——與 TASK-017 的載入器相容（Python 端讀得進去），但對「上線用的快照」多要求 interval（沒有 interval 的商品根本不能抓）。
- **跨語言各驗一次**：`tests/test_static_snapshot.py` 從客戶端那一側讀同一份檔案。這比「JS 自己說合法」強，也正是報告 F-001（同一份資料兩條路徑）想避免的分岔。變異 `J05`（把佔位網址換成真實網域）由兩邊同時抓到。
- **佔位值一眼看得出來**：`version` 為 `0.0.0`、`released_at` 為 1970-01-01、`sha256` 全 0、`size` 為 0、網域用保留的 `.invalid`，且 `notes` 直接寫明「發行前請以實際版本資訊取代」。這讓「忘了換掉佔位值就上線」不可能安靜發生（Python 的更新檢查會說有新版、`url` 也不可能被誤下載）。
- **快取標頭的取捨已記錄**：`max-age=300` 對齊客戶端的去抖動視窗；`stale-while-revalidate=86400` 讓來源短暫不可用時仍能服務（靜態內容的 resilience）。實際 CDN 行為無法在此驗證（A-6）。
- **變異矩陣的強度**：32 個變異在凍結版**全數被抓到、沒有存活者**；`static.js` 的每一個檢查分支、快照的每一個欄位、`wrangler.toml` 的佔位值都有對應的負例。跨語言的兩個變異（`S11`／`J05`）由 Node 與 Python 兩邊各自失敗。
- **沒有動到既有契約**：Worker 路由表、`db.js`、`lease.js` 與 Python 產品程式碼完全未改；新增檔案都在 `cloudflare/static/`、`cloudflare/worker/src/static.js`、`cloudflare/test/static.test.mjs` 與 `tests/test_static_snapshot.py`。未發現新的 blocking 問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 快照內容是佔位值 | advisory（**發行前必做**） | `static/latest.json` 的 `version=0.0.0`、`released_at=1970-01-01`、`min_supported=0.0.0`、網址指向 `.invalid`、`sha256` 全 0、`size=0` | 發行時以實際版本資訊取代（`version`／`released_at`／`min_supported`／`notes`／`catalog_version`／兩個網址／`sha256`／`size`），並重跑 `validateSnapshot` 與兩套測試；`notes` 已寫明此事 | 已記錄（`test_snapshot_urls_are_placeholders` 等測試要求「一眼看得出是佔位」） |
| A-2 | 版本同源的來源 | advisory | 快照的 `catalog_version` 與 `wrangler.toml` 的 `CATALOG_VERSION`（以及租約帶的版本）目前是三個地方各自的值：`1970-01-01`／`1970-01-01`／`"unknown"` | TASK-034 已讓 manifest 與 catalog 同源（有檢查）；發行流程應以**同一次**發行產生三者（例如一個 `release.mjs` 同時寫入 manifest／catalog／`wrangler.toml`），否則會出現三個版本 | 已記錄（`validateSnapshot` ＋ 部署前指令；TASK-033 的 A-4 延續） |
| A-3 | 部署方式未定案 | advisory | `static.js` 的回應函式要由誰呼叫（Pages Functions？R2＋Worker？純靜態主機的設定？）尚未決定；`wrangler.toml` 只記錄對照註解 | 部署前選擇一種（建議 Pages／R2 直接託管 JSON 並以設定標頭 `Cache-Control`，就不需要跑 JS），並確認標頭與本張的 `CACHE_CONTROL` 一致 | 待辦（已記於 `STATE.md`；TASK-037 的 DELIVERY 明列未驗證） |
| A-4 | 與 TASK-032 的契約 | advisory | manifest 的 `schema`／`version`／`released_at` 等欄位由 `ediaad.update.parse_manifest` 讀取；本張的驗證比 TASK-032 的解析**更嚴格**（例如 `min_supported` 在 TASK-032 是選填，在本張必填） | 這是刻意的：上線用的 manifest 不該缺欄位，而客戶端的解析必須容忍舊 manifest。兩邊都有測試，且 Python 端直接讀本張的快照（交叉檢查） | 已記錄（兩邊的綠燈即是證據） |
| A-5 | Worker 是否也提供靜態端點 | advisory | 現在 Worker 對 `GET /v1/latest` 會回 404（路由表只有兩個 POST） | 這是刻意的（報告第 6.5 節：靜態端點不依賴 Worker）。若日後要方便本機端到端測試，可另寫一個**獨立的**小靜態伺服器（不要加回 Worker 路由，否則「Worker 掛掉仍可讀」的性質會消失） | 已記錄（TDD 的「未執行或受阻」第 2 點） |
| A-6 | CDN 快取未驗證 | advisory（**未執行**） | `Cache-Control` 只是回應值；實際 CDN 是否遵守、`stale-while-revalidate` 的行為、以及部署後的標頭都無法驗證（無帳號／網域） | 部署後以 `curl -I` 檢查兩個端點的標頭與 CDN 快取狀態（TASK-037） | 待辦（DELIVERY 明列） |
| A-7 | catalog 商品清單的代表性 | advisory | 快照的八個商品是示範資料（四個來源各兩檔，台股四檔）；這不是「完整目錄」 | 發行時由 catalog 產生流程填入實際清單；`validateCatalog` 已確保來源與商品對得上 | 已記錄（`catalog.json` 的內容會被發行流程取代） |
| A-8 | 流程記載 | advisory（非程式） | 第一版把 `sources` 的選填鍵當成必填（4 個測試失敗）；`source_id` 存在性檢查原本有「來源集合非空才檢查」的守衛，會在來源清單壞掉時安靜跳過 | 已修正並如實記載（TDD 的「如實記載」第 1、2 點）；兩個修正都補了對應的負例測試 | **已記載** |

## 修正與重審

- 第 1 輪 Spec Review：AC-061 的五項宣稱逐條符合（十鍵 manifest、catalog 契約、可快取、不依賴 Worker、版本同源），並以跨語言測試補強「客戶端讀得進去」。
- 第 1 輪品質 Review 修正 2 處：鍵檢查改為「必填＋選填」兩組（與客戶端載入器相容）；`source_id` 存在性檢查拿掉「來源集合非空」的守衛（不再安靜跳過）。
- 依變異檢查：**32 個變異全數被抓到，第一階段沒有存活者**；跨語言的兩個變異由 Node 與 Python 兩邊各自失敗。
- 重審：重跑 `node --test`（**54 passed**）、Python 單檔（`5 passed`）與全套（**971 passed**）、兩個流程驗證器（exit 0），並在凍結版重跑變異矩陣（**32／32 偵測到，0 存活、0 無效**）；重讀 `static.js` 的每一條檢查與兩個回應分支、兩份快照的每一個欄位、`wrangler.toml` 的新增區塊。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-061 逐條符合）
- 品質 Review：passed（無 blocking；A-1 為發行前必做，A-2／A-3／A-6 交後續，A-4／A-5 為已記錄的刻意選擇，A-7／A-8 已記錄）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（快照佔位值必須在發行時取代）、A-2（三處版本的發行流程應同源）、A-3（部署方式未定案）、A-6（部署後才能驗 CDN 標頭）、A-7（目錄內容由發行流程產生）、A-8（已記載）
- 能否標為 done：**可以**
- 限制與未驗證事項：部署與 CDN 快取未驗證（未執行任何部署指令）；兩個端點未被真的以 HTTP 提供（純函式＋快照，端到端屬 TASK-037）；manifest 的 `url`／`sha256`／`size` 只做 schema 驗證、不下載不校驗；快照內容為佔位值；`catalog_version` 在 manifest／catalog／`wrangler.toml` 三處需由發行流程保持同源
