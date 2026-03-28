---
name: project-rules
description: daodao-ai-backend 專案開發規範，涵蓋 FastAPI 模式、資料庫、API 格式、程式碼風格
---

# daodao-ai-backend 專案規範

## 技術棧

Python 3.12、FastAPI、SQLAlchemy（PostgreSQL）、Redis、Qdrant（向量搜尋）、ClickHouse（分析）、Prometheus。

## 專案結構

```
src/
├── main.py              # FastAPI app + lifespan
├── config.py            # Pydantic Settings
├── dependencies.py      # FastAPI DI
├── response_template.py # API response decorator
├── models/              # SQLAlchemy ORM
├── schemas/             # Pydantic request/response
├── routers/             # API route handlers
├── services/            # Business logic + 外部服務 client
├── db/                  # Database factories
├── middleware/          # CORS, rate limit, logging, API key
└── utils/               # Helpers, enums, ORM converters
```

## 路由模式

所有路由 `async def`，用 `Annotated` + `Depends()` 注入依賴：

```python
@router.get("/users/{user_id}")
@api_response_decorator
async def get_user(user_id: str, session: SessionDep) -> dict:
    ...
```

- `@api_response_decorator` 統一 response 格式
- `@observe_api` 做 observability

## API Response 格式

統一 wrapper：`{ success, data, error, pagination, cacheHit, processingTime, timestamp, requestId }`

分頁：cursor-based（`after_id`），用 `CursorPaginationInfo`。

## 設定管理

Pydantic `BaseSettings` + `.env`，`frozen=True`：

```python
from src.config import get_settings
settings = get_settings()
```

prefix-based parsing：`POSTGRES_*`、`REDIS_*`、`QDRANT_*`。

## 資料庫

- SQLAlchemy declarative base（`models/base.py`）
- Session 透過 `SessionDep` dependency 注入
- ORM → dict 轉換用 `orm_to_dict()`

## 快取

Redis with TTL constants per endpoint，cache miss 時 log warning 不 raise error。

## Validation

Pydantic v2 schemas + FastAPI `Query()` constraints：

```python
@router.get("/search")
async def search(q: str = Query(min_length=1, max_length=100)):
    ...
```

## 程式碼風格

- Full type hints（parameters + return types）
- `Optional[T]` for nullable
- snake_case functions、PascalCase classes、UPPERCASE constants
- 中英混合 comments
- Models 檔名 PascalCase（`User.py`）

## Lint / Format

- `make format` — Ruff + Black
- `make check` — 檢查格式
- `make lint` — Pylint + Bandit
- `.pylintrc` 停用：missing docstrings、too-few-public-methods、import-error
