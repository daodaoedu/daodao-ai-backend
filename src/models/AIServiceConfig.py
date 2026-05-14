from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.sql import func

from src.models.base import Base


class AIServiceConfig(Base):
    __tablename__ = "ai_service_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 服務識別碼，如 'insight' / 'feed' / 'chat_reply'
    service = Column(String(100), nullable=False)

    # 版本名稱，供管理介面辨識
    name = Column(String(200), nullable=False)

    model_id = Column(
        Integer, ForeignKey("llm_models.id", ondelete="RESTRICT"), nullable=False
    )
    system_prompt_id = Column(
        Integer, ForeignKey("system_prompts.id", ondelete="SET NULL"), nullable=True
    )

    # 生成參數（None 表示使用 backend 預設值）
    max_tokens = Column(Integer, nullable=True)
    temperature = Column(Numeric(4, 2), nullable=True)
    top_p = Column(Numeric(4, 2), nullable=True)
    top_k = Column(Integer, nullable=True)

    # 每個 service 最多一筆 is_active=True（由 DB partial unique index 強制）
    is_active = Column(Boolean, nullable=False, default=False)

    notes = Column(Text, nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        Index("idx_ai_service_configs_service", "service"),
        Index("idx_ai_service_configs_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<AIServiceConfig id={self.id} service={self.service} name={self.name} active={self.is_active}>"
