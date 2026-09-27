# TASK-029：純 Python Ed25519 驗章（RFC 8032 向量）

- id：TASK-029
- type：feature
- status：done
- spec_version：SPEC-001 v0.4
- ac_ids：["AC-054"]
- depends_on：["TASK-001"]
- test_evidence：["docs/workflow/tdd/TASK-029.md"]
- review_evidence：["docs/workflow/reviews/TASK-029.md"]
- blocked_from／阻塞原因／恢復條件：無

## 交付與邊界

- 本張完成後可驗證的行為：`ediaad/license.py` 提供純 Python 的 `ed25519_verify(public_key, message, signature) -> bool`；對 RFC 8032 第 7.1 節官方測試向量的五組輸入全部回傳 `True`，對任何被改動的訊息、簽章或公鑰回傳 `False` 且不拋出例外；`.venv` 內 `importlib.util.find_spec("cryptography")` 為 `None`，`requirements.txt`／`requirements-dev.txt` 不含 `cryptography`；模組可被 import 而不觸碰檔案、網路或時鐘。
- 本張不做：不建立 `Lease` 模型與機器指紋（TASK-028）；不做啟用、離線啟動驗證與時鐘防護（TASK-030）；不做續期、到期停止與功能分級（TASK-031）；**不簽章、不持有私鑰**（簽章在 Cloudflare Worker 以 WebCrypto 執行，見 TASK-033）；不引入 `cryptography` 或任何第三方依賴；不做 CLI 子命令（TASK-036）。
- 每個 AC 在本張負責的範圍：AC-054 全部（RFC 8032 官方向量全數通過、實作為純 Python、`.venv` 不含 `cryptography` 依賴）。租約層級的驗章整合（簽章＋指紋＋到期）屬 AC-053，由 TASK-030 負責，本張只交付可獨立驗證的驗章函式與內嵌公鑰。

## 接手上下文

- 路徑慣例：本張的實作檔案路徑相對 `ocaievo/`（例如 `ediaad/data.py` 指 `ocaievo/ediaad/data.py`）；工作文件與證據路徑（`docs/workflow/…`）相對專案根。執行指令的工作目錄為 `ocaievo/`。
- Spec／相關 ADR／既有規範：`docs/workflow/SPEC.md` AC-054、第 5 節「模組責任與邊界」原則 1（計算不碰 I/O）與模組表 `ediaad/license.py` 的對外 API `ed25519_verify`、第 6 節安全（租約以 Ed25519 簽章保護到期日與指紋）；`docs/workflow/adr/ADR-002.md`（授權驗章採純 Python Ed25519，不引入 `cryptography`；不得自行發明曲線運算，需依 RFC 8032 參考流程；約 100～150 行、屬安全敏感程式碼，必須有向量測試與 Review）；`docs/architecture/ENGINEERING-REPORT.md` 第 6.4 節「Ed25519 驗章：純 Python」（`hashlib.sha512` ＋ 任意精度整數；2000 次模逆 0.206 秒；測試依據為 RFC 8032 官方向量；Worker 用 WebCrypto 簽、客戶端用純 Python 驗）；`docs/workflow/PROJECT.md` 環境實測表（系統 `cryptography` 41.0.7 **不使用**）與第 2.12 節（客戶端以內嵌公鑰驗證）。正確性 oracle 為 RFC 8032 第 7.1 節「Test Vectors for Ed25519」（TEST 1、TEST 2、TEST 3、TEST 1024、TEST SHA(abc)），以常數內嵌測試檔，測試不需網路。
- 模組與公開介面：`ediaad/license.py`（本張首次建立）新增 `ed25519_verify(public_key: bytes, message: bytes, signature: bytes) -> bool`（長度或格式不合法一律回 `False`，不丟 `EdiaadError`；錯誤階層沿用 `ediaad/errors.py`）；模組常數 `LICENSE_PUBLIC_KEY`（內嵌的 32 bytes Ed25519 公鑰，供 TASK-030 驗租約）。內部 Ed25519 群運算（`p = 2**255 - 19`、`L`、`_recover_x`、`_point_add`、`_scalar_mult`、SHA-512 展開）為私有實作，不列入公開契約。上述新名稱為本張依 SPEC 模組表提案，**實作前重新查證**命名與簽章是否與既有 API 一致。
- 預計觸及的檔案：`ediaad/license.py`、`tests/test_license_ed25519.py`；必要時 `tests/conftest.py`（共用向量 fixture）；實作前重新查證。
- 必要環境／依賴：Python 3.12.3 的 `.venv`＋`pytest`；僅標準庫 `hashlib` 與任意精度整數運算；不得 import 或安裝 `cryptography`（系統雖已安裝 41.0.7，`PROJECT.md` 明訂不用）；全程離線，不需要環境變數。

## 測試計畫

- 測試公開邊界：單元測試只呼叫 `ediaad.license.ed25519_verify`，輸入為 RFC 8032 第 7.1 節向量的（公鑰, 訊息, 簽章）三元組；不觸及檔案、網路、時鐘與其他模組。
- 第一個失敗行為與預期斷言：`ediaad/license.py` 尚未存在時，`import ediaad.license` 丟 `ModuleNotFoundError`（或 `ed25519_verify` 不存在時丟 `AttributeError`）；首案 `test_rfc8032_test1_empty_message` 斷言 `ed25519_verify(TEST1_PK, b"", TEST1_SIG) is True`，實作錯誤時得到 `False` 而非例外。
- 後續例外／邊界情境：（1）簽章篡改一位元、訊息篡改一位元、公鑰篡改一位元，三種都必須回 `False`；（2）非正規編碼（`s ≥ L`、`R`／`A` 未正規化）時回 `False`，不得接受可延展（malleable）簽章；（3）長度不是 32／64 bytes（空公鑰、截斷簽章）、型別非 bytes（`str`、`None`）皆回 `False` 且不拋例外；（4）`A` 為小階點／identity、`R`／`S` 為全零時回 `False`；（5）RFC 8032 第 7.1 節五組向量中，對同一公鑰但換成另一組向量的訊息與簽章必須回 `False`（交叉負例）。
- 單項及相關回歸的實際命令／工作目錄：專案根執行 `.venv/bin/python -m pytest tests/test_license_ed25519.py -q`；回歸 `.venv/bin/python -m pytest -q`；沿用 `docs/workflow/PROJECT.md` 的指令表。
- 非程式任務的替代驗證與理由：不適用，本張有可先寫的行為 Red（驗章函式對官方向量的行為）。
- 必要的人工檢查：無視覺或平台相依項目；另以 `.venv/bin/python -c "import importlib.util; print(importlib.util.find_spec('cryptography'))"` 人工確認輸出為 `None`，並以 `grep -n cryptography requirements.txt requirements-dev.txt` 確認無此依賴（此為 AC-054「`.venv` 不含 `cryptography`」的直接證據）。

## 完成條件

- [x] 本張 AC 行為完成，符合目前 Spec 版本
- [x] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [x] Spec 與品質 Review 完成，blocking 問題歸零
- [x] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：基準 `docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）。開工前 `ocaievo/` 已有 TASK-001～TASK-028 的交付物（全套 **814 passed**），檔案樹 sha256 `0c378a8ba64fa1a99b86a10b6489a1ce19e50accfaf157dcb530f21b8e8a9e38`（81 檔）；本次修改 `ediaad/license.py`（新增 Ed25519 驗章與 `LICENSE_PUBLIC_KEY`）並新增 `tests/test_license_ed25519.py`（逐檔 sha256 見 Review 紀錄；本專案未初始化 Git）
- TDD 紀錄位置：見上方 test_evidence（`docs/workflow/tdd/TASK-029.md`）
- Review 紀錄位置：見上方 review_evidence（`docs/workflow/reviews/TASK-029.md`）
- 目前被驗證版本／檔案狀態：`snap-2026-09-24-ocaievo-ed25519` sha256:a6503eb5e87fa310bb305ed3a9f96d10deedeb7d320ad8a8a58020bf765178f6（原始碼樹，82 檔）；`ediaad/license.py` `4ba247f6…`、`tests/test_license_ed25519.py` `1c8343ae…`；全套 **836 passed**；變異矩陣 24 個（22 偵測到、2 等價）；AC-054 直接檢查：`.venv` 內 `cryptography` 為 `None`、requirements 兩檔皆不含
- 取消、重開或變更原因：無
