import enum
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base

# =========================================================
# Enum 定義
# =========================================================


class IdeaStatus(str, enum.Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"


# =========================================================
# Ideas 模型
# =========================================================


class Idea(Base):
    __tablename__ = "ideas"

    id = Column(Integer, primary_key=True, index=True, comment="創意想法唯一識別碼")
    external_id = Column(
        UUID(as_uuid=True), unique=True, default=uuid4, comment="外部唯一識別碼（UUID）"
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="發布者ID",
    )

    content = Column(Text, nullable=False, comment="創意想法內容")
    status = Column(
        Enum(IdeaStatus, name="idea_status"),
        default=IdeaStatus.ACTIVE,
        nullable=False,
        comment="狀態：active、draft、archived",
    )

    has_resources = Column(Boolean, default=False, comment="是否有關聯資源")

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), comment="建立時間"
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, comment="更新時間")
    deleted_at = Column(DateTime(timezone=True), nullable=True, comment="軟刪除時間")

    version = Column(Integer, default=1, comment="版本號")

    # Relationship (假設有 User 模型)
    user = relationship("User", back_populates="ideas")
