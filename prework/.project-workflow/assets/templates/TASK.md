# TASK-NNN：填入一個可驗證的交付行為

- id：TASK-NNN
- type：feature（或 bugfix／setup／spike／refactor／docs）
- status：draft
- spec_version：SPEC-001 v0.1
- ac_ids：[]
- depends_on：[]
- test_evidence：[]
- review_evidence：[]
- blocked_from／阻塞原因／恢復條件：無

建立時將 TASK-NNN 改成 TASK-001 等穩定 ID。ac_ids、depends_on 與證據欄位使用 JSON 字串清單，例如 `["AC-001"]`。證據路徑相對於目標專案根目錄，例如 `["docs/workflow/tdd/TASK-001.md"]`；尚未建立時保留空清單。完整契約見工具包 references/validation.md。

## 交付與邊界

- 本張完成後可驗證的行為：待填
- 本張不做：待填
- 每個 AC 在本張負責的範圍：待填

## 接手上下文

- Spec／相關 ADR／既有規範：待填
- 模組與公開介面：待盤點
- 預計觸及的檔案：待盤點；實作前重新查證
- 必要環境／依賴：待填

## 測試計畫

- 測試公開邊界：待填
- 第一個失敗行為與預期斷言：待填
- 後續例外／邊界情境：待填
- 單項及相關回歸的實際命令／工作目錄：待填，沿用 PROJECT
- 非程式任務的替代驗證與理由：不適用，除非另有記錄

## 完成條件

- [ ] 本張 AC 行為完成，符合目前 Spec 版本
- [ ] 必要測試及檢查實際通過，TDD 證據完整（或有合理不適用說明與替代驗證）
- [ ] Spec 與品質 Review 完成，blocking 問題歸零
- [ ] 相關文件、TASKS、STATE 同步

## 執行紀錄與證據位置

- 開工前基準 SHA／檔案快照與既有修改：尚未記錄
- TDD 紀錄位置：見上方 test_evidence
- Review 紀錄位置：見上方 review_evidence
- 目前被驗證版本／檔案狀態：尚未執行
- 取消、重開或變更原因：無
