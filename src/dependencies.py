from typing import Annotated, Generator

from fastapi import Depends, HTTPException, Request, status
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

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    # def get_current_user(authorization: Optional[str] = Header(None)):

    """
    FastAPI Dependency: 驗證 JWT 並回傳 payload
    """
    token = credentials.credentials  # 自動取 token，不用 Bearer 前綴
    try:
        decoded = verify(token)  # 這裡可能丟錯誤
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,  # token 無效/過期。
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not decoded:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,  # 有 token，但驗證不通過（可能缺權限）。
            detail="Could not validate credentials",
        )

    return decoded.get("_id", "unknown")


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

LLMDep = Annotated[LLMClient, Depends(get_llm_client)]

QdrantDep = Annotated[QdrantClient, Depends(get_qdrant_client)]
CacheDep = Annotated[CacheClient, Depends(get_cache_client)]
ClickHouseDep = Annotated[ClickHouseClient, Depends(get_clickhouse_client)]

DatabaseDep = Annotated[BaseDatabase, Depends(get_database_postgres)]
SessionDep = Annotated[Session, Depends(get_db_session)]
UserDep = Annotated[str, Depends(get_current_user)]
