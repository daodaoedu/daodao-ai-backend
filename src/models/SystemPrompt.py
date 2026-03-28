from sqlalchemy import Boolean, Column, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.sql import func

from src.models.base import Base


class SystemPrompt(Base):
    __tablename__ = "system_prompts"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 人類可讀的唯一識別名稱，如 "insight-v2", "rag-default"
    name = Column(String(200), nullable=False, unique=True)

    content = Column(Text, nullable=False)

    is_active = Column(Boolean, nullable=False, default=False)

    # 每次更新 content 時 +1
    version = Column(Integer, nullable=False, default=1)

    created_by = Column(String(255), nullable=True)  # User.mongo_id
    updated_by = Column(String(255), nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (UniqueConstraint("name", name="uq_admin_system_prompts_name"),)

    def __repr__(self) -> str:
        return f"<SystemPrompt id={self.id} name={self.name} active={self.is_active}>"
