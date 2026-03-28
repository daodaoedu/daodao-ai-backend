from typing import Annotated, Generator, Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db.interface_db import BaseDatabase
from src.db.postgresql import PostgreSQLDatabase
from src.services.cache.client import CacheClient
from src.services.clickhouse.client import ClickHouseClient
from src.services.llm.client import LLMClient
from src.services.qdrant.client import QdrantClient
from src.verify_jwt import verify

security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Optional[str]:
    # def get_current_user(authorization: Optional[str] = Header(None)):

    """
    FastAPI Dependency: 驗證 JWT 並回傳 payload
    """

    # ⭐ 無 token → 無痕模式
    if credentials is None:
        return None

    token = credentials.credentials

    try:
        decoded = verify(token)

        if not decoded:
            return None

        return decoded.get("_id")

    except Exception:
        return None


def get_database(request: Request) -> BaseDatabase:
    """Get database from the request state."""
    return request.app.state.database


def get_database_postgres(request: Request) -> PostgreSQLDatabase:
    """Get PostgreSQLDatabase from app state."""
    db = request.app.state.database
    if not isinstance(db, PostgreSQLDatabase):
        raise RuntimeError("Database is not a PostgreSQLDatabase instance")
    return db


def get_db_session(
    database: Annotated[PostgreSQLDatabase, Depends(get_database)],
) -> Generator[Session, None, None]:
    """Get database session dependency."""
    with database.get_session() as session:
        yield session


def get_cache_client(request: Request) -> CacheClient:
    """Get Ollama client from the request state."""
    return request.app.state.cache_client


def get_llm_client(request: Request) -> LLMClient:
    """Get Ollama client from the request state."""
    return request.app.state.llm_client


def get_qdrant_client(request: Request) -> QdrantClient:
    """Get OpenSearch client from the request state."""
    return request.app.state.qdrant_client


def get_clickhouse_client(request: Request) -> ClickHouseClient:
    return request.app.state.clickhouse_client


# Dependency annotations


SettingsDep = Annotated[Settings, Depends(get_settings)]

# LLMDep = Annotated[LLMClient, Depends(get_llm_client)]

# QdrantDep = Annotated[QdrantClient, Depends(get_qdrant_client)]
CacheDep = Annotated[CacheClient, Depends(get_cache_client)]
# ClickHouseDep = Annotated[ClickHouseClient, Depends(get_clickhouse_client)]

DatabaseDep = Annotated[BaseDatabase, Depends(get_database_postgres)]
SessionDep = Annotated[Session, Depends(get_db_session)]
UserDep = Annotated[Optional[str], Depends(get_current_user)]
