---
name: codebase-map
description: daodao-ai-backend codebase 地圖——FastAPI 分層、LLM client 組織、啟動依賴、Makefile 指令、已停用元件。開工前先讀
---

# daodao-ai-backend Codebase 地圖

> 目錄結構有變動時必須同步更新本檔。最後校準：2026-07-06。

## 分層結構

`src/main.py`（app + lifespan）→ `src/routers/`（feed / insight / ping / recommendation / users + `admin/` 8 個子路由）→ `src/services/`（llm / cache / insight / feed / practice / admin / prompts）→ `src/models/`（SQLAlchemy ORM，檔名 PascalCase 如 `User.py`，約 50 個）＋ `src/schemas/`（Pydantic）＋ `src/db/`（factory + PostgreSQL）＋ `src/middleware/`（CORS、TrustedHost、Logging、ApiKey、Prometheus、rate limit）＋ `src/config.py`（Pydantic Settings，`frozen=True`）＋ `src/dependencies.py`（DI + JWT/admin 驗證）。

## 路由與掛載

- 雙前綴：main.py 掛 `prefix="/api"`，各 router 內再帶 `/v1` → 實際路徑 `/api/v1/...`。健康檢查是 `/api/v1/health`。
- admin 路由 `/api/v1/admin/*` 用 JWT（`get_admin_user`，role ∈ {admin, superadmin}），**豁免 x-api-key**；一般路由走 ApiKey middleware。
- `feedback`、`resource` router 存在但**未掛載**（main.py 註解掉）。

## 啟動依賴（lifespan 順序）

1. DB（`make_database()`）→ 2. **Redis 健康檢查，失敗直接 raise 中止 app**（硬依賴）→ 3. 冪等 seed（default prompts / llm models / admin quotas）→ 4. `InsightScheduler`（APScheduler cron，失敗僅 warning）。
- **Qdrant / ClickHouse / app.state 的 LLM client 已全數註解停用**——`dependencies.py` 對應的 getter 若被重新啟用會 AttributeError，先恢復 lifespan 初始化。
- 本服務**不做 DDL**：啟動只唯讀驗證 users/practices/practice_checkins 三表。schema 歸 daodao-storage 管。

## LLM 呼叫組織

- 統一入口 `src/services/llm/client.py` 的 `LLMClient`，`_BACKEND_MAP` 註冊 **10 個 provider**（openai/gemini/anthropic/ollama/groq + cloudflare/nvidia/cerebras/openrouter/ollama_cloud，後五個共用 OpenAIChatBackend）。
- `BaseLLMBackend.generate() -> (output, cost, usage, backend_name)`；guardrail 後綴自動注入；`LoggingLLMClient` 每次呼叫寫 `AIQueryLog`。
- Prompt 在 `src/services/prompts/`（`.txt` 模板 + prompts.py）。
- Insight 排程：模型優先讀 DB `ai_service_configs`（service='insight', is_active），fallback `settings.insight.llm_backend`。**已知缺陷**：`llm/factory.py` 硬編碼 `"gemini"`，未讀 active config。

## 設定與環境

- `ENVIRONMENT` 決定讀 `.env.prod` 或 `.env.dev`；nested delimiter `__`；prefix 分組 `REDIS_` / `POSTGRES_` / `INSIGHT__` / `LLM_BACKEND__<PROVIDER>__<KEY>`。
- `get_settings()` 有 lru_cache。CD 部署時用 GitHub Secrets sed 覆寫 `.env.<env>`。

## Makefile 指令（常用）

- 品質：`make check`（black --check + ruff check，**與 CI 相同門檻**）、`make format`（ruff format + black）、`make lint`（pylint + bandit，**皆 `|| true` 不阻斷，CI 也不跑 pylint**——實質強制門檻只有 black + ruff）。
- 測試：`make test` / `make test-cov`——走**本機 `.venv/bin/python3.12`**（非容器），需先 `uv sync` 建 venv。`make test-insight` 引用的測試檔已不存在。
- Docker：`make up-dev`（port 8002→8000，mount src 熱更新）/ `up-prod`（不對外）；`make health-dev`。
- Insight 手動跑：`make insight-run` / `insight-dry-run` 及各 provider 變體。

## 工具鏈版本鎖定（踩過的坑）

CI 精確 pin `black==25.9`、`ruff==0.14.1`（`.github/workflows/ci.yml`），但 pyproject 只給下界（`>=`）——`uv sync` 可能拉到更新版，black 25.9 與 26.x 對多行字串縮排結果不同，會導致 CI 反覆紅。**本地版本必須與 CI 對齊**：`uv pip install "black==25.9" "ruff==0.14.1"`。Python 實際綁定 3.12（Makefile / CI），儘管 pyproject 寫 `>=3.10`。

## 跨 repo

與 server 共用 PostgreSQL（storage 管 schema，ORM 需人工同步）與 JWT（HS256 `JWT_SECURITY`，fallback 讀 `auth_token` cookie；payload 帶 `id` 與 `_id`）。入向：f2e（feed/recommendation/insights）、admin-ui（`/api/v1/admin/*`）。詳見 `.claude/skills/system-map/SKILL.md`。
