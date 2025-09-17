from typing import Annotated, Generator


from sqlalchemy.orm import Session
from db.interface_db import BaseDatabase

from config import Settings, get_settings
from fastapi import Depends, Request
from services.cache.client import CacheClient
from services.llm.client import LLMClient
from services.qdrant.client import QdrantClient



def get_database(request: Request) -> BaseDatabase:
    """Get database from the request state."""
    return request.app.state.database


def get_db_session(database: Annotated[BaseDatabase, Depends(get_database)]) -> Generator[Session, None, None]:
    """Get database session dependency."""
    with database.get_session() as session:
        yield session




def get_llm_client(request: Request) -> LLMClient:
    """Get Ollama client from the request state."""
    return request.app.state.llm_client


def get_qdrant_client(request: Request) -> QdrantClient:
    """Get OpenSearch client from the request state."""
    return request.app.state.qdrant_client



# Dependency annotations


SettingsDep = Annotated[Settings, Depends(get_settings)]

LLMDep = Annotated[LLMClient, Depends(get_llm_client)]

QdrantDep = Annotated[QdrantClient, Depends(get_qdrant_client)]

DatabaseDep = Annotated[BaseDatabase, Depends(get_database)]
SessionDep = Annotated[Session, Depends(get_db_session)]
