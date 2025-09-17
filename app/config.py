import os

from pathlib import Path
from typing import Literal, Optional, Dict
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


class BaseConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        extra="ignore",
        frozen=True,
        env_nested_delimiter="__",
        case_sensitive=False,
    )


class LLMBackendConfig(BaseConfigSettings):
    url: str
    model: str
    api_key: Optional[str] = None



class RedisSettings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="REDIS_",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    url : str = "redis://localhost:6379/0"
    

    # Cache settings
    ttl_hours: int = 6  # Cache TTL in hours


class PostgreSQLSettings(BaseSettings):
    """PostgreSQL configuration settings."""

    database_url: str = Field(
        default="postgresql+psycopg2://username:passweord@localhost:5432/db", description="PostgreSQL database URL"
    )
    echo_sql: bool = Field(default=False, description="Enable SQL query logging")
    pool_size: int = Field(default=20, description="Database connection pool size")
    max_overflow: int = Field(default=0, description="Maximum pool overflow")

    class Config:
        env_prefix = "POSTGRES_"


class ClickHouseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="CLICKHOUSE_",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )
    host: str = Field(default="localhost", description="ClickHouse 伺服器主機位址")
    port: int = Field(default=9000, description="ClickHouse 伺服器連接埠")
    user: str = Field(default="default", description="ClickHouse 使用者帳號")
    password: str = Field(default="", description="ClickHouse 使用者密碼")
    database: str = Field(default="default", description="ClickHouse 資料庫名稱")
    
    
class Settings(BaseConfigSettings):
    app_version: str = "0.1.0"
    debug: bool = True
    environment: Literal["development", "staging", "production"] = "development"
    service_name: str = "daodao-ai-backend-api"
    
    redis: RedisSettings = Field(default_factory=RedisSettings)
    postgresql: PostgreSQLSettings = Field(default_factory=PostgreSQLSettings)
    clickhouse:ClickHouseSettings = Field(default_factory=ClickHouseSettings)
    
    
    llm_backend : Dict[str, LLMBackendConfig] = Field(
        default_factory=lambda: {
            "ollama": LLMBackendConfig(
                url="http://ollama-dev:11434/api/generate",
                model="phi3:mini",
            ),
            # "openai": LLMBackendConfig(
            #     url="https://api.openai.com/v1/responses",
            #     model="gpt-4",
            #     api_key=os.getenv("OPENAI_API_KEY"),
            # ),
            "gemini": LLMBackendConfig(
                url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
                model="gemini",
                api_key=os.getenv("GEMINI_API_KEY"),
            ),
            # "grok": LLMBackendConfig(
            #     url="https://api.x.ai/v1/chat/completions",
            #     model="grok-2-latest",
            #     api_key=os.getenv("GROK_API_KEY"),
            # ),
        }
    )
    


    database_url : str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://username:passweord@localhost:5432/db"
    )
    
    jwt_security: str = "xxxxxxxxxxxxxxxx"
    jwt_expiration: str = "1h"
    
    
    class Config:
        validate_assignment = True  # 允許設定後驗證
        
    # Qdrant
    qdrant_url: str = "http://qdrant-dev:6333"
    collection_name: str = "arxiv_collection"
    
        
    
def get_settings() -> Settings:
    return Settings()   
        
        
if __name__ == "main":
    # --- 使用方式 ---
    settings = Settings()
    print(settings.redis_url)
    print(settings.llm_backend["openai"].url)
