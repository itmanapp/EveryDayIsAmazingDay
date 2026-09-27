# TASK-008 Code Review

- task_id：TASK-008
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-patterns-detect sha256:819486e7792c225bfd778b30b71e35f47dc7c59f12704a1f452d9dc721262c94
- Task／Spec 版本：TASK-008 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含 B-1 blocking 修正與兩處邊界補強）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `819486e7792c225bfd778b30b71e35f47dc7c59f12704a1f452d9dc721262c94`；本張交付的兩個檔案——`ediaad/patterns.py` `5d5dc091c0ff2aa752fe9440c80c187cbbd610a5818977e0998a334982e4f066`（含 TASK-007 的規格模型）、`tests/test_patterns_detect.py` `c98f2e6b74337187543b22bc18a4f8f232f5fac64e4c359d1a8d686771b5d163`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對；本張在 `ediaad/patterns.py` 擴充（新增 `PatternEvent`／`atr`／`detect`／`_confidence`，未改動 TASK-007 的 `PatternSpec` 契約）並新增一個測試檔
- 納入的已提交、未提交、新增檔案：`ediaad/patterns.py`（本張新增部分）、`tests/test_patterns_detect.py`＋ 本張 TDD／Review 紀錄
- 排除的既有修改及理由：`PatternSpec`／`NAMED_PATTERNS`／`RECOVERY_TARGETS`／`to_json`／`from_json` 屬 TASK-007 交付物（已於 TASK-007 Review 審查），本張未修改其行為
- 程式規範來源：`docs/workflow/SPEC.md` 第 5 節（`patterns.py` 責任、`PatternEvent` 欄位、原則 1 與 3）、AC-016～AC-020、報告第 5.4 節（ATR）、第 5.5 節（六條判定條件、二分搜尋與最長區間、去重）、第 5.6 節（信心值）、第 4.5 節（資料流 B／C）、`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-016 | `ediaad/patterns.py`（`atr`）；`tests/test_patterns_detect.py` 的 4 個案例 | 符合 | — |
| AC-017 | `ediaad/patterns.py`（`PatternEvent`、`detect` ①②③⑤、`_confidence`）；同檔 5 個案例 | 符合 | — |
| AC-018 | `ediaad/patterns.py`（反例防護）；同檔 5 個案例（含兩個對照組） | 符合 | B-1（已修正） |
| AC-019 | `ediaad/patterns.py`（比值式判定）；同檔 6 個參數化案例 | 符合 | — |
| AC-020 | `ediaad/patterns.py`（去重與排序）；同檔 3 個案例 | 符合 | — |

逐條核對：

- **AC-016**：前 `period-1` 個為 NaN、其後與純 Python 推導的 ATR 相符（`abs=1e-12`）；「不引用未來」以「植入點之後乘 10 → 之前各索引差異 < 1e-12」驗證，並**同時斷言之後的值必須改變**（避免空轉）。`period=1` 時退化為 TR 亦有測試。符合。
- **AC-017**：植入的三相位得到 `range=[30,49]`、`breakdown_index=50`、`recovery_index=51`、`band=2.4`、`depth=0.8333`、`recovery_bars=1`；`confidence` 以獨立計算的 ATR 與 SPEC 第 5.6 節公式逐項比對（`abs=1e-12`）且落在 [0,1]。`PatternEvent` 九個欄位名稱與順序以 `__dataclass_fields__` 斷言。符合。
- **AC-018**：深度不足（0.1667 < 0.2）、深度過大（2.5 > 1.5）、回歸前出現更低低點、回歸逾時四種反例皆零命中；另加兩個對照組確認「恰好落在期限」必須命中（避免 `<=` 誤寫成 `<`）。符合（B-1 修正後）。
- **AC-019**：三種乘常數與三種平移後四個相位索引完全相同；`band` 隨乘常數縮放、平移不變；`depth` 與 `confidence` 不變。符合。
- **AC-020**：同一 `(breakdown_index, recovery_index)` 只保留最長盤整；結果依盤整長度降冪（實測 `[20, 14]`）。符合。

## 品質 Review

- **B-1（blocking，已修正）——增量極值的初始視窗不完整**：`detect` 原本以 `running_high = -inf` 起步，從 `shortest_start` 往左逐格加入，**但第一個視窗 `[shortest_start..j]` 本身包含多根 K 線，右半邊從未被加入**。後果是 `band` 被低估：在安靜且同質的資料上巧合正確（`[30..49]` 的極值與子區間相同），但在異質視窗上嚴重錯誤——例如 `[51..55]` 的 `band` 被算成 1.5（實際 2.4），使不合格的區間通過 `band <= limit`，因而憑空產生事件。
  **修正**：先以 `np.max`／`np.min` 完整建立最短視窗的極值，再逐格往左擴張（`if start < shortest_start` 才更新）。
  **辨識它的測試**：AC-018 的「深度過大」與「回歸逾時」反例（原本各自多出 1 筆與 4 筆命中）。這一點值得記錄：**反例測試不只是防誤報，還能抓到「過度命中」的實作缺陷**。
- **正確性（對照報告第 5.5 節六條判定）**：① 盤整長度與 band 上限（ATR 只用 `j` 以前資料）；② 跌破為**第一次**穿破區間下緣（由 ④ 的語意反推：若取極低點則 ④ 恆真）；③ 回歸為第一次收盤回到均值之上（嚴格 `>=`）；④ 反例防護檢查 `k+1..m-1`；⑤ 信心值三項平均並 `clip`；⑥ 去重保留最長。逐項有測試。未發現不符。
- **演算法取捨**：以「由短往長掃描、超限即停」取代報告所述的二分搜尋，得到相同的「最長可行區間」語意（因 `band` 對起始索引單調不減）且實作更單純；複雜度同為 O(range_bars_max) 上界。已於 docstring 說明，並以 M6 變異證實 `break` 只是最佳化（移除後結果不變）。
- **浮點邊界（新發現的實務風險）**：`close[m] >= mean(close[i..j])` 的「恰好等於」在浮點下極脆——交錯 100.0／100.4 的均值是 `100.20000000000002`，與字面上的 100.2 不相等。**處置**：不引入容差（維持報告定義的嚴格比較），但要求測試必須使用可精確表示的均值（平坦盤整）才能測這個邊界；已在測試註解寫明。這也是本張一開始「邊界測試疑似失敗」的真正原因。
- **模組責任與依賴**：只使用 numpy／pandas 與 `ediaad.errors`；未匯入 `monitor`／`scan`／`config`；不讀寫檔案、不連網、不輸出訊息。符合 SPEC 第 5 節原則 1 與報告第 4.2 節的依賴方向。
- **效能**：`detect` 於 1,000 根 0.01 秒、10,000 根 0.06 秒（門檻 2 秒）。未發現問題。
- **測試品質**：ATR oracle 與信心值 oracle 皆為獨立實作；偵測器以植入式 oracle 逐相位斷言；反例、邊界（`>=`／`<`／期限）、尺度不變與去重齊備；含兩個「對照組」避免單側測試。變異 M1～M5 全部被抓到（M2 為先發現的測試缺口，補測後成立），M6 為等價變異。未發現問題。
- **命名與可讀性**：`detect` 的 docstring 完整列出六條判定；`_confidence` 標明「不是機率」；去重的排序鍵與同長度時的取捨都有註解。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| B-1 | 正確性 | **blocking** | `ediaad/patterns.py` `detect`：增量極值未完整建立初始視窗，`band` 被低估。觸發情境：任一 `j` 的最短視窗右半邊含有極值差異的序列（例如跌破後修復的異質區間）。影響：憑空產生命中，且回報的 `band`／`depth` 錯誤 | 先完整建立 `[shortest_start..j]` 的極值再往左擴張 | **已修正並驗證**：`5d5dc091…`；辨識測試為 AC-018 的兩個反例；全套 `150 passed` |
| T-1 | 測試缺口 | advisory（已補） | 跌破的嚴格比較 `<` 在預設規格下與 `<=` **不可區分**（相等時深度為 0，被 `depth_min=0.2` 擋掉） | 以 `breakdown_depth_band_min=0` 的規格另測一次 | **已補測試**：`test_breakdown_requires_a_strictly_lower_low_even_when_zero_depth_is_allowed`；M2 由「未抓到」變為「抓到」 |
| T-2 | 測試夾具 | advisory（已修） | 「回歸前更低低點」反例的原始夾具含**另一個合法結構**（把原跌破根吸收進盤整區間），使該反例無法只由反例防護決定 | 把中間那根的 low 壓到 88.0，使次要結構深度超出上限 | 已修正並在註解寫明理由 |
| F-1 | 浮點邊界 | advisory | `close[m] >= mean(...)` 的等值邊界受浮點表示影響（均值 `100.20000000000002`） | 不引入容差（維持報告定義）；測試改用可精確表示的均值 | 已記錄並以平坦盤整夾具覆蓋 |
| A-1 | 語意取捨 | advisory | 「回歸之前」定義為嚴格早於回歸根（`k+1..m-1`），回歸根自身的下影線不再檢查 | 本重建版明確定義並註解；報告未細分 | 已處理（文件化） |
| A-2 | 效能 | advisory | 去重與排序在全部事件產生後才進行（非線上） | 事件數遠小於候選數，無實際影響；10,000 根 0.06 秒 | 延後（無壓力） |
| A-3 | 整合 | advisory（待補） | 與 `outlook.forward_stats(end_attr="recovery_index")` 的真實整合尚未驗證（TASK-006 的 A-4） | TASK-009 之後或 TASK-037 補一次端到端斷言 | 待辦（已記於兩張 Task 的紀錄） |

## 修正與重審

- 第 1 輪：Spec Review 符合；品質 Review 找到 B-1（blocking）、T-1／T-2（測試面）、F-1（浮點邊界）。
- 修正：B-1 修正實作；T-1 補測試；T-2 修夾具；F-1 文件化並改夾具。修正後重跑單檔（28 passed）與全套（150 passed）。
- 重審：重讀 `detect` 全文複查掃描方向、極值更新條件、`k`／`m` 搜尋邊界（`min(..., bars-1)+1`）、反例防護範圍與去重排序鍵；確認未破壞 TASK-007 的 `PatternSpec` 契約（`tests/test_patterns_spec.py` 35 passed）。
- 本報告的 `checked_version` 與個別檔案雜湊皆指向修正後版本。

## 結果

- Spec Review：passed（AC-016～AC-020 逐條符合）
- 品質 Review：passed（B-1 已修正並重驗；無其他 blocking）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-2（無效能壓力）、A-3（待 TASK-009／TASK-037 補整合）
- 能否標為 done：**可以**
- 限制與未驗證事項：與 `outlook` 的真實 `PatternEvent` 整合待補；「回歸之前」的邊界語意為本重建版的明確定義
