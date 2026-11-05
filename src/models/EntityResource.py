from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base

if TYPE_CHECKING:
    pass


# =========================================================
# EntityResource 模型
# =========================================================


class EntityResource(Base):
    __tablename__ = "entity_resources"

    id = Column(Integer, primary_key=True, index=True, comment="關聯記錄唯一識別碼")
    external_id = Column(
        UUID(as_uuid=True),
        unique=True,
        default=uuid4,
        comment="外部API使用的UUID識別碼",
    )

    # 關聯對象
    resource_id = Column(
        Integer,
        ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        comment="關聯的學習資源ID",
    )

    # 多型關聯欄位
    entity_type = Column(
        String(20),
        nullable=False,
        default="idea",
        comment="實體類型：practice、project、idea",
    )
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('practice','idea','project')",
            name="ck_entity_resource_type",
        ),
    )

    entity_id = Column(Integer, nullable=False, comment="實體ID，支援UUID或數字ID格式")

    # 關聯資訊
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="建立關聯的使用者ID",
    )
    note = Column(Text, nullable=True, comment="使用者對此資源關聯的個人備註")

    day_number = Column(
        Integer,
        nullable=True,
        comment="指定資源於實踐第幾天使用（1–91）；NULL代表整段期間",
    )

    # 系統欄位
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), comment="關聯建立時間"
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, comment="最後更新時間")
    deleted_at = Column(DateTime(timezone=True), nullable=True, comment="軟刪除時間")

    # 關聯
    resource = relationship("Resource", back_populates="entity_links")
    creator = relationship("User", back_populates="created_entity_resources")

    # 唯一性約束及資源使用天數範圍
    __table_args__ = (
        UniqueConstraint(
            "resource_id", "entity_type", "entity_id", name="uq_resource_entity"
        ),
        CheckConstraint(
            "day_number BETWEEN 1 AND 91", name="entity_resources_day_number_check"
        ),
    )
