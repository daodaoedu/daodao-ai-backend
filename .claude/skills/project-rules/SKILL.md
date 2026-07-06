---
name: project-rules
description: daodao-ai-backend 專案開發規範，涵蓋 FastAPI 模式、資料庫、API 格式、程式碼風格
---

# daodao-ai-backend 專案規範

## 技術棧

Python 3.12（Makefile/CI 綁定 3.12，儘管 pyproject 寫 `>=3.10`）、FastAPI、SQLAlchemy（PostgreSQL）、Redis（**啟動硬依賴**，不健康 app 直接中止）、Prometheus。

Qdrant（向量搜尋）與 ClickHouse（分析）**目前停用**——lifespan 與 dependencies 中已註解，重新啟用前先恢復初始化（見 codebase-map）。

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

- `make format` — Ruff + Black 自動修復
- `make check` — Black --check + Ruff check（**與 CI 相同門檻，這是實質強制的檢查**）
- `make lint` — Pylint + Bandit（皆 `|| true` 非阻斷，CI 也不跑 pylint，僅供參考）
- `.pylintrc` 停用：missing docstrings、too-few-public-methods、import-error

### 工具鏈版本鎖定（踩過的坑，必守）

CI 精確 pin `black==25.9`、`ruff==0.14.1`（`.github/workflows/ci.yml`），但 pyproject 只給下界——black 25.9 與 26.x 對多行字串縮排結果不同，版本不對齊會導致 CI 反覆紅。本地安裝：

```
uv pip install "black==25.9" "ruff==0.14.1"
```

版本以 CI workflow 檔為準；若 CI 改版，本條要同步更新。
