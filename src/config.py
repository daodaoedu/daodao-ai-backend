import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


# 根據環境變數決定讀取的 env 檔案
_ENV = os.getenv("ENVIRONMENT", "development")
_ENV_FILE = ".env.prod" if _ENV == "production" else ".env.dev"


class BaseConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=[_ENV_FILE, ".env", str(ENV_FILE_PATH)],
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
        env_file=[_ENV_FILE, ".env", str(ENV_FILE_PATH)],
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
        env_file=[_ENV_FILE, ".env", str(ENV_FILE_PATH)],
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
        env_file=[_ENV_FILE, ".env", str(ENV_FILE_PATH)],
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
        env_file=[_ENV_FILE, ".env", str(ENV_FILE_PATH)],
        env_prefix="INSIGHT__",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    schedule_cron: str = "0 1 * * *"  # 預設每天 01:00 UTC
    llm_backend: str = "groq"  # 預設使用 Groq


_LLM_BACKEND_DEFAULTS: Dict[str, Dict[str, str]] = {
    "ollama": {"url": "http://ollama-dev:11434/api/generate", "model": "qwen2.5:1.5b"},
    "openai": {"url": "https://api.openai.com/v1/responses", "model": "gpt-4o"},
    "gemini": {
        "url": "https://generativelanguage.googleapis.com",
        "model": "gemini-2.5-flash",
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "model": "claude-3-5-sonnet-20241022",
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
    },
    "cloudflare": {
        "url": "https://api.cloudflare.com/client/v4/accounts/PLACEHOLDER/ai/v1",
        "model": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    },
    "nvidia": {
        "url": "https://integrate.api.nvidia.com/v1",
        "model": "meta/llama-3.3-70b-instruct",
    },
    "cerebras": {
        "url": "https://api.cerebras.ai/v1",
        "model": "llama3.1-8b",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "ollama_cloud": {
        "url": "https://ollama.com/v1",
        "model": "gpt-oss:120b",
    },
}


class Settings(BaseConfigSettings):
    model_config = SettingsConfigDict(
        env_file=[_ENV_FILE, ".env", str(ENV_FILE_PATH)],
        extra="ignore",
        frozen=True,
        env_nested_delimiter="__",
        case_sensitive=False,
        validate_assignment=True,
    )

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
            k: LLMBackendConfig(**v) for k, v in _LLM_BACKEND_DEFAULTS.items()
        }
    )

    @model_validator(mode="before")
    @classmethod
    def _merge_llm_backend_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        llm_data = data.get("llm_backend")
        if not llm_data or not isinstance(llm_data, dict):
            return data
        merged: Dict[str, Dict] = {k: dict(v) for k, v in _LLM_BACKEND_DEFAULTS.items()}
        for provider, cfg in llm_data.items():
            if isinstance(cfg, dict):
                merged.setdefault(provider, {})
                merged[provider].update(
                    {k: v for k, v in cfg.items() if v is not None and v != ""}
                )
        data["llm_backend"] = merged
        return data

    jwt_security: str = "xxxxxxxxxxxxxxxx"
    jwt_expiration: str = "1h"

    # Qdrant
    qdrant_url: str = "http://qdrant-dev:6333"
    collection_name: str = "daodao_collection"

    #
    cloudflare_account_id: str = ""
    api_secret_key: str = "xxxxxxxxxxxxxxxx"

    @model_validator(mode="after")
    def _inject_cloudflare_account_id(self) -> "Settings":
        if self.cloudflare_account_id:
            cf_cfg = self.llm_backend.get("cloudflare")
            if cf_cfg and "PLACEHOLDER" in cf_cfg.url:
                # LLMBackendConfig is frozen, rebuild
                object.__setattr__(
                    self,
                    "llm_backend",
                    {
                        **self.llm_backend,
                        "cloudflare": LLMBackendConfig(
                            url=cf_cfg.url.replace(
                                "PLACEHOLDER", self.cloudflare_account_id
                            ),
                            model=cf_cfg.model,
                            api_key=cf_cfg.api_key,
                        ),
                    },
                )
        return self

    @model_validator(mode="after")
    def _validate_secrets(self) -> "Settings":
        if self.environment in ("production", "staging"):
            if self.jwt_security == "xxxxxxxxxxxxxxxx":
                raise ValueError(
                    "JWT_SECURITY must be configured (currently using placeholder)"
                )
            if self.api_secret_key == "xxxxxxxxxxxxxxxx":
                raise ValueError(
                    "API_SECRET_KEY must be configured (currently using placeholder)"
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


if __name__ == "main":
    # --- 使用方式 ---
    settings = Settings()
    print(settings.redis_url)
    print(settings.llm_backend["openai"].url)
