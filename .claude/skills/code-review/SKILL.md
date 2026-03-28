---
name: code-review
description: Push 前 review 整個 branch 的變更，檢查邏輯錯誤、安全問題、效能問題、架構一致性
---

# Code Review

Review 當前 branch 相對於 base branch 的所有變更。

## 步驟 1：取得變更範圍

1. 執行 `git log --oneline main...HEAD` 確認 commit 數量
2. 執行 `git diff main...HEAD --stat` 確認變更檔案範圍
3. 如果 base branch 不是 main（例如 dev），自行判斷正確的 base

## 步驟 2：逐檔 Review

對每個變更的檔案，執行 `git diff main...HEAD -- <file>` 讀取 diff，檢查：

- **邏輯錯誤**：edge case、型別錯誤、exception 未處理、async 邏輯
- **安全問題**：SQL injection、硬編碼 secret、不安全的 API endpoint、缺少認證
- **效能問題**：不必要的資料庫查詢、大量資料未分頁、缺少 cache
- **架構一致性**：是否遵守專案既有模式（路由結構、service 層分離等）

## 步驟 3：回報結果

以表格格式列出發現的問題：

| 嚴重度 | 檔案 | 問題 | 建議 |
|--------|------|------|------|

嚴重度分三級：
- **High**：必須修，有 bug 或安全風險
- **Medium**：建議修，效能或可維護性問題
- **Low**：可選，風格或小優化

## 步驟 4：處理問題

- High 問題 → 詢問使用者是否要修復
- Medium / Low → 列出即可，由使用者決定
