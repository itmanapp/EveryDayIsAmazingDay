# TASK-017 測試紀錄

- task_id：TASK-017
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-catalog sha256:bd49d41006475ccf8e0d8313fb8f9a425f0f9cc036bac8ceaa34dac371302428
- alternative_reason：無（版本比對、下載次數與原子取代皆可以假 HTTP 客戶端與真實檔案系統完整驗證）
- Task／Spec 版本：TASK-017 / SPEC-001 v0.4
- 測試邊界：`load_catalog`／`save_catalog`／`catalog_version` 對檔案的往返效果，以及 `update_catalog(...)` 的請求次數、回傳狀態、狀態容器與本地檔內容（含位元組比對）。HTTP 一律注入假客戶端，全程離線。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-016 的交付物，全套 **475 passed**（本張完成後為 519 passed）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。
- TDD 不適用的理由與替代驗證（若有）：不適用。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/markets/catalog.py` | `0b2aa3ad` | 新增：`Catalog`、`CatalogSource`、`UpdateResult`、`load_catalog`、`save_catalog`、`catalog_version`、`update_catalog` |
| `ediaad/markets/__init__.py` | `da15bd6e` | 修改：匯出 `catalog` |
| `tests/test_markets_catalog.py` | `ab2cdbf4` | 新增：44 個測試 |

## Cycle 1：`Catalog` 結構與檔案往返（AC-038，真實 Red → Green）

- 測試：`save_catalog`／`load_catalog` 完全往返（含 `Instrument` 的來源與名稱）；載入後可解析出來源中介資料（`id`／`display_name`／`supported_intervals`／`needs_api_key`）與商品；寫出的 JSON 只有三個頂層鍵；原子寫入不留暫存檔、可建立父目錄、可覆寫既有檔；`catalog_version` 接受 `Catalog` 或路徑；**缺檔時 `catalog_version` 回 `None`（首次安裝的正常狀態）**；`load_catalog` 對缺檔丟 `DataFormatError`（與 `data.load_csv` 的既有慣例一致）；十一種壞 payload（損毀 JSON、不是物件、缺版本、版本格式錯、版本非字串、`sources`／`instruments` 不是陣列、來源缺 `id`、商品缺 `symbol`、商品或頂層含未知鍵）各自可讀錯誤；`Catalog` 建構時就驗證版本格式；frozen 且可雜湊，共 22 個（其中 11 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_markets_catalog.py -q` | 1 | `22 failed`：`ModuleNotFoundError: No module named 'ediaad.markets.catalog'` | 尚未有模組／2026-09-24 |
| Green | 同上 | 0 | `22 passed in 0.38s` | snap-2026-09-24-ocaievo-catalog／2026-09-24 |

- 實作：`_require_version`（`YYYY-MM-DD`，`Catalog.__post_init__` 與 manifest 共用同一個驗證）、`CatalogSource`／`Catalog`（frozen；`sources` 用 `CatalogSource`、`instruments` **重用 `markets.base.Instrument`**）、`_catalog_to_payload`／`_catalog_from_payload`（嚴格：未知鍵一律擋下，與 `load_config` 的既有風格一致）、`load_catalog`（缺檔與內容不合法皆 `DataFormatError`）、`save_catalog`（暫存檔 ＋ `os.replace`，失敗時清除暫存檔）、`catalog_version`（`Catalog` → 版本；路徑 → 讀檔；**缺檔 → `None`**）。
- **`instruments` 重用 `Instrument` 是刻意的**：catalog 因此是「哪個商品該問哪個來源」的權威對照（`source_id` 就在商品上），而這正是 TASK-013／015／016 那條跨 Task 缺口所需要的東西。

## Cycle 2：版本比對、下載與原子取代（**既有覆蓋**，無真實 Red）

- 測試：遠端較新 → 狀態 `updated`、請求 1 次、URL 正確、本地版本更新、不留暫存檔；**manifest 版本相同 → 請求 0 次、本地檔位元不變**；manifest 版本較舊 → 狀態 `local-newer`、不降版、位元不變；manifest 未給版本時以下載到的內容比對（相同 → `current` 且**不重寫**、較舊 → `local-newer`）；首次安裝 → `installed` 並建立檔案；本地檔損毀 → 視為需要下載並在訊息留下損毀說明；三種下載失敗（連線錯誤、非 200、來源錯誤）→ `failed`、位元不變、原檔仍可載入、不留暫存檔；五種畸形下載 → 同上；目錄不可寫 → `failed` 且原檔無損；狀態容器被更新且不清掉其他鍵；非法 manifest 版本 → `DataFormatError` 且不發出請求，共 21 個（其中 12 個參數化）。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | — | — | **未取得**（見下） | — |
| Green | 同上 | 0 | `43 passed in 0.45s` | 同上／2026-09-24 |

- **如實記載的流程偏差**：`update_catalog` 在 Cycle 1 就隨模組一次寫成，因此 Cycle 2 的測試首次執行即通過，**沒有真實 Red**。這是本專案近幾張反覆出現的順序瑕疵（TASK-013 Cycle 2／3、TASK-015 Cycle 2 同型）。補救方式：把 `update_catalog` 暫時還原為 `raise NotImplementedError` 的 stub，取得**綁定證據**——`21 failed, 22 passed`（失敗數正好等於呼叫 `update_catalog` 的 21 個測試，Cycle 1 的 22 個不受影響），之後還原實作並確認雜湊一致。
- **`remote_version` 參數的存在理由**：manifest 同時提供 `catalog_version` 與 `catalog_url`（報告第 6.5 節），因此**版本相同時連請求都不用發**——比「下載後才發現版本相同」更省，也更符合「更新檢查不得阻塞主要流程」。未提供時才以下載到的內容比對（此時 `requests == 1` 是預期的）。
- **失敗一律回報狀態而不丟例外**：更新檢查屬於背景維護（六條架構約束的「失敗靜默」屬 TASK-032），因此下載失敗不得讓服務失敗；本地檔在失敗時**位元不變**且仍可 `load_catalog`（兩種失敗情境各有斷言）。

## Cycle 3（補測）：兩個問題同時存在時的訊息

- 發現一個未覆蓋的組合：**本地檔損毀且下載也失敗**時，原本的訊息只會提到下載失敗，使用者可能修好了網路卻不知道本地檔也要處理。新增 `_combine` 讓訊息同時包含兩者，並補測試斷言「訊息同時提到本地 JSON 損毀與下載失敗」且「損毀的原檔不得被刪除或改寫」。
- 測試數 43 → 44。這是由**狀態空間檢查**（而不是變異檢查）發現的缺口。

## 變異檢查（證明測試有辨識力）

| 變異 | 植入內容 | 實際結果 |
| --- | --- | --- |
| M1 | 版本比較用 `>=`（相同也下載） | 被抓到 |
| M2 | 版本比較反向 | 被抓到 |
| M3 | 忽略 manifest 版本（一律下載） | 被抓到 |
| M4 | `installed`／`updated` 狀態互換 | 被抓到 |
| M5 | 下載失敗時回報 `updated` | 被抓到 |
| M6 | 內容不合法時直接往外丟 | 被抓到 |
| M7 | 失敗時仍把目前版本寫回本地 | 被抓到 |
| M8 | 狀態容器被清空 | 被抓到 |
| M9 | 狀態不記錄版本 | 被抓到 |
| M10 | 非原子寫入（`copy`，留下暫存檔） | 被抓到 |
| M11 | `load_catalog` 不擋未知鍵 | 被抓到 |
| M12 | 版本不驗證日期格式 | 被抓到 |
| M13 | 商品的來源與名稱不寫進 payload | 被抓到 |
| M14 | 缺檔時回空 catalog | 被抓到 |
| M15 | 缺檔時 `catalog_version` 丟錯 | 被抓到 |
| M16 | `updated` 時回報舊版本 | 被抓到 |
| M17 | `save_catalog` 不建父目錄 | 被抓到 |
| M18 | 非法 manifest 版本改丟 `ConfigError` | 被抓到 |

工具紀律：整行比對、`count(frm) == 1` 才執行、每次變異後立即還原並比對檔案 sha256。**本輪踩到一次工具陷阱**：我為了修 `_combine` 而改了訊息字串，M5／M6 的變異字串因此變成 `count == 0`，腳本把它們列為 `SURVIVORS`；我沒有直接接受這個結果，而是回頭確認輸出後發現是 `[SKIP]`（字串已不符），更新變異字串後兩者都被抓到。矩陣在**最終版檔案**上重跑過（另移除兩個未使用的匯入之後），18／18 全數被抓到；還原後 `ediaad/markets/catalog.py` `0b2aa3ad` 與變異前一致，單檔 `44 passed`。

## 回歸與 Review 後驗證

| 原因／檢查 | 命令與工作目錄 | 結果／exit | 版本／證據位置 |
| --- | --- | --- | --- |
| 本張單檔 | `ocaievo/`：`.venv/bin/python -m pytest tests/test_markets_catalog.py -q` | 0（`44 passed in 0.41s`） | snap-2026-09-24-ocaievo-catalog |
| 相關回歸（registry＋Twelve Data） | `ocaievo/`：`.venv/bin/python -m pytest tests/test_markets_base.py tests/test_markets_twelvedata.py -q` | 0（`105 passed in 0.57s`） | 同上 |
| 全套回歸 | `ocaievo/`：`.venv/bin/python -m pytest -q` | 0（`519 passed in 19.13s`） | 同上 |
| 綁定 Red（`update_catalog` 還原為 stub） | `ocaievo/`：把 `update_catalog` 第一行改為 `raise NotImplementedError` 後跑本張單檔 | 1（`21 failed, 22 passed`） | 同上 |
| 未使用匯入掃描 | `ocaievo/`：AST 粗檢 `ediaad/` | 0（先抓到 `field`／`SourceError` 兩個未使用匯入並移除） | 同上 |
| 變異後還原驗證 | 同本張單檔與全套 | 0，檔案雜湊與變異前一致 | 同上 |

## 未執行或受阻

- 無未執行的必要檢查。
- 已知邊界（記錄）：
  - **不做排程與六條架構約束**（5 秒逾時、不阻塞啟動與輪詢、失敗靜默、先回快取、5 分鐘去抖動、可完全關閉）——那是 TASK-032；本張只提供可被它呼叫的同步函式與狀態回報。逾時由預設客戶端的 `HTTP_TIMEOUT = 5.0` 承擔。
  - **不做端點**：`GET /v1/latest` 與 `/catalog.json` 屬 TASK-034；本張只消費 manifest 提供的 `catalog_url`／`catalog_version`。因此「非 200」的判斷落在客戶端（`urllib` 對 4xx／5xx 丟例外 → 狀態 `failed`），測試以會丟例外的假客戶端覆蓋。
  - **未與真實更新服務對接**（`EDIAAD_UPDATE_URL` 為佔位；Q-011 假設無 Cloudflare 帳號）。真實 manifest 的欄位名以報告第 6.5 節為依據。
  - `state` 容器的形狀（`state["catalog"] = {status, version, message}`）是本張定義的介面，供 TASK-025 的系統狀態頁與 TASK-032 的排程讀取；已於 Review 標為需追認的設計決定（A-2）。
  - **`update_catalog` 的 `remote_version` 是選填**：未提供時一定發出一次請求。TASK-032／034 應確保 manifest 一定帶 `catalog_version`，才能完全享有「版本相同不請求」。
  - **catalog 尚無消費端**：`Catalog`／`load_catalog` 目前沒有呼叫端，`monitor.load_config` 也還沒用 catalog 決定商品的來源。這是 TASK-013 A-1 那條跨 Task 缺口的同一條線（見 Review A-1），catalog 正是解它所需要的權威對照。
- 未涵蓋：SQLite（TASK-018）、設定與原子寫入（TASK-019）、網頁（TASK-020 之後）、更新排程（TASK-032）、更新端點（TASK-034）。
