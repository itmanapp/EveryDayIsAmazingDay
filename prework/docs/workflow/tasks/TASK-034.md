# TASK-034：靜態 manifest 與 catalog 端點

- id：TASK-034
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-061"]
- depends_on：["TASK-033"]
- test_evidence：["docs/workflow/tdd/TASK-034.md"]
- review_evidence：["docs/workflow/reviews/TASK-034.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`GET /v1/latest` 回傳凍結 schema 的 manifest，鍵集合恰為 `schema`、`version`、`released_at`、`min_supported`、`notes`、`catalog_version`、`catalog_url`、`url`、`sha256`、`size`（不得多、不得缺）；`GET /catalog.json` 回傳 catalog 且其 `catalog_version` 與 manifest 的 `catalog_version` 來自同一快照；兩者回應都帶可快取標頭且**不依賴 Worker 是否可用**——純靜態回應函式不查 D1、不呼叫 `handleActivate`／`handleRenew`、不需要 `env` 的任何綁定即可產生回應。
- 本張不做：不部署到 Cloudflare Pages／R2、不設定或使用真實網域、不做版本檔下載或上傳、不實作客戶端 catalog 版本比對與原子取代（TASK-017）、不做 Worker activate／renew API（TASK-033）、不做後台與重新申請頁（TASK-035）、不做版本頁 UI（TASK-025）。
- 每個 AC 在本張負責的範圍：AC-061 全部（manifest 與 catalog 的凍結 schema、可快取性、不依賴 Worker 可用性）。manifest 欄位中的 `url`／`sha256`／`size` 在本張只作為 schema 欄位被驗證，不下載、不校驗檔案；實際更新檢查的六條約束屬 AC-059（TASK-032）。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-061、第 5 節模組表、第 7 節測試策略列、第 2 節 out of scope（不部署）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.5 節（manifest schema 全文：「分成兩個端點的理由：manifest 是靜態可快取的，`renew` 是動態的；Worker 掛掉時 manifest 仍可讀」）、第 6.1 節元件圖（Pages/R2 提供 `GET /v1/latest` 與 `GET /catalog.json`）；`docs/workflow/PROJECT.md` 授權範圍（部署一律未授權）與環境實測表（無帳號／網域／D1）。
- 模組與公開介面：`cloudflare/static/latest.json`、`cloudflare/static/catalog.json`（凍結 schema 的樣本內容，版本與日期使用佔位值）；`cloudflare/worker/src/static.js` 提供 `validateManifest(obj) -> string[]`（回空陣列代表合法）、`validateCatalog(obj) -> string[]`、`manifestResponse(manifest) -> {status, headers, body}`、`catalogResponse(catalog) -> {status, headers, body}`；`cloudflare/wrangler.toml` 以註解記錄 `<佔位網域>` 的路由對照（不填入真實網域）。
- 預計觸及的檔案：`cloudflare/static/latest.json`、`cloudflare/static/catalog.json`、`cloudflare/worker/src/static.js`、`cloudflare/test/static.test.mjs`、`cloudflare/wrangler.toml`；實作前重新查證路徑是否與 TASK-033 的 `router.js` 及部署方式一致。
- 必要環境／依賴：Node v24.21.0，工作目錄 `cloudflare/` 執行 `node --test`；以 `node:fs` 讀取兩個 JSON 檔；不需網路、不需 `wrangler`、不需 D1 綁定。

## 測試計畫

- 測試公開邊界：對 `validateManifest`／`validateCatalog`／`manifestResponse`／`catalogResponse` 直接呼叫；靜態 JSON 以 `node:fs` 讀入後餵入驗證函式與回應函式；不啟動伺服器、不發出任何請求。
- 第一個失敗行為與預期斷言：`cloudflare/static/latest.json` 尚未存在時讀檔丟 `ENOENT`；首案 `test_manifest_is_frozen_schema` 斷言檔案可解析、鍵集合恰為上述十個鍵、`size` 為整數、`sha256` 為 64 位十六進位、`released_at` 為 ISO 8601 UTC 字串。
- 後續例外／邊界情境：
  1. 缺鍵／多鍵／型別錯（`size` 為字串、`sha256` 長度錯誤、`notes` 非字串）→ `validateManifest` 回非空錯誤清單，訊息指出欄位名。
  2. 快取性：`manifestResponse(...).headers["Cache-Control"]` 同時含 `public` 與 `max-age`；`catalogResponse` 同理。
  3. 不依賴 Worker：以**沒有任何 D1 綁定**的空 `env`（或省略 `env`）呼叫兩個回應函式仍成功，且測試以計數假物件斷言未呼叫 `handleActivate`／`handleRenew`／任何 `db.prepare`。
  4. 版本一致性：manifest 的 `catalog_version` 與 `catalog.json` 的 `catalog_version` 相同；刻意讓兩者不同時測試必須失敗（避免快照錯位）。
  5. 佔位網域：`catalog_url`／`url` 使用 `<佔位網域>` 時仍通過 schema 驗證；測試中不出現真實網域，也不發出真實網路請求。
  6. catalog 的 `sources` 與 `instruments` 結構符合 SPEC 第 5 節 `Catalog` 契約（`catalog_version`、`sources`、`instruments`）。
- 單項及相關回歸的實際命令／工作目錄：`cloudflare/` 下執行 `node --test`（單檔 `node --test test/static.test.mjs`）；全套回歸入口為 TASK-037；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用。須誠實標示：部署後的實際 HTTP 標頭、CDN 快取與真網域路由無法驗證（無帳號／網域／部署授權），由 TASK-037 的 DELIVERY 明列為未驗證。
- 必要的人工檢查：人工複核 `cloudflare/static/*.json` 與 `wrangler.toml` 不含真實網域或資源識別碼，且未執行任何部署指令。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-033 與 TASK-025 的交付物（Python 全套 **966 passed**、Node **42 passed**），檔案樹 sha256 `729d545795e5a2158bcd15cfaa77f3a6189b73e50d1206b45e95fbdc40cec362`（110 檔，即 TASK-033 的 `checked_version`；`cloudflare/static/` 尚不存在）。本次新增 `cloudflare/static/latest.json`／`catalog.json`、`cloudflare/worker/src/static.js`、`cloudflare/test/static.test.mjs` 與 `tests/test_static_snapshot.py`，並修改 `cloudflare/wrangler.toml`（靜態端點對照與部署前檢查指令）（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-034.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-034.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-static-snapshot` sha256:2b1d1b16deec9d682570dd12603643f048129e431b39d8bf2bb78d1de0678a65（原始碼樹，115 檔）；`cloudflare/static/latest.json` `9751e3b4…`、`catalog.json` `11efdf95…`、`worker/src/static.js` `67ab011c…`、`test/static.test.mjs` `bfc00af9…`、`wrangler.toml` `bcfc6036…`、`tests/test_static_snapshot.py` `c8acadcd…`；Node `node --test` **54 passed**（52 個測試案例）、Python 全套 **971 passed**；變異矩陣 32 個 → **32 偵測到**（0 存活、0 無效）
- 取消、重開或變更原因：無（第 1 輪 Review 修正鍵檢查的必填／選填與 `source_id` 檢查的守衛）
