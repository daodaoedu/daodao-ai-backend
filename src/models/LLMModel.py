from sqlalchemy import (
    Boolean,
    Column,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.sql import func

from src.models.base import Base


class LLMModel(Base):
    __tablename__ = "llm_models"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Provider: "openai", "gemini", "anthropic", "groq", "ollama"
    provider = Column(String(50), nullable=False)

    # 模型識別碼，如 "gpt-4o", "gemini-2.0-flash", "llama-3.3-70b-versatile"
    model_name = Column(String(200), nullable=False)

    # 顯示名稱（UI 用）
    display_name = Column(String(200), nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    # 費率：USD per 1M tokens（用 Numeric 避免浮點漂移）
    input_cost_per_1m = Column(Numeric(12, 6), nullable=False, default=0)
    output_cost_per_1m = Column(Numeric(12, 6), nullable=False, default=0)
    cached_input_cost_per_1m = Column(Numeric(12, 6), nullable=False, default=0)

    notes = Column(Text, nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "provider", "model_name", name="uq_admin_llm_models_provider_model"
        ),
        Index("ix_admin_llm_models_provider", "provider"),
        Index("ix_admin_llm_models_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<LLMModel id={self.id} provider={self.provider} model={self.model_name}>"
        )
