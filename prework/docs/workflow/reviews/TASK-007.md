# TASK-007 Code Review

- task_id：TASK-007
- spec_result：passed
- quality_result：passed
- blocking_count：0
- checked_version：snap-2026-09-24-ocaievo-patterns-spec sha256:8f6edeb7ddfb91c799b8c42a470657afaa1efee3eff4cb5695041faf179b1058
- Task／Spec 版本：TASK-007 / SPEC-001 v0.4
- 審查模式：self-review（同一 AI 分兩次、以分開的清單執行；本專案未指定獨立 reviewer）
- 日期／輪次：2026-09-24，第 1 輪（含一次 Review 後的小幅清理，見「修正與重審」）
- 基準 SHA／前置快照：`docs/workflow/evidence/baseline-before-implement.txt`（sha256 `a8da2be21ae623c2ea439e095d22c9467688d2969dbc7d288611fd40c2e611e3`）
- 審查目標 SHA／檔案雜湊：原始碼樹組合 sha256 `8f6edeb7ddfb91c799b8c42a470657afaa1efee3eff4cb5695041faf179b1058`；本張交付的兩個檔案——`ediaad/patterns.py` `1eed00098013b5ae57c8ad75ae307fc98996f26a03323b44c220d0f418eb231d`、`tests/test_patterns_spec.py` `03eac75ee8b5cf3ce7d6410dff7d6cba3342da72b8e50209a7a3108180e34651`
- 差異命令或前後比較方法：無 Git（未取得 `git init` 授權），以前後檔案清單與逐檔 sha256 比對；本張新增 2 檔，未修改其他模組
- 納入的已提交、未提交、新增檔案：`ediaad/patterns.py`（本張僅 `PatternSpec` 部分）、`tests/test_patterns_spec.py`（本張交付物）＋ 本張 TDD／Review 紀錄
- 排除的既有修改及理由：`data.py`／`features.py`／`similarity.py`／`scan.py`／`outlook.py`／`errors.py` 與既有測試屬 TASK-001～006 交付物，本張未修改
- 程式規範來源：`docs/workflow/SPEC.md` 第 5 節（`patterns.py` 責任、`PatternSpec` 欄位契約與內建預設值、原則 1、錯誤分層）、AC-014／AC-015、報告第 3.1 節 F7、第 4.3 節、第 4.4 節（`PatternSpec` 欄位清單與預設值）、第 8.3 節 F-002、`references/review.md`

## Spec Review

| AC | 實作與測試位置 | 結果（符合／不符／未驗證） | 發現 ID |
| --- | --- | --- | --- |
| AC-014 | `ediaad/patterns.py`（`PatternSpec.__post_init__`、`RECOVERY_TARGETS`、`NAMED_PATTERNS`）；`tests/test_patterns_spec.py` 的 6 個案例 ＋ 20 個參數化不合法案例 | 符合 | — |
| AC-015 | `ediaad/patterns.py`（`to_json`、`from_json`、`_spec_field_names`）；`tests/test_patterns_spec.py` 的 9 個案例 | 符合 | — |

逐條核對：

- **AC-014**：欄位順序以 `dataclasses.fields` 驗證等於 SPEC 第 5 節的十個名稱；`NAMED_PATTERNS["range_fakeout_reversion"]` 與 SPEC 的預設值逐欄相等；frozen 以指派觸發 `FrozenInstanceError` 驗證；「無價格欄位」以「欄位名不得含 price／open／high／low／close／volume」與「`RECOVERY_TARGETS == ("range_mean",)`」兩項斷言表達；20 個不合法案例涵蓋交叉條件（`min > max`、深度下限 > 上限）、各欄位下限、`band_atr_multiple_max` 為 0、未知 `recovery_target`、以及四種型別錯誤（含 `bool` 給 int 欄位、`14.5` 給 int 欄位）。合法邊界 `min == max` 與 `recovery_bars_max == 0` 亦各有測試。符合。
- **AC-015**：`from_json(to_json(spec)) == spec`（frozen dataclass 相等語意）；連續兩次 `to_json` 輸出字串完全相同且鍵序等於字母序、鍵集合等於欄位集合；缺欄位、部分欄位、多欄位、型別不符、非法 JSON、非物件 JSON 六種輸入各自 `ConfigError`，且都在建構之前擋下（不建構出任何規格）。符合。
- **錯誤契約**：所有驗證失敗都是 `ediaad.errors.ConfigError`（對應 CLI exit 2），未外洩 `TypeError`／`JSONDecodeError`。符合。

## 品質 Review

- **正確性（對照報告第 4.4 節與 SPEC 第 5 節）**：十個欄位名稱、型別與預設值逐項相符；`range_bars_min <= range_bars_max`、深度區間、`recovery_target` 的候選集合皆與規格一致。未發現不符。
- **「不合法規格無法被建構」的落實**：所有驗證都在 `__post_init__`，因此沒有任何路徑能取得不合法實例（包含 `from_json` 也走同一條建構路徑）。以 20 個參數化案例與變異 M1／M5／M6 驗證。未發現問題。
- **邊界取捨的一致性**：`breakdown_bars_max >= 1`（0 會讓 `j < k <= j` 無解，規格永遠不可能命中）與 `recovery_bars_max >= 0`（0 代表同一根完成跌破與回歸）看似不對稱，但兩者都直接對應規格的不等式語意，且各有測試；已在 TDD 紀錄與 `__post_init__` 的下限參數中載明。**這不是缺陷**，但值得在交付報告提醒使用者。
- **序列化的嚴格性**：`from_json` 明確拒絕缺欄位與未知欄位，且**不以預設值補齊**——理由是不這樣做會讓「使用者以為自己設定的參數」與「實際生效的參數」不一致（此風險在後續 `watchlist.json` 的 `pattern_spec` 會真實出現）。訊息列出缺少或未知的欄位名。未發現問題。
- **穩定性與可比較性**：`sort_keys=True` 讓兩份規格可直接以文字比對（後續 catalog 與設定的 diff 會用到）；`ensure_ascii=False` 讓錯誤訊息與欄位保持可讀。未發現問題。
- **模組責任與依賴**：只使用標準庫 `json`／`dataclasses`／`collections.abc` 與 `ediaad.errors`；沒有 `numpy`／`pandas` 依賴，也未匯入上層模組；不讀寫檔案、不連網、不輸出訊息（SPEC 第 5 節原則 1）。未發現問題。
- **後續擴充的介面穩定**：`RECOVERY_TARGETS`／`NAMED_PATTERNS`／`PatternSpec` 三者是 TASK-008／009／010 的依賴；欄位名稱與順序已由測試鎖定，後續擴充若改動會立刻失敗。未發現問題。
- **測試品質**：型別錯誤涵蓋 `bool` 對 int 這種 Python 特有的陷阱；`from_json` 的六種壞輸入都以「不建構出規格」為判準；變異 M1～M6 全部被抓到。未發現問題。
- **命名與可讀性**：`PatternSpec` 每個欄位都有 docstring（說明單位與語意）；`_require_int`／`_require_number` 的訊息含欄位名與實際值；模組 docstring 說明「相對單位」與「不合法無法建構」兩項保證。未發現問題。

## 問題清單

| ID | 面向 | blocking／advisory | 檔案／行號、觸發情境與影響 | 修正建議 | 狀態／驗證證據 |
| --- | --- | --- | --- | --- | --- |
| Q-1 | 冗餘驗證 | advisory | `band_atr_multiple_max` 同時使用 `_require_number(..., minimum=0)` 與顯式 `<= 0` 檢查，前者多餘 | 移除 `minimum=0` 參數（顯式檢查已涵蓋 0 與負值） | **已修正**（`1eed0009…`）；行為不變，全套 `122 passed` |
| A-1 | 邊界語意 | advisory | `breakdown_bars_max >= 1` 與 `recovery_bars_max >= 0` 的不對稱可能被誤解 | 已於 TDD 紀錄與下限參數載明；建議交付報告再提醒一次 | 已記錄（無程式變更） |
| A-2 | 可變常數 | advisory | `NAMED_PATTERNS` 雖標為常數，但其值為可變 `dict`；呼叫端若修改會影響全程序 | 可用 `types.MappingProxyType` 包住外層與內層；目前無任何程式碼修改它，且 SPEC 未要求凍結此映射 | 延後（若 TASK-010 或網頁層需要共享此常數，再包成唯讀） |
| A-3 | 型別標註 | advisory | `NAMED_PATTERNS` 值標為 `dict[str, Any]`，實際可能以 `Mapping` 更精確 | 待 A-2 決定後一併調整 | 延後（與 A-2 綁定） |

## 修正與重審

- 第 1 輪：Spec Review 符合；品質 Review 發現 Q-1（冗餘驗證），已修正。
- 重審：修正後重跑單檔（35 passed）與全套（122 passed）；重讀 `patterns.py` 複查驗證順序（型別 → 下限 → 交叉條件）、`from_json` 的三段式檢查（解析 → 鍵集合 → 建構）與訊息內容。Spec 與品質兩軸通過，blocking 歸零。
- 本報告的 `checked_version` 與個別檔案雜湊皆指向修正後的版本。

## 結果

- Spec Review：passed（AC-014／AC-015 逐條符合；20 個不合法案例與 6 種壞 JSON 都有直接證據）
- 品質 Review：passed（正確性、驗證落實、邊界語意、序列化嚴格性、穩定性、模組責任、測試品質皆已檢查；Q-1 已修正）
- 未解決 blocking 數：0
- 延後 advisory 及理由：A-1（語意已載明）、A-2／A-3（目前無呼叫端修改此常數，SPEC 未要求凍結）
- 能否標為 done：**可以**
- 限制與未驗證事項：`recovery_target` 目前只有 `range_mean`；`atr`／`detect`／`learn` 與 `PatternEvent` 尚未存在（TASK-008／009）
