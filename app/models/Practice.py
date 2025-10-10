import enum
from uuid import uuid4

from sqlalchemy import (
    DECIMAL,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base


class PracticeContentType(str, enum.Enum):
    BOOK = "book"
    VIDEO = "video"
    ARTICLES = "articles"
    PODCAST = "podcast"
    COURSE = "course"
    CUSTOM = "custom"


class PracticeStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class DailyGoalType(str, enum.Enum):
    TIME = "time"
    COMPLETION = "completion"


# =========================================================
# Practices 模型
# =========================================================


class Practice(Base):
    __tablename__ = "practices"

    id = Column(Integer, primary_key=True, index=True, comment="練習記錄ID")
    external_id = Column(
        UUID(as_uuid=True), unique=True, default=uuid4, comment="外部唯一識別碼"
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="練習者ID",
    )

    title = Column(String(100), nullable=False, comment="練習標題")

    content_type = Column(Enum(PracticeContentType), nullable=False, comment="內容類型")
    custom_content_type = Column(String(50), nullable=True, comment="自定義內容類型")

    total_amount = Column(Integer, nullable=False, comment="總目標數量")
    current_progress = Column(DECIMAL(10, 2), default=0, comment="目前進度")

    start_date = Column(Date, nullable=True, comment="開始日期")

    daily_goal_type = Column(
        Enum(DailyGoalType), nullable=False, comment="每日目標類型"
    )
    daily_goal_time_minutes = Column(
        Integer, nullable=True, comment="每日目標時間（分鐘）"
    )
    daily_goal_amount = Column(Integer, nullable=True, comment="每日目標數量")
    daily_goal_unit = Column(
        String(10), nullable=True, comment="每日目標單位（頁、章節等）"
    )

    practice_action = Column(Text, nullable=True, comment="練習行動描述")

    status = Column(
        Enum(PracticeStatus),
        default=PracticeStatus.ACTIVE,
        nullable=False,
        comment="狀態",
    )

    has_resources = Column(Boolean, default=False, comment="是否有關聯資源")

    streak = Column(Integer, default=0, comment="目前連續紀錄")
    max_streak = Column(Integer, default=0, comment="最高連續紀錄")

    last_checkin_date = Column(Date, nullable=True, comment="最後一次打卡日期")

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), comment="建立時間"
    )
    updated_at = Column(DateTime(timezone=True), nullable=True, comment="更新時間")
    deleted_at = Column(DateTime(timezone=True), nullable=True, comment="軟刪除時間")

    # Relationship
    user = relationship("User", back_populates="practices")

    # Constraints
    __table_args__ = (
        CheckConstraint("total_amount > 0", name="check_total_amount_positive"),
        CheckConstraint(
            "daily_goal_time_minutes BETWEEN 5 AND 240", name="check_goal_time_range"
        ),
        CheckConstraint(
            "daily_goal_amount BETWEEN 1 AND 100", name="check_goal_amount_range"
        ),
    )
