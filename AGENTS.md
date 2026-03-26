# AI Agent Instructions

## 專案規範

進行任何開發工作（規劃、實作、除錯、review）前，先讀 `.claude/skills/project-rules/SKILL.md` 了解專案規範。

## Commit 流程

commit 時必須依序執行：

1. 先執行 `.claude/skills/pre-commit-check/SKILL.md` skill 跑品質檢查（format + lint）
2. 檢查通過後，執行 `.claude/skills/format-commit/SKILL.md` skill 產生 commit message
3. 使用者確認後才執行 git commit

### 品質檢查指令

- `make check` — Black + Ruff 格式化檢查
- `make lint` — Pylint + Bandit 靜態分析
- `make format` — 自動修復格式問題

## Push 流程

使用者說要 push 時，先詢問「要 review 嗎？」：
- Yes → 執行 `.claude/skills/code-review/SKILL.md` skill，review 完再 push
- No → 直接 push
