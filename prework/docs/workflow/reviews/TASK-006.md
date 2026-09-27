# TASK-006 Code Review

- task_id：TASK-006
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-outlook sha256:1f053e86d43c06c5f18e2e96251708c5bf4823d5d75b3bafa336bb2a366fac44
- Task／Spec 版本：TASK-006 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `1f053e86d43c06c5f18e2e96251708c5bf4823d5d75b3bafa336bb2a366fac44`；本張交付的兩個檔案——`ediaad/outlook.py` `afa7497019def510ef6c4dcd8aa8609925c529b022653a649579dd5dc6c424f7`、`tests/test_outlook.py` `63f243a0b579cd64449dc9a88a13c21780bbb6b6ae7ba767170b07dfa3559c31`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對；本張新增 2 檔，未修改其他模組
- 納入的已提交、未提交、新增檔案：`ediaad/outlook.py`、`tests/test_outlook.py`（本張交付物）＋ 本張 TDD／Review 紀錄
- 排除的既有修改及理由：`data.py`／`features.py`／`similarity.py`／`scan.py`／`errors.py` 與既有測試屬 TASK-001～005 交付物，本張未修改
- 程式規範來源：`docs/workflow/SPEC.md` 第 5 節（`outlook.py` 責任、`OutlookStats` 欄位、原則 1 與 3、依賴方向）、AC-012／AC-013、報告第 4.2 節（`outlook` 不匯入 `scan`）、第 5.8 節（統計定義與已知偏誤）、第 8.3 節 F-002、`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-012 | `ediaad/outlook.py`（`OutlookStats`、`forward_stats`）；`tests/test_outlook.py` 的 7 個 Cycle 1 案例 | 符合 | — |
| AC-013 | `ediaad/outlook.py`（`end_attr` 參數、`HasEndIndex`）；`tests/test_outlook.py` 的 6 個 Cycle 2 案例 | 符合（真實 `PatternEvent` 整合待 TASK-008 補） | — |

逐條核對：

- **AC-012**：5 個樣本的 `samples=5`、`up_probability=0.6`（`returns` 中的 0.0 不計入上漲）、`mean_return`／`median_return`／`std_return` 與獨立以 `statistics` 計算的值相符（`abs=1e-6` 級精度，涵蓋 `pstdev` 的母體定義）；`end + horizon == len - 1` 保留、`== len` 排除（成對斷言）；空片段清單與全被尾端排除兩種情況都得到 `samples=0` 且四個欄位皆 `None`。符合，未多做未要求行為。
- **AC-013**：同一替身同時具備 `end_index=0` 與 `recovery_index=7` 時，未指定 `end_attr` 得到 0.05（用 `end_index`）、指定 `recovery_index` 得到 0.2；兩條路線對同一組位置得到**完全相同**的 `OutlookStats`（以 dataclass 相等比較）；這正是報告 F-002 的結構性修法。符合。
- **依賴方向**：`outlook.py` 只匯入 numpy／pandas 與 `errors`，未匯入 `scan`／`patterns`／`monitor`；以 `Protocol`（`HasEndIndex`）描述輸入形狀。符合 SPEC 第 5 節與報告第 4.2 節。

## 品質 Review

- **正確性（對照報告第 5.8 節）**：`end_attr` 取值 → 尾端排除（`end + horizon >= length`）→ 報酬 `close[end+H]/close[end]-1` → `up_probability` 為**嚴格大於 0** 的比例 → 母體標準差。逐項與報告一致。未發現問題。
- **`None` 而非 0**：無樣本時四個欄位為 `None`，符合報告「0 會被誤讀為報酬為 0」。已由兩個測試（空清單、全部被尾端排除）與變異 M3 把關。未發現問題。
- **錯誤處理（本張新增的兩項守門，超出 AC 但有其必要）**：
  1. **缺結束索引欄位 → `ConfigError`**（`_end_index`）。理由是 F-002 的失敗模式正是「物件沒有預期的欄位」；裸的 `AttributeError` 會被監控迴圈當成「來源畸形資料」吞成 warning，掩蓋契約不一致。訊息同時指出兩條路線各自的欄位名，讓接手者能直接修正。
  2. **基準價格為 0 或非有限 → `ConfigError`**。理由：不擋的話會得到 `inf`／`NaN` 統計（Red 階段實際出現 `RuntimeWarning: invalid value encountered in subtract`），違反 SPEC 第 6 節可靠性與專案「退化情境不得產生 NaN」的一貫原則；相對於「靜默排除該片段」的替代方案，報錯更符合 F-003 的教訓（「沒有結果」與「無法得到結果」必須區分）。
  - 這兩項是**刻意超出 AC-012／AC-013 的最小防禦**，已在 TDD 紀錄與本表載明，供使用者覆核。
- **模組責任**：純計算、無 I/O、無訊息輸出；`OutlookStats` 為 frozen dataclass，可安全比較（測試即利用 dataclass 相等驗證兩條路線一致）。未發現問題。
- **測試品質**：oracle 為標準庫獨立計算；含成對邊界斷言（避免單側測試讓 `<`／`<=` 錯誤矇混）、零報酬的上漲判定、兩個 `None` 情境、雙路線一致與三項錯誤契約；資料確定、離線。變異 M1～M5 全部被抓到。未發現問題。
- **命名與可讀性**：模組 docstring 完整說明統計定義、`end_attr` 的由來（F-002）、尾端排除與 `None` 的理由，以及已知的統計偏誤；`_end_index` 的錯誤訊息可讀。未發現問題。
- **未使用或冗餘**：檢查 `Protocol`／`runtime_checkable`／`Sequence`／`HasEndIndex` 皆有實際用途；無未使用匯入。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| A-1 | 範圍（刻意超出） | advisory | `outlook.py` 新增兩項 `ConfigError` 守門（缺欄位、基準價非有限或為 0），AC-012／AC-013 未明文要求 | 保留；理由見品質 Review（F-002 失敗模式與 NaN 污染）。若使用者認為超出授權範圍，可移除並改為文件化假設 | 已實作並各有測試；已於本表與 TDD 紀錄標明 |
| A-2 | 輸入驗證 | advisory | `horizon` 未檢查（負值會算出「往過去」的報酬；`0` 會得到恆為 0 的報酬） | 由呼叫端（CLI／monitor 的設定驗證）負責；本模組保持純函式 | 延後（TASK-010／TASK-011 的設定驗證涵蓋） |
| A-3 | 統計偏誤 | advisory（已知限制） | 相似片段可能時間相近、高度相關，使上漲機率被重複計數影響 | 報告第 5.8 節已揭露；本版只揭露樣本數，不處理獨立性 | 已記錄（模組 docstring、SPEC 第 8 節；交付報告將再列） |
| A-4 | 整合完整性 | advisory（待補） | `PatternEvent` 尚未存在（TASK-008），目前以測試替身驗證 `end_attr="recovery_index"` | TASK-008 完成後以真實 `PatternEvent` 補一次整合斷言 | 待辦（已記於 TASK-006 測試計畫與 TDD 紀錄的「未執行或受阻」） |
| A-5 | 型別標註 | advisory | `fragments: Sequence[object]` 較寬鬆，`HasEndIndex` 已定義但未用於簽名 | 可改為 `Sequence[HasEndIndex]`；但規律路線的物件以 `recovery_index` 取值，靜態型別無法表達「依參數選欄位」，故保留 `object` 並以執行期檢查把關 | 延後（設計取捨已於 docstring 說明） |

## 修正與重審

第 1 輪未發現 blocking。Cycle 2 的 Red 有 3 個失敗（兩項守門與 F-002 的 `AttributeError`），已全數補上並重驗；變異檢查 M1～M5 全部被抓到。

重審範圍：修正後重跑單檔（13 passed）與全套（87 passed）；重讀 `outlook.py` 全文複查守門順序（先取索引 → 再判尾端 → 再檢查基準價）與 `None` 路徑。無需第二輪 blocking 修正迴圈。

## 結果

- Spec Review：passed（AC-012／AC-013 逐條符合；`end_attr` 的雙路線一致性有直接證據）
- 品質 Review：passed（正確性、`None` 契約、錯誤處理、模組責任、測試品質皆已檢查；未發現 blocking）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-2（由呼叫端驗證 `horizon`）、A-3（報告已揭露的統計偏誤）、A-4（待 TASK-008 補真實整合）、A-5（靜態型別無法表達依參數選欄位）
- 能否標為 done：**可以**
- 限制與未驗證事項：真實 `PatternEvent` 的整合斷言待 TASK-008（目前以測試替身覆蓋）；未處理片段相關性
