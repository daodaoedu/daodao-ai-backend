import os
from pathlib import Path
from typing import Dict, Literal, Optional

from pydantic import Field
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

    url: str = "redis://localhost:6379/0"

    # Cache settings
    ttl_hours: int = 6  # Cache TTL in hours


class PostgreSQLSettings(BaseSettings):
    """PostgreSQL configuration settings."""

    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="POSTGRES_",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    # database_url: str = Field(
    #     default="postgresql+psycopg2://username:passweord@localhost:5432/db",
    #     description="PostgreSQL database URL",
    # )
    db_user: str = Field(default="postgres", description="PostgreSQL username")
    db_password: str = Field(default="", description="PostgreSQL password")
    db_host: str = Field(default="localhost", description="PostgreSQL host")
    db_port: int = Field(default=5432, description="PostgreSQL port")
    db_name: str = Field(default="postgres", description="PostgreSQL database name")

    echo_sql: bool = Field(default=False, description="Enable SQL query logging")
    pool_size: int = Field(default=20, description="Database connection pool size")
    max_overflow: int = Field(default=0, description="Maximum pool overflow")


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


class InsightSettings(BaseConfigSettings):
    """精選洞察排程設定"""

    model_config = SettingsConfigDict(
        env_file=[".env", str(ENV_FILE_PATH)],
        env_prefix="INSIGHT__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    schedule_cron: str = "0 1 * * *"  # 預設每天 01:00 UTC
    llm_backend: str = "gemini"  # 預設使用 Gemini


class Settings(BaseConfigSettings):
    app_version: str = "0.1.0"
    debug: bool = True
    environment: Literal["development", "staging", "production"] = "development"
    service_name: str = "daodao-ai-backend-api"

    redis: RedisSettings = Field(default_factory=RedisSettings)
    postgresql: PostgreSQLSettings = Field(default_factory=PostgreSQLSettings)
    clickhouse: ClickHouseSettings = Field(default_factory=ClickHouseSettings)
    insight: InsightSettings = Field(default_factory=InsightSettings)

    llm_backend: Dict[str, LLMBackendConfig] = Field(
        default_factory=lambda: {
            "ollama": LLMBackendConfig(
                url="http://ollama-dev:11434/api/generate",
                model="phi3:mini",
            ),
            "openai": LLMBackendConfig(
                url="https://api.openai.com/v1/responses",
                model="gpt-4o",
                api_key=os.getenv("OPENAI_API_KEY"),
            ),
            "gemini": LLMBackendConfig(
                url="https://generativelanguage.googleapis.com",
                model="gemini-2.0-flash",
                api_key=os.getenv("GEMINI_API_KEY"),
            ),
            "anthropic": LLMBackendConfig(
                url="https://api.anthropic.com/v1/messages",
                model="claude-3-5-sonnet-20241022",
                api_key=os.getenv("ANTHROPIC_API_KEY"),
            ),
        }
    )

    jwt_security: str = "xxxxxxxxxxxxxxxx"
    jwt_expiration: str = "1h"

    class Config:
        validate_assignment = True  # 允許設定後驗證

    # Qdrant
    qdrant_url: str = "http://qdrant-dev:6333"
    collection_name: str = "daodao_collection"

    #
    api_secret_key: str = "xxxxxxxxxxxxxxxx"


def get_settings() -> Settings:
    return Settings()


if __name__ == "main":
    # --- 使用方式 ---
    settings = Settings()
    print(settings.redis_url)
    print(settings.llm_backend["openai"].url)
