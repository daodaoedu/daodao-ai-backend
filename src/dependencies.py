import hmac
from typing import Annotated, Generator, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import String
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db.interface_db import BaseDatabase
from src.db.postgresql import PostgreSQLDatabase
from src.models.Role import Role
from src.models.User import User
from src.services.cache.client import CacheClient
from src.services.clickhouse.client import ClickHouseClient
from src.services.llm.client import LLMClient
from src.services.qdrant.client import QdrantClient
from src.verify_jwt import verify

security = HTTPBearer(auto_error=False)


SERVICE_TOKEN_HEADER = "X-Service-Token"
SERVICE_PRINCIPAL = "service:daodao-server"


def _service_token_matches(request: Request) -> bool:
    """daodao-server 服務間呼叫：X-Service-Token 與 API_SECRET_KEY 相同即視為已認證"""
    provided = request.headers.get(SERVICE_TOKEN_HEADER)
    if not provided:
        return False
    expected = get_settings().api_secret_key
    if not expected or expected == "xxxxxxxxxxxxxxxx":
        return False
    return hmac.compare_digest(provided, expected)


def require_service_caller(request: Request) -> str:
    """只允許帶正確 X-Service-Token 的服務間呼叫（daodao-server）；一般使用者 JWT 不足以呼叫"""
    if not _service_token_matches(request):
        raise HTTPException(status_code=403, detail="僅限 daodao-server 服務間呼叫")
    return SERVICE_PRINCIPAL


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Optional[str]:
    """
    FastAPI Dependency: 驗證 JWT 並回傳使用者識別
    優先讀 Authorization Bearer header，fallback 讀 auth_token cookie；
    daodao-server 轉發的 JWT 只有 PostgreSQL `id`（沒有 mongo `_id`），兩者都接受。
    服務間身份由 require_service_caller 另行驗證，不得取代使用者 JWT。
    """

    token: Optional[str] = None

    if credentials is not None:
        token = credentials.credentials
    else:
        # Fallback: 從 cookie 讀取（與 daodao-server 共用 auth_token）
        token = request.cookies.get("auth_token")

    if token:
        try:
            decoded = verify(token)
            if decoded:
                identity = decoded.get("_id") or decoded.get("id")
                if identity is not None:
                    return str(identity)
        except Exception:
            pass

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


def get_llm_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LLMClient:
    """建立 LLM client（使用 insight 預設 backend）。"""
    return LLMClient(settings, settings.insight.llm_backend)


def get_qdrant_client(request: Request) -> QdrantClient:
    """Get OpenSearch client from the request state."""
    return request.app.state.qdrant_client


def get_clickhouse_client(request: Request) -> ClickHouseClient:
    return request.app.state.clickhouse_client


def get_admin_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db_session),
) -> User:
    """
    FastAPI Dependency：驗證 JWT 存在且用戶 role.name == 'admin' / 'superadmin'。
    優先讀 Authorization Bearer header，fallback 讀 auth_token cookie。
    回傳 User ORM 物件供 admin routes 使用。

    查詢順序：
    1. JWT 的 id（PostgreSQL PK，最可靠）
    2. JWT 的 _id → mongo_id 欄位
    3. JWT 的 _id → external_id 欄位（UUID 格式 fallback）
    """
    token: Optional[str] = None
    if credentials is not None:
        token = credentials.credentials
    else:
        token = request.cookies.get("auth_token")

    if not token:
        raise HTTPException(
            status_code=403, detail="Admin access required: not authenticated"
        )

    decoded = verify(token)
    if not decoded:
        raise HTTPException(
            status_code=403, detail="Admin access required: invalid or expired token"
        )

    numeric_id = decoded.get("id")
    mongo_id = decoded.get("_id")

    user: Optional[User] = None
    if numeric_id:
        user = db.query(User).filter(User.id == int(numeric_id)).first()
    if user is None and mongo_id:
        user = db.query(User).filter(User.mongo_id == mongo_id).first()
    if user is None and mongo_id:
        user = db.query(User).filter(User.external_id.cast(String) == mongo_id).first()

    if user is None:
        raise HTTPException(
            status_code=403, detail="Admin access required: user not found"
        )

    role: Optional[Role] = db.query(Role).filter(Role.id == user.role_id).first()
    if role is None or role.name.lower() not in ("admin", "superadmin"):
        raise HTTPException(
            status_code=403, detail="Admin access required: insufficient permissions"
        )

    return user


# Dependency annotations


SettingsDep = Annotated[Settings, Depends(get_settings)]

LLMDep = Annotated[LLMClient, Depends(get_llm_client)]

# QdrantDep = Annotated[QdrantClient, Depends(get_qdrant_client)]
CacheDep = Annotated[CacheClient, Depends(get_cache_client)]
# ClickHouseDep = Annotated[ClickHouseClient, Depends(get_clickhouse_client)]

DatabaseDep = Annotated[BaseDatabase, Depends(get_database_postgres)]
SessionDep = Annotated[Session, Depends(get_db_session)]
UserDep = Annotated[Optional[str], Depends(get_current_user)]
AdminDep = Annotated[User, Depends(get_admin_user)]
