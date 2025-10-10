from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Enum,
    UniqueConstraint, CheckConstraint, func
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from .base import Base  # 你自己的 Base 模組（共用 declarative_base()）

# =========================================================
# Enum 定義
# =========================================================

class EntityTagType(str, enum.Enum):
    RESOURCE = "resource"
    IDEA = "idea"
    PROJECT = "project"
    PRACTICE = "practice"
    CIRCLE = "circle"
    USER = "user"

# =========================================================
# EntityTag 模型
# =========================================================

class EntityTag(Base):
    __tablename__ = "entity_tags"

    id = Column(Integer, primary_key=True, index=True, comment="唯一識別碼")

    entity_type = Column(Enum(EntityTagType), nullable=False, comment="實體類型")
    entity_id = Column(Integer, nullable=False, comment="實體ID")

    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, comment="標籤ID")
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="建立者ID")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="建立時間")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="最後更新時間")

    # 關聯：使用字串延遲解析，避免循環 import
    tag = relationship("Tag", back_populates="entity_links", lazy="joined")
    creator = relationship("User", back_populates="created_tags", lazy="joined")

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "tag_id", name="uq_entity_tag"),
        CheckConstraint(
            "entity_type IN ('resource', 'idea', 'project', 'practice', 'circle', 'user')",
            name="check_entity_type_valid"
        ),
    )
