# 來源與改編說明

閱讀日期：2026-09-21。來源：[mattpocock/skills](https://github.com/mattpocock/skills)，讀取 `main` 分支公開文件，未取得可驗證 commit SHA；以下為移動連結，上游後續內容可能變更。

| 上游文件 | 本工具包採用的概念 |
| --- | --- |
| [grill-with-docs](https://github.com/mattpocock/skills/blob/main/skills/engineering/grill-with-docs/SKILL.md) | 訪談時同步整理領域知識與決策 |
| [grilling](https://github.com/mattpocock/skills/blob/main/skills/productivity/grilling/SKILL.md) | 先解決前置決策，再問依賴它的問題；可查事實自行查 |
| [domain-modeling](https://github.com/mattpocock/skills/blob/main/skills/engineering/domain-modeling/SKILL.md) | 清楚詞彙、具體情境、必要時保存 ADR |
| [to-spec](https://github.com/mattpocock/skills/blob/main/skills/engineering/to-spec/SKILL.md) | 從既有討論整理 Spec，包含測試公開邊界與範圍 |
| [to-tickets](https://github.com/mattpocock/skills/blob/main/skills/engineering/to-tickets/SKILL.md) | 可驗證的垂直切片；每張明列阻擋依賴 |
| [implement](https://github.com/mattpocock/skills/blob/main/skills/engineering/implement/SKILL.md) | 以測試推動實作，最後做 Review |
| [tdd](https://github.com/mattpocock/skills/blob/main/skills/engineering/tdd/SKILL.md) | 公開介面上的行為測試，一輪一個 Red → Green |
| [code-review](https://github.com/mattpocock/skills/blob/main/skills/engineering/code-review/SKILL.md) | 固定差異基準，Spec 與 Standards 分開審查 |

## 本版刻意調整

- **連續工作流程**：上游許多技能設計為由使用者分別觸發；本版以一個入口在授權範圍內接續所有階段。
- **先落地本機文件**：不要求 Issue tracker 或初始化上游工具；GitHub 可以只用來存放與分享此工具包。
- **具體追溯與續作**：加入 AC／Task ID、Spec 版本、狀態轉移、測試證據及交付範本。
- **訪談負擔**：每輪以少量關鍵問題為主；授權範圍內的可逆假設明列後繼續。
- **確認方式**：Spec、測試邊界與任務清單可合併確認；保留既有授權，不反覆確認每張 Task。
- **TDD 與重構**：讀取當日的上游 `tdd` 明列 Red → Green，並把重構放在 Review；本版採同樣安排。上游 README 仍使用 red-green-refactor 概括說明，兩者表述粒度不同。
- **Review 模式**：上游使用兩個平行代理；本版預設兩軸 self-review，在明確要求並有能力時才使用獨立代理。
- **工作區完整性**：Review 包括未提交、新增及無 Git 的檔案，而非只看已提交差異。
- **對外動作**：不自動發布 Issue 或提交／push；依使用者的專案授權處理。

以上以自己的敘述重組方法，並加入新範本及初始化工具。上游授權見 [MIT LICENSE](https://github.com/mattpocock/skills/blob/main/LICENSE)。
