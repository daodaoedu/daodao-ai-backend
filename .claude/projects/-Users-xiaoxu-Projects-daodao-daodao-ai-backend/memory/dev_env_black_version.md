---
name: dev_env_black_version
description: CI 鎖定 black==25.9 和 ruff==0.14.1，本地必須對齊
type: feedback
---

本地 black/ruff 版本必須跟 CI 一致，否則格式化結果不同導致 CI 失敗。

**Why:** black 26.x 和 25.9 對多行字串縮排的格式化結果不同，曾導致 CI 反覆失敗。

**How to apply:** 在 daodao-ai-backend 安裝時用 `uv pip install "black==25.9" "ruff==0.14.1"`，版本定義在 `.github/workflows/*.yml` 裡。
