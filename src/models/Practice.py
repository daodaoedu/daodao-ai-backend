from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    Date,
    DECIMAL,
    TIMESTAMP,
    ForeignKey,
    ARRAY,
    CheckConstraint,
    func,
)
from sqlalchemy.orm import relationship


from src.models.base import Base

# =========================================================
# Practices 模型
# =========================================================
from enum import Enum


class PracticeStatus(str, Enum):
    DRAFT = "draft"
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class PracticePrivacyStatus(str, Enum):
    PRIVATE = "private"
    PUBLIC = "public"
    DELAYED = "delayed"


class Practice(Base):
    __tablename__ = "practices"

    id = Column(Integer, primary_key=True)

    external_id = Column(String, unique=True, server_default=func.gen_random_uuid())

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    template_id = Column(
        Integer, ForeignKey("practice_templates.id", ondelete="SET NULL"), nullable=True
    )

    title = Column(String(100), nullable=False)

    practice_action = Column(Text)

    # ===== 時間 =====
    start_date = Column(Date)
    duration_days = Column(Integer)

    end_date = Column(Date)

    # ===== session =====
    session_duration_minutes = Column(Integer)

    frequency_min_days = Column(Integer)
    frequency_max_days = Column(Integer)

    practice_time_periods = Column(ARRAY(String))

    other_context = Column(Text)

    insight = Column(Text, nullable=True)  # AI 生成的成長洞察（排程寫入）

    # ===== 狀態 =====
    status = Column(String(20), default=PracticeStatus.DRAFT.value)

    privacy_status = Column(String(20), default=PracticePrivacyStatus.PRIVATE.value)

    has_resources = Column(Boolean, default=False)

    theme_color = Column(String(20))

    # ===== progress =====
    progress_percentage = Column(DECIMAL(5, 2), default=0)

    first_checkin_at = Column(TIMESTAMP(timezone=True))

    # ===== timestamps =====
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())

    deleted_at = Column(TIMESTAMP(timezone=True))

    user = relationship("User", back_populates="practices")

    # ===== Constraints =====
    __table_args__ = (
        CheckConstraint("duration_days IN (7,14,21,30)", name="chk_duration_days"),
        CheckConstraint(
            "session_duration_minutes IN (15,30,45,60)", name="chk_session_duration"
        ),
        CheckConstraint(
            "frequency_max_days >= frequency_min_days", name="chk_frequency_days"
        ),
    )
