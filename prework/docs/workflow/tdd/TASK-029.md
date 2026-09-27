# TASK-029 測試紀錄

- task_id：TASK-029
- verification：tdd
- result：passed
- checked_version：snap-2026-09-24-ocaievo-ed25519 sha256:a6503eb5e87fa310bb305ed3a9f96d10deedeb7d320ad8a8a58020bf765178f6
- alternative_reason：不適用（純函式：RFC 8032 官方測試向量離線內嵌，篡改與非正規輸入的行為可完全自動驗證；`cryptography` 不在 `.venv` 內也以 `importlib.util.find_spec` 直接證明）。
- Task／Spec 版本：TASK-029 / SPEC-001 v0.4
- 測試邊界：只呼叫 `ediaad.license.ed25519_verify`（以及為固定安全規則而測的內部解碼／群運算函式）；輸入為 RFC 8032 第 7.1 節的五組向量與刻意構造的惡意輸入；不觸及檔案、網路、時鐘與其他模組。
- 基線結果：開工前 `ocaievo/` 已有 TASK-001～TASK-028 的交付物，全套 **814 passed**（本張完成後為 **836 passed**）；基準快照 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`），開工前檔案樹 sha256 `0c378a8ba64fa1a99b86a10b6489a1ce19e50accfaf157dcb530f21b8e8a9e38`（81 個檔案）。
- TDD 不適用的理由與替代驗證（若有）：無。

工作目錄一律為 `ocaievo/`，命令一律為 `.venv/bin/python -m pytest …`。

## 交付檔案

| 檔案 | sha256（前 8 碼） | 說明 |
| --- | --- | --- |
| `ediaad/license.py` | `4ba247f6` | 修改：新增 `_P`／`_L`／`_D`／`_I`／`_IDENTITY`、`_recover_x`／`_decompress`／`_point_add`／`_scalar_mult`／`_point_equal`／`_is_small_order`、`_BASE`、`LICENSE_PUBLIC_KEY`（fail-closed 佔位）與 `ed25519_verify` |
| `tests/test_license_ed25519.py` | `1c8343ae` | 新增：22 個測試（向量 5 ＋ 交叉負例 1 ＋ 嚴格性 7 ＋ 內部規則 3 ＋ 純標準庫 4 ＋ 效能 1 ＋ 佔位 1） |

## Cycle 1：純 Python Ed25519 驗章（AC-054，真實 Red → Green）

- **測試向量先被獨立交叉核對過**（見下方「證據的來源」），才寫進測試檔。
- 測試（22 個）：
  - **官方向量**：TEST 1（空訊息）、TEST 2、TEST 3、TEST 1024、TEST SHA(abc) 五組全部 `True`（參數化）；同一公鑰配上**另一組**向量的訊息與簽章全部 `False`（交叉負例，避免「什麼都回 True」）。
  - **嚴格性**：訊息／簽章／公鑰各翻一個位元、訊息尾端多一個 byte → `False`；`S >= L`（`L`、`L+1`、`2L`）的可延展簽章 → `False`；非正規點編碼（`y >= p`、`x = 0` 卻帶 sign bit）→ `False`；8 個小階點編碼與 identity → `False`；長度不是 32／64、型別是 `str`／`None`／整數／清單／物件 → `False`（bytes-like 的 `bytearray`／`memoryview` 視為同一種輸入並通過）；40 組隨機輸入與 20 組雜訊簽章**從不拋出例外**。
  - **兩個具體偽造**（本張最重要的負例）：`A = identity`、`R = identity`、`S = 0`（群等式成立）；以及**通用偽造** `A = identity` 時 `[k]A` 恆為 identity，攻擊者取 `R = [S]B`（`S = 1`、`R` = 基底點）即對**任意訊息**滿足群等式——兩者都必須靠小階點檢查擋下。
  - **內部安全規則**（公開 API 無法構造這些輸入）：`_recover_x` 對 `y >= p` 與「`x = 0` 帶 sign bit」回 `None`；`_decompress` 對長度不是 32 回 `None`（用「31 bytes 的 identity」這種本身是合法點的輸入，長度檢查必須先擋）；`_point_equal` **必須比兩個座標**（只比 X 會把 `P` 與「同 X、Y 相反」的點視為相等）；`_is_small_order` 對 identity／全零編碼為 `True`、對基底點為 `False`。
  - **純標準庫**：`.venv` 內 `find_spec("cryptography") is None`；`requirements.txt`／`requirements-dev.txt` 不含 `cryptography`；在**子程序**中 import 本模組不得拉進 `socket`／`ssl`／`http`／`cryptography`／`requests`（`pathlib` 在 CPython 3.12 會拉進 `urllib.parse`，那是純字串解析、沒有 I/O，已排除在檢查之外並在註解說明）。
  - **效能**：TEST 1024 一次驗章必須遠低於 1 秒（實測 **3.8 ms**）。
  - **`LICENSE_PUBLIC_KEY`**：32 bytes 且目前是全零佔位（TASK-033 產生 Worker 金鑰後才填入），用它在任何輸入上都驗不過——**fail closed**，未產生金鑰的組建不可能接受任何租約。

| 階段 | 命令 | exit | 關鍵輸出 | 版本／日期 |
| --- | --- | --- | --- | --- |
| Red | `.venv/bin/python -m pytest tests/test_license_ed25519.py -q` | 2 | collection error：`ImportError: cannot import name 'LICENSE_PUBLIC_KEY'` | 尚未有驗章／2026-09-24 |
| Green | 同上 | 0 | `22 passed in 0.33s` | snap-2026-09-24-ocaievo-ed25519／2026-09-24 |

- 實作：依 RFC 8032 第 5.1 節的參考流程（`_recover_x` 對應 5.1.3、`_point_add` 對應 5.1.4、`_scalar_mult` 對應 5.1.5、`ed25519_verify` 對應 5.1.7），只用 `hashlib` 與任意精度整數（ADR-002：不引入 `cryptography`、不自行發明曲線運算）。
- **只驗章、不簽章**：簽章在 Cloudflare Worker 以 WebCrypto 執行（TASK-033），客戶端不持有私鑰；`LICENSE_PUBLIC_KEY` 以 fail-closed 佔位值提供，TASK-030 才會真正使用它。
- **嚴格性不是裝飾**：`S >= L` 是可延展簽章；小階點／identity 會讓「零簽章」或「通用偽造」通過群等式。這三條規則各有具體測試，且都是變異矩陣的偵測點。

## 證據的來源（為什麼可以相信內嵌的向量）

官方向量是**常數**，抄錯一個字元就會變成「測試與實作一起錯」。因此在寫測試之前，先用系統既有的獨立實作（`cryptography` 41.0.7，**只作為編寫測試時的交叉核對工具，不進入 `.venv`、不成為專案依賴**）核對每一組：

1. 由 RFC 的 secret key 推導出的 public key 必須等於內嵌的 public key（TEST 1／2／3／1024／SHA(abc) 全部相符）。
2. 內嵌的簽章必須在內嵌的訊息上通過驗證（TEST 1／2／3／1024 全部通過）。
3. `TEST SHA(abc)` 的簽章第一版抄錯（後 32 bytes 有誤），由第 2 步發現；Ed25519 簽章是**決定性的**，因此以同一把 secret key 重算即得正確值：`...09351fc9ac90b3ecfdfbc7c66431e030` ＋ `3dca179c138ac17ad9bef1177331a704`（訊息為 `sha512("abc")`，也由 `hashlib` 直接確認）。

這一步讓「官方向量」不只是聲稱，而是**在寫測試之前就被外部實作確認過**。

## 變異測試（兩階段：先殺存活者，再跑凍結版）

- 工具：`/tmp/mutate_task029.py`（整行替換、`count(frm) == 1` 才套用、逾時 180 秒、跑完立即還原並比對 sha256、`flock` 確保單一行程）。
- 矩陣：**24 個變異**（全部在 `ediaad/license.py`），涵蓋非正規編碼、`x = 0` 的 sign bit、開平方的第二個根、sign bit 與 y 的還原、extended 座標加法的四個分量、純量乘法的分支與加倍、點相等的兩個座標、小階點判定、曲線常數 `d`／群階 `L`／基底點 `y`、型別與長度守門、A／R 的小階點檢查、`S >= L`、挑戰值的雜湊輸入、群等式。
- **第一階段抓到 6 個真實存活者，全部補強測試擊殺**：
  1. `E01`／`E02`（`y >= p` 與「`x = 0` 帶 sign bit」）——公開 API 無法構造「`y >= p` 且非小階」的輸入（需要一個 `y < 19` 的真實金鑰），原本被小階點檢查掩蓋 → 新增**解碼層**測試。
  2. `E05`（`_decompress` 的長度檢查）——原本的 31 bytes 輸入剛好不是合法點，於是「回 `None`」與長度檢查無關 → 改用「31 bytes 的 identity」（本身是合法點）。
  3. `E13`（`_point_equal` 只比 X）——**安全缺陷**：只比 X 會把 `P` 與「同 X、Y 相反」的點視為相等 → 新增「identity vs `(0, -1)`」的比較測試。
  4. `E14`（小階點判定）與 `E20`（A 的小階點檢查）——原本的負例都被群等式順帶擋下，檢查本身沒有被測到 → 新增**通用偽造**案例（`A = identity`、`R = [S]B`）。
- **2 個判讀為等價／刻意保留的存活者**：
  - `E17`（`_BASE_Y` 少了 `% _P`）：**等價**——後續所有運算都在模 `p` 下進行，未化簡的值會被吸收。
  - `E21`（R 的小階點檢查）：在**無共因子（cofactorless）**群等式下不可觀測（小階 R 除 `R = identity` 且 `S = k·a` 外無法滿足等式，而那需要離散對數）；**刻意保留**作為縱深防禦（libsodium 同樣拒絕小階 R，且未來若改用共因子或批次驗證就會變成真缺陷）。
- **最終凍結版結果：22／24 偵測到、2 個等價（`E17`／`E21`）、0 無效**，逐輪輸出形如 `21 passed, 1 failed`（22 個測試）。

### 工具缺陷：假的 DETECTED（`.pyc` 時效）

第一輪全量執行時 `E21` 顯示「偵測到」，但單獨重跑三次都是存活。追查後發現是**工具缺陷**：CPython 的 `.pyc` 標頭只記錄 mtime 到**秒**，而 `E20` 與 `E21` 的變異字串等長（`point_a` 與 `point_r` 同長度），於是同一秒內產生的檔案「大小相同、秒數相同」→ Python 誤用上一個變異的 bytecode，讓 `E21` 的測試跑在 `E20` 的程式碼上。已修正為在子程序加上 `PYTHONDONTWRITEBYTECODE=1`（不寫 bytecode 就沒有時效問題），重跑後 `E21` 穩定為存活，並**回頭用修正後的工具重跑 TASK-024～028 的矩陣**（結果全部不變：39／39、29／30＋1 等價、25／25、20／20）。

**另一個如實記載的操作教訓**：變異矩陣進行中不可以同時計算檔案樹雜湊。我第一次算出的樹雜湊與先前不一致，原因是矩陣正在改寫 `ediaad/match.py`（`flock` 只防止兩個矩陣同時跑，不保護讀者）。等矩陣結束、確認逐檔 sha256 回到文件記載的值之後才重新計算，才得到本紀錄的 `checked_version`。

## 迴歸與整體驗證

| 命令 | exit | 關鍵輸出 |
| --- | --- | --- |
| `.venv/bin/python -m pytest tests/test_license_ed25519.py -q` | 0 | `22 passed in 0.33s` |
| `.venv/bin/python -m pytest -q` | 0 | `836 passed, 2 warnings in 131.41s` |
| `.venv/bin/python -c "import importlib.util; print(importlib.util.find_spec('cryptography'))"` | 0 | `None`（AC-054 的直接證據） |
| `grep -c cryptography requirements.txt requirements-dev.txt` | 1 | 兩個檔案都是 `0`（`grep` 找不到所以回 1，屬預期） |
| `python3 .project-workflow/scripts/validate_workflow.py .` | 0 | 通過 |
| `python3 /tmp/check_tasks.py` | 0 | 檢查 37 個 Task 檔；SPEC AC 66 項；結果：通過 |

## 未執行或受阻

- 無。AC-054 的三項宣稱（官方向量全數通過、純 Python、`.venv` 不含 `cryptography`）都有自動或直接證據；本張沒有視覺或平台相依項目。
- 已知的**後續依賴**（不是本張的缺口）：`LICENSE_PUBLIC_KEY` 仍是全零佔位，TASK-033 產生 Worker 金鑰後才會填入真值；`ed25519_verify` 與 `Lease` 的整合（簽章 ＋ 指紋 ＋ 到期）屬 TASK-030。
