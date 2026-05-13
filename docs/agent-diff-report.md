# Agent Architecture Diff Report

**Target**: /Users/xiaoxu/Projects/daodao/daodao-ai-backend
**Date**: 2026-05-10
**Overall Score**: 49/195 (25%)

## Summary

| Category | Score | Max | % |
|----------|-------|-----|---|
| Harness Engineering | 30 | 115 | 26% |
| Context Engineering | 10 | 50 | 20% |
| Prompt Engineering | 9 | 30 | 30% |
| **Overall** | **49** | **195** | **25%** |

## Top Gaps (Highest Impact)

1. **Tool System** (A3: 2/5) — LLM cannot call tools; all generation is single-turn prompt→text with no function-calling capability
2. **Error Handling & Resilience** (A5: 2/5) — Zero retry logic; transient 429/5xx immediately surfaces as error; easy fix with `tenacity`
3. **Conversation History** (B4: 0/5) — All calls are stateless single-turn; no multi-turn conversation or session continuity possible
4. **Memory System** (B3: 0/5) — No user memory or cross-session personalization; each request starts from scratch
5. **Few-Shot Examples** (C3: 1/5) — No example outputs in any prompt file; LLM has no reference for what "good" looks like; low effort to fix

## Detailed Analysis

### A. Harness Engineering — 30/115

#### A1. Hooks / Lifecycle — Score: 2/5
**Status**: Partial — HTTP middleware only, no AI-layer lifecycle events
**Evidence**:
- `src/middleware/middleware.py:61-71` — `LoggingMiddleware` intercepts HTTP request/response with timing
- `src/middleware/middleware.py:75-113` — `ApiKeyMiddleware` for auth; hardcoded exempt path list
- No PreToolUse / PostToolUse / SessionStart equivalents anywhere in `src/`
**Action Plan**:
- Define hook registry with `before_generate` / `after_generate` events on `LLMClient`
- Make exempt paths configurable via `Settings` rather than hardcoded Python
- Add `pre_request`/`post_response` hook callbacks for external registration
**Effort**: High

---

#### A2. Permission Model — Score: 1/5
**Status**: Partial — global API key toggle + JWT; no per-tool rules
**Evidence**:
- `src/middleware/middleware.py:75-113` — `ApiKeyMiddleware`: dev bypasses all, prod requires `x-api-key`
- `src/verify_jwt.py` — JWT verification for admin routes
- `src/services/quota_service.py` — per-user token quota; only gate is token consumption, not action type
**Action Plan**:
- Introduce `@require_role("admin")` decorator for admin endpoints
- Add per-endpoint permission config to `Settings`
- Log permission decisions (allow/deny + reason) to `AIQueryLog` or a dedicated audit table
**Effort**: Medium

---

#### A3. Tool System — Score: 2/5
**Status**: Partial — provider registry exists; LLM cannot call tools
**Evidence**:
- `src/services/llm/client.py:16-27` — `_BACKEND_MAP` maps 10 providers (tool = LLM backend, not agent-callable tool)
- `src/schemas/` — Pydantic schemas for HTTP endpoints only, no LLM function-call definitions
- No `inputSchema`, no `@tool` decorator, no dynamic tool selection by the LLM
**Action Plan**:
- Define `ToolDefinition` dataclass with `name`, `description`, `input_schema`, `execute()`
- Add function-calling support to Anthropic and OpenAI backends (native support exists)
- Create tool registry that `LLMClient` passes as `tools=` in API calls
**Effort**: High

---

#### A4. Configuration Layering — Score: 3/5
**Status**: Implemented — multi-file env merge with deep merge; no dynamic reload
**Evidence**:
- `src/config.py:13-14` — `.env.prod` / `.env.dev` selection by `ENVIRONMENT` env var
- `src/config.py:18-24` — `pydantic_settings` with 3-file fallback chain
- `src/config.py:168-185` — `_merge_llm_backend_defaults` deep merges per-provider overrides
- `src/config.py:104-139` — `_LLM_BACKEND_DEFAULTS` for all 10 providers; `__` delimiter overrides
**Action Plan**:
- Add `@lru_cache` to `get_settings()` — currently rebuilds entire Settings on every call (one-line fix)
- Wire `AIServiceConfig` DB model as a live override layer (runtime update without restart)
- Log which env file was loaded and which values were overridden
**Effort**: Low

---

#### A5. Error Handling & Resilience — Score: 2/5
**Status**: Partial — basic try/catch everywhere; no retry or backoff
**Evidence**:
- `src/services/llm/anthropic_backend.py:49-51` — `try/except Exception`, log, re-raise; no retry across all backends
- `src/services/insight/insight_scheduler.py:76-80` — fallback to default client if DB config fails
- `src/services/insight/insight_scheduler.py:132-137` — per-practice exception counts without crashing job
- No `tenacity`, no `backoff`, no `Retry-After` parsing anywhere
**Action Plan**:
- Add `tenacity` retry decorator to `BaseLLMBackend.generate()` with exponential backoff for 429/5xx
- Implement fallback model chain: `LLMClient(settings, backends=["gemini","groq","anthropic"])`
- Parse `Retry-After` headers from rate limit responses
**Effort**: Medium

---

#### A6. Multi-Model Support — Score: 3/5
**Status**: Implemented — 10 providers, DB-driven routing; hardcoded factory
**Evidence**:
- `src/services/llm/client.py:16-27` — 10 providers in `_BACKEND_MAP`
- `src/services/insight/insight_scheduler.py:66-80` — runtime model selection from `AIServiceConfig` DB with fallback
- `src/models/AIServiceConfig.py` — per-service provider/model/temperature/max_tokens in DB
- `src/services/llm/factory.py` — hardcoded `"gemini"` instead of reading active config
**Action Plan**:
- Fix `factory.py` to read backend from `AIServiceConfig` or settings instead of hardcoding `"gemini"`
- Add fallback chain: try providers in order on failure
- Add model capability metadata (`supports_function_calling`, `context_window`) to `LLMModel`
**Effort**: Medium

---

#### A7. Operational Modes — Score: 1/5
**Status**: Partial — deployment environments only; no agent behavior modes
**Evidence**:
- `src/config.py:154` — `environment: Literal["development","staging","production"]` affects CORS/auth only
- No `planMode`, `sandboxMode`, `executionMode`, `verbose`, `dry_run` anywhere in `src/`
- No mode concept affects LLM behavior or tool availability
**Action Plan**:
- Add `execution_mode` to `AIServiceConfig`: `"normal"`, `"readonly"`, `"debug"` — debug logs full prompts
- Add `dry_run` flag to `LLMClient.generate()` returning mock response without API call
- Define `readonly` mode for insight generation using lower-cost models
**Effort**: Medium

---

#### A8. Background Execution — Score: 3/5
**Status**: Implemented — APScheduler + BackgroundTasks; no task queue or status tracking
**Evidence**:
- `src/services/insight/insight_scheduler.py:1-2` — `APScheduler` `AsyncIOScheduler` with `CronTrigger`
- `src/main.py:74-85` — scheduler in FastAPI lifespan; `misfire_grace_time=3600`
- `src/config.py:100-101` — cron schedule configurable via `INSIGHT__SCHEDULE_CRON` env var
- `src/routers/feedback.py:64,89` — `BackgroundTasks` with Celery TODO comment
**Action Plan**:
- Add `GET /admin/scheduler/status` and `POST /admin/scheduler/trigger` admin endpoints
- Replace `BackgroundTasks` in feedback router with Celery (already declared in `pyproject.toml`)
- Store scheduler job results in `SchedulerRunLog` table
**Effort**: Medium

---

#### A9. Skill / Plugin System — Score: 1/5
**Status**: Partial — static prompt files only; no skill discovery or registry
**Evidence**:
- `src/services/prompts/prompts.py` — `RAGPromptBuilder` loads `.txt` files; 2 static templates
- `src/services/prompts/rag_system.txt`, `insight_system.txt` — no discovery mechanism
- No `loadSkill`, `pluginManifest`, or `marketplace` signals anywhere
**Action Plan**:
- Define `PromptTemplate` base class with registry dict for named templates
- Add `skills/` directory with YAML skill definitions loaded at startup
- Long-term: plugin manifest schema with typed capabilities (prompt, tool, agent)
**Effort**: High

---

#### A10. Agent Dispatch — Score: 0/5
**Status**: Not implemented
**Evidence**:
- No `*agent*`, `*subagent*`, `*coordinator*` files in `src/`
- No `spawnAgent`, `forkAgent`, `orchestrat` patterns anywhere
- All LLM calls are single-shot synchronous via `LLMClient.generate()`
**Action Plan**:
- Implement `AgentRunner` class using `asyncio.gather()` with different system prompts in parallel
- Define agent "personas" as YAML configs (`insight_agent.yaml`, `recommendation_agent.yaml`)
- Long-term: coordinator that dispatches specialized agents and merges results
**Effort**: High

---

#### A11. Output Control — Score: 1/5
**Status**: Partial — fixed response structure; no streaming or output style system
**Evidence**:
- `src/response_template.py` — single fixed response structure
- `src/services/llm/base.py:13` — `generate()` returns `(output, cost, usage, backend_name)`; no style param
- `src/models/AIQueryLog.py` — `is_stream` column exists but no streaming implementation
**Action Plan**:
- Add `output_format` enum to `generate()`: `json | markdown | plain`
- Implement SSE streaming in Anthropic and OpenAI backends (native support exists)
- Add `response_style` config field to `AIServiceConfig`
**Effort**: Medium

---

#### A12. Planning & Task Management — Score: 0/5
**Status**: Not implemented (domain `Task` model exists but is not agent planning)
**Evidence**:
- `src/models/Task.py` — user-facing task domain model, not agent planning construct
- No `AgentTask`, `planMode`, `taskDependenc`, `blockedBy` patterns anywhere
- All operations are single-turn: prompt in → LLM response out
**Action Plan**:
- Add `AgentTask` dataclass with `status: Literal["pending","in_progress","completed","failed"]`; store in Redis
- For multi-step pipelines: decompose into explicit steps tracked in a plan dict before execution
- Add `plan_mode` flag preventing writes until plan is confirmed
**Effort**: High

---

#### A13. MCP Integration — Score: 0/5
**Status**: Not implemented
**Evidence**:
- No `*mcp*` files, no `.mcp.json`, no `McpServer`, `MCPConnection`, `mcp__` patterns anywhere
- Direct Python SDK calls used instead of MCP protocol
**Action Plan**:
- Add `mcp` Python package and implement basic `MCPClient` wrapper
- Create `.mcp.json` with at least one MCP server definition
- Expose Qdrant search and PostgreSQL as MCP tools consumable by LLM agent layer
**Effort**: High

---

#### A14. Security & Privacy — Score: 2/5
**Status**: Partial — auth + CORS + rate limiting; no prompt injection detection
**Evidence**:
- `src/middleware/middleware.py:23-55` — TrustedHost + CORS per environment
- `src/middleware/limiter.py` — `slowapi` rate limiting
- `src/models/AIQueryLog.py:52` — `prompt_chars` not raw prompt ("不存 prompt 原文，保護隱私")
- No sandbox, no secret detection, no prompt injection detection
**Action Plan**:
- Add prompt injection detection: scan for `<system>`, `IGNORE PREVIOUS` patterns in LLM tool results
- Extend `Bandit` lint to runtime injection pattern checks
- Add destructive operation warnings in system prompts
**Effort**: Medium

---

#### A15. Observability & Cost Tracking — Score: 3/5
**Status**: Implemented — structured per-call logging + Prometheus; no distributed tracing
**Evidence**:
- `src/models/AIQueryLog.py` — `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `status`, `backend`, `user_id` all logged
- `src/services/llm/logging_client.py:65-92` — `LoggingLLMClient` wraps every call with timing + DB write in `finally`
- `src/auto_metrics.py` — `@observe_api` Prometheus Counter + Histogram per endpoint
- `src/routers/admin/dashboard.py` — admin analytics endpoint
**Action Plan**:
- Add OpenTelemetry instrumentation (spans from HTTP → LLM call → DB write)
- Add `cache_hit` field to `AIQueryLog` from Anthropic `cache_read_input_tokens` response
- Add cost alert in `LoggingLLMClient` when `cost_usd > threshold`
**Effort**: Medium

---

#### A16. IDE & External Integration — Score: 0/5
**Status**: Not implemented (architecturally not applicable for a backend service)
**Evidence**:
- No IDE extension, LSP server, or deep-link surface in `src/`
- External integration is inbound HTTP REST only
**Action Plan**:
- If needed: add WebSocket endpoint for streaming responses consumable by IDE extension
- Add OpenAPI-based typed client SDK generator for consumers
**Effort**: High (likely out of scope)

---

#### A17. Command System — Score: 1/5
**Status**: Partial — single Click CLI script; no command registry
**Evidence**:
- `src/services/rank_feed.py:5,297-298` — `@click.command()` with `-t`/`--to` option; one standalone script
- No `commands/` directory, no registry, no keybinding system
**Action Plan**:
- Extract all operational scripts into `src/cli/` package with Click groups per domain (feed, insight, admin)
- Add `description` and `is_enabled` metadata to each command
- Wire CLI entry point in `pyproject.toml` under `[project.scripts]`
**Effort**: Low

---

#### A18. SDK / Programmatic API — Score: 2/5
**Status**: Partial — internal APIs exist; no versioned external SDK
**Evidence**:
- FastAPI auto-generates OpenAPI spec for HTTP consumers
- `src/services/llm/client.py` — `LLMClient` as typed internal API surface
- `src/services/feed/__init__.py:4` — `__all__` exports `FeedService`, `score_practice`, etc.
**Action Plan**:
- Publish `daodao-ai-sdk` Python package wrapping HTTP API with typed Pydantic models
- Add `src/sdk/` module exposing `LLMClient`, `FeedService`, `InsightService` with documented interfaces
**Effort**: Medium

---

#### A19. Concurrency Management — Score: 2/5
**Status**: Partial — async framework used; insight loop is serial; Celery declared but unused
**Evidence**:
- `src/services/insight/insight_scheduler.py:122-138` — serial `for practice in practices` with individual `await` calls
- `src/routers/feedback.py:64,89` — `BackgroundTasks.add_task()` with Celery TODO
- `pyproject.toml` — `celery[redis]` declared but not wired
- No `asyncio.gather`, `asyncio.Semaphore` usage in `src/`
**Action Plan**:
- Replace serial insight loop with `asyncio.gather(*[...], return_exceptions=True)` + semaphore limit (5 concurrent)
- Wire Celery for feedback processing
- Add `asyncio.Lock` in `InsightScheduler._run_job` to prevent overlapping cron firings
**Effort**: Medium

---

#### A20. Version Migration — Score: 1/5
**Status**: Partial — Alembic referenced in comments; no migration files in repo
**Evidence**:
- `src/db/postgresql.py:17` — comment: "Schema 管理由 Alembic migration 負責，此服務不執行 DDL"
- No `migrations/` or `alembic/` directory in repo
- No `schemaVersion` or config format migration
**Action Plan**:
- Add `alembic/` directory (or link to shared migration repo) with documented workflow
- Add `config_version` to `Settings` with startup validation warning on mismatch
- Document migration runbook in `docs/`
**Effort**: Medium

---

#### A21. File Operation Safety — Score: 0/5
**Status**: Not applicable as primary feature; admin prompt CRUD has no change history
**Evidence**:
- No file editing pipeline in the service
- `src/routers/admin/system_prompts.py` — edits DB-persisted prompts with no versioning or rollback
**Action Plan**:
- Add `prompt_history` table (soft-delete + versioning) for `SystemPrompt` changes
- Add `PromptChangeLog` model recording old/new values, editor user ID, timestamp
**Effort**: Low

---

#### A22. Sandbox Execution Environment — Score: 0/5
**Status**: Not implemented (not currently needed — LLM output is text-only)
**Evidence**:
- No sandbox runtime, no `allowed_paths`, no `nsjail`/`firejail` in `src/`
- `src/routers/admin/playground.py` — runs LLM prompts interactively; prompt injection unguarded
**Action Plan**:
- If code execution added: integrate `RestrictedPython` or subprocess jail
- For admin playground: add prompt injection detection for role-override patterns
**Effort**: High (if code execution added); Low (playground injection guard)

---

#### A23. Computer Use — Score: 0/5
**Status**: Not implemented (out of scope for this backend)
**Evidence**:
- No `playwright`, `selenium`, `pyautogui`, `screenshot`, or GUI interaction in `src/`
**Action Plan**:
- If needed: add `playwright` async Python behind `ComputerUseService` interface
- Expose `/api/computer-use/screenshot` gated by admin auth
**Effort**: High

---

### B. Context Engineering — 10/50

#### B1. Context Assembly Pipeline — Score: 2/5
**Status**: Partial — manual section concatenation; no section registry or cache boundary
**Evidence**:
- `src/services/insight/insight_service.py:115-218` — `_build_prompt()` assembles named sections (system, practice info, checkin stats, notes, user profile) via string concatenation
- `src/services/insight/insight_service.py:28-43` — 4-level priority chain for system prompt source
- `src/services/llm/anthropic_backend.py:38` — system prompt embedded in user message, not `system=` param
- `src/services/prompts/rag_system.txt:1` — `{style_section}` placeholder never populated (bug)
**Action Plan**:
- Refactor `_build_prompt()` sections into named registry dict with defined resolution order
- Pass system prompt via `system=` parameter in `AnthropicBackend` (enables server-side prompt caching)
- Fix the broken `{style_section}` substitution in `RAGPromptBuilder`
**Effort**: Medium

---

#### B2. Instruction Layering & Merging — Score: 1/5
**Status**: Partial — sequential fallback only; no hierarchical merge
**Evidence**:
- `src/services/admin/prompt_service.py:51-60` — single active prompt per named slot; only one source active at a time
- `src/services/insight/insight_service.py:28-43` — priority: override → DB → txt → hardcode (fallback, not merge)
- No global + project + user-level instruction hierarchy at runtime
**Action Plan**:
- Introduce two-layer system: base system prompt (global, versioned) + per-context addendum
- Add user-preference layer appending language/tone instructions based on user profile data
**Effort**: Medium

---

#### B3. Memory System — Score: 0/5
**Status**: Not implemented
**Evidence**:
- No `*memory*`, `saveMemory`, `loadMemory`, `recallMemory` anywhere in `src/`
- `src/services/llm/anthropic_backend.py:38` — every call is single-turn; no prior state passed
- `src/services/insight/insight_service.py` — behavioral stats from DB injected ad-hoc; not a general memory system
**Action Plan**:
- Create `UserMemory` DB table for user-level preferences and past interaction patterns; inject relevant entries into `_build_prompt()`
- Cache analyzed checkin stats (streak, mood pattern) in Redis with TTL to avoid re-querying DB
**Effort**: High

---

#### B4. Conversation History Management — Score: 0/5
**Status**: Not implemented
**Evidence**:
- All backends: `messages=[{"role": "user", "content": prompt}]` — single-turn only
- `src/services/review_service.py:17` — history injected as JSON blob in user message (not proper `messages` array)
- No `sessionHistory`, `transcript`, `resumeSession` patterns anywhere
**Action Plan**:
- Extend `BaseLLMBackend.generate()` to accept optional `messages: list[dict]` for multi-turn
- Add `ConversationSession` model (Redis + TTL) storing `[{role, content}]` arrays keyed by session UUID
- Refactor `review_service.py` to pass history as actual `messages` entries
**Effort**: High

---

#### B5. Token Budget & Allocation — Score: 2/5
**Status**: Partial — per-call output cap + user quota; no pre-call input estimation
**Evidence**:
- `src/services/llm/base.py:28-29` — `_estimate_tokens(text)`: `max(1, len(text) // 4)` (crude; wrong for CJK)
- `src/services/llm/anthropic_backend.py:26` — `max_tokens = kwargs.get("max_tokens", 1024)` — configurable
- `src/services/quota_service.py:119-137` — `check_user_quota()` enforces monthly/daily token limits
- `src/utils/llm_router.py:59` — `estimate_tokens` commented out (dead code)
- No pre-call guard against context window overflow; no truncation strategy
**Action Plan**:
- Replace `_estimate_tokens()` with `anthropic.count_tokens()` or `tiktoken` (especially for CJK content)
- Add pre-call guard in `_build_prompt()`: if estimated input > `(context_window - max_tokens)`, truncate least-important sections
- Track `cache_read_input_tokens` separately once Anthropic prompt caching is implemented
**Effort**: Medium

---

#### B6. Dynamic Injection — Score: 1/5
**Status**: Partial — DB-backed system prompt; string concatenation not `system=` parameter
**Evidence**:
- `src/routers/admin/playground.py:62-74` — system prompt prepended via f-string: `f"{system_content}\n\n---\n{body.message}"`
- `src/models/SystemPrompt.py` — DB-backed prompt entity with active/inactive toggle
- No `systemReminder`, `injectContext`, `attachment` patterns anywhere
**Action Plan**:
- Pass `system=system_content` as separate parameter in `AnthropicBackend.generate()`
- Add `context_parts: list[str]` accumulator to `LLMClient` for mid-assembly injection
- Define `Reminder` dataclass for between-message context injection
**Effort**: Medium

---

#### B7. Information Retrieval Strategy — Score: 2/5
**Status**: Partial — Qdrant infrastructure built but disabled in production; RAGPromptBuilder broken
**Evidence**:
- `src/services/qdrant/client.py:57-66` — `QdrantClient.search()` with vector search, `min_score`, cosine distance
- `src/main.py:46-47` — Qdrant client creation **commented out** (disabled in production)
- `src/dependencies.py:147` — `QdrantDep` also commented out
- `src/services/llm/client.py:50` — `RAGPromptBuilder` instantiated but `create_rag_prompt()` references `self.system_prompt_template` which doesn't exist (bug)
**Action Plan**:
- Uncomment and wire Qdrant client in `main.py` and `dependencies.py`
- Fix `RAGPromptBuilder`: use correct attribute name in `create_rag_prompt()`
- Add `min_score` fallback to keyword/SQL search when vector results are empty
- Add embedding LRU cache (keyed by text hash) to avoid redundant API calls
**Effort**: Medium

---

#### B8. Multimodal Input — Score: 0/5
**Status**: Not implemented
**Evidence**:
- All backends: `content` is always a plain string; no image blocks, base64, or file uploads
- No `image.*input`, `processImage`, `voice`, `audio`, `STT`, `pdf.*read` patterns in `src/`
**Action Plan**:
- Change `BaseLLMBackend.generate()` to accept `content: str | list[dict]` for multi-part messages
- Implement image input in `AnthropicBackend` using `{"type": "image", "source": {...}}` blocks
- Add `FileAttachment` schema and `UploadFile` handling at endpoint level
**Effort**: High

---

#### B9. Context Eviction & Compression — Score: 0/5
**Status**: Not implemented (not needed yet — all calls are stateless single-turn)
**Evidence**:
- No `compact`, `compress`, `evict`, `summariz.*history` patterns anywhere
- All calls stateless; no conversation history accumulated that would need eviction
**Action Plan**:
- After implementing B4 (Conversation History): add `max_history_tokens` threshold
- When exceeded: summarize oldest N turns via dedicated summarization LLM call and replace with summary
- Persist session to Redis with TTL
**Effort**: High (depends on B4)

---

#### B10. Cache Strategy — Score: 2/5
**Status**: Partial — Redis output-level caching; no Anthropic prompt caching
**Evidence**:
- `src/services/cache/client.py` — Redis `CacheClient` with `write_dict`/`read_dict`/`expire`
- `src/routers/recommendation.py:51-52` — `cache_hit` flag; Redis check before LLM call
- `src/schemas/api_response.py:40` — `cache_hit: bool` in every API response
- No `cache_control`, `cacheControl`, `promptCache` at LLM API level anywhere
**Action Plan**:
- Add `cache_control: {"type": "ephemeral"}` to `system` parameter in `AnthropicBackend.generate()`
- Separate static system prompt prefix (cacheable) from dynamic per-request suffix
- Invalidate Redis output caches when `SystemPrompt` is updated (hook into PUT endpoint)
- Track `cache_read_input_tokens` vs `cache_creation_input_tokens` from Anthropic response
**Effort**: Medium

---

### C. Prompt Engineering — 9/30

#### C1. Instruction Writing Patterns — Score: 2/5
**Status**: Basic — structure present; no priority ordering, anti-patterns, or NEVER/MUST language
**Evidence**:
- `CLAUDE.md:9` — sequential commit steps; some structure
- `src/services/prompts/insight_system.txt:10-18` — three output sections listed; no priority hierarchy
- `src/services/prompts/rag_system.txt:36` — numbered reminders but aspirational, not rule-based
- No NEVER/MUST NOT/CRITICAL language in any prompt file; no anti-pattern tables
**Action Plan**:
- Add priority-ranked rules to `insight_system.txt`: "NEVER fabricate statistics not present in input"
- Add anti-pattern section: "Do NOT use formal/academic tone — write like a warm coach"
- Add conditional branches: "If user has no checkin notes → base insight on stats only"
- Distinguish CLAUDE.md (human dev rules) from AGENTS.md (AI agent execution rules)
**Effort**: Medium

---

#### C2. Tool Description Quality — Score: 1/5
**Status**: Minimal — no tool system with descriptions; backend selection has no guidance
**Evidence**:
- `src/services/llm/client.py:16` — `_BACKEND_MAP` maps 9 backend names; no "when to use" metadata
- `src/utils/llm_router.py` — entire routing logic file is commented-out dead code
- `src/services/llm/base.py:14` — `generate()` has no docstring on when/how to use each backend
**Action Plan**:
- Add docstrings to each backend class specifying use case, strengths, limitations
- Resurrect or replace `llm_router.py` with documented routing logic
- Add selection guide in `LLMClient` or `factory.py` explaining when each backend fits
**Effort**: Medium

---

#### C3. Few-Shot and Example Design — Score: 1/5
**Status**: Minimal — output structure described but no example outputs; no format templates
**Evidence**:
- `src/services/prompts/insight_system.txt:10-18` — "洞察需包含: 1. 你做到了什麼 2. 你學到了什麼 3. 給你的建議" — structure described, no example output
- `src/services/prompts/rag_system.txt:1-40` — full prompt with data sections; zero examples of good output
- No `<example>` tagged blocks anywhere in any prompt file
**Action Plan**:
- Add 1-2 example insight outputs in `insight_system.txt` using `<example>` tags
- Add a "bad output" example (generic praise, made-up facts — what to avoid)
- Add a format template showing: opening observation → learning extract → concrete next step
- For `rag_system.txt`, add example weaving trend data + project info into cohesive response
**Effort**: Low

---

#### C4. Reasoning and Thinking Guidance — Score: 1/5
**Status**: Minimal — no chain-of-thought, no reasoning phases, no thinking budget
**Evidence**:
- `src/services/insight/insight_service.py:298` — `kwargs: dict = {"max_tokens": 2000}`; only output cap configured
- `src/services/prompts/insight_system.txt:10-18` — three output sections (not reasoning phases)
- `src/services/prompts/rag_system.txt:36-40` — three post-hoc reminders, not pre-reasoning steps
- No temperature guidance, no thinking budget, no "think step by step" instruction
**Action Plan**:
- Add reasoning preamble to `insight_system.txt`: "Before writing, identify: (1) dominant emotional pattern, (2) strongest behavioral evidence, (3) most actionable gap"
- Configure temperature per use-case (coaching ~0.7, factual RAG ~0.3) and document rationale
- Consider structured scratchpad section the model fills before final output
**Effort**: Low

---

#### C5. Guardrails and Boundary Control — Score: 2/5
**Status**: Basic — output format constraints; no hallucination prevention or scope limits
**Evidence**:
- `src/services/prompts/insight_system.txt:17-19` — "不超過 300 字\n以純文字輸出，不使用 Markdown 語法"
- `src/services/insight/insight_service.py:17` — `_THINK_RE` strips `<think>` tags from output
- `src/services/insight/insight_service.py:148` — edge-case fallback: "（用戶未留下筆記，請根據統計數據生成洞察）"
- No "NEVER fabricate data" instruction; user notes interpolated directly into prompt without injection warning
**Action Plan**:
- Add to `insight_system.txt`: "NEVER invent data, dates, or quotes not present in input. If missing, say so."
- Add scope limit: "Only write the three required sections. Do not add extra sections."
- Add prompt injection warning for user note field (untrusted input directly interpolated into prompt)
- Add similar guardrails to `rag_system.txt`
**Effort**: Low

---

#### C6. Tone, Style and User Adaptation — Score: 2/5
**Status**: Basic — language + basic tone specified; no verbosity control or user adaptation
**Evidence**:
- `src/services/prompts/insight_system.txt:1` — "請使用繁體中文（台灣用語）回覆。"
- `src/services/prompts/insight_system.txt:14` — "直接稱呼「你」，語氣溫暖但不浮誇"
- `src/services/prompts/rag_system.txt:1` — `{style_section}` placeholder exists but never populated (dead code)
- No user expertise adaptation; fixed 300-word cap; no per-session style configuration
**Action Plan**:
- Implement `{style_section}` with at least 2 styles: "brief" (150 words, 3 bullets) and "detailed" (300 words, prose)
- Add user expertise adaptation using checkin history length as experience proxy
- Add explicit emoji policy: "do not use emojis"
- Add formatting guidance: "Write in continuous prose paragraphs, not bullet lists"
**Effort**: Medium

---

## Action Plan (Priority Order)

| Priority | Dimension | Current | Target | Effort | Impact |
|----------|-----------|---------|--------|--------|--------|
| 1 | A5 Error Handling & Resilience | 2/5 | 4/5 | Low | High — `tenacity` retry is ~10 lines, prevents transient failures |
| 2 | A4 Config Layering (`lru_cache`) | 3/5 | 4/5 | Low | High — one-line fix, avoids rebuilding Settings on every call |
| 3 | C3 Few-Shot Examples | 1/5 | 3/5 | Low | High — add 2 examples to insight_system.txt, immediate quality boost |
| 4 | C4 Reasoning Guidance | 1/5 | 3/5 | Low | High — add reasoning preamble, cost ~5 words added to prompt |
| 5 | C5 Guardrails | 2/5 | 4/5 | Low | High — hallucination prevention + injection guard, low effort |
| 6 | B1 Context Assembly (system param) | 2/5 | 3/5 | Medium | High — pass system via `system=` enables Anthropic prompt caching |
| 7 | B10 Cache Strategy (prompt cache) | 2/5 | 4/5 | Medium | High — Anthropic prompt caching reduces input token cost ~90% for static portion |
| 8 | A5 Resilience (fallback chain) | 2/5 | 4/5 | Medium | High — fallback model chain prevents outage when primary provider fails |
| 9 | B7 RAG (uncomment Qdrant + fix bug) | 2/5 | 3/5 | Medium | High — infrastructure already built; just needs wiring |
| 10 | A3 Tool System | 2/5 | 4/5 | High | Critical — enables LLM function-calling for structured AI workflows |
| 11 | B4 Conversation History | 0/5 | 3/5 | High | High — enables multi-turn chat; prerequisite for B9 |
| 12 | A19 Concurrency (`asyncio.gather`) | 2/5 | 4/5 | Medium | Medium — parallelizes insight generation, reduces scheduled job wall time |
| 13 | A17 Command System | 1/5 | 3/5 | Low | Medium — unify operational scripts into `src/cli/` |
| 14 | A21 Prompt History (audit trail) | 0/5 | 2/5 | Low | Medium — versioning for admin prompt changes |
