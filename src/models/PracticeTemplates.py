from enum import Enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    TIMESTAMP,
    ARRAY,
    CheckConstraint,
    func,
)

from src.models.base import Base


class PracticeTimePeriod(str, Enum):
    MORNING = "morning"
    COMMUTE = "commute"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class PracticeTemplate(Base):
    __tablename__ = "practice_templates"

    id = Column(Integer, primary_key=True)

    external_id = Column(
        String, unique=True, nullable=False, server_default=func.gen_random_uuid()
    )

    # ===== Template Basic Info =====
    title = Column(String(100), nullable=False)

    practice_action = Column(Text)

    # ===== Execution Settings =====
    duration_days = Column(Integer)

    frequency_min_days = Column(Integer)

    frequency_max_days = Column(Integer)

    session_duration_minutes = Column(Integer)

    practice_time_periods = Column(ARRAY(String), nullable=True)

    other_context = Column(Text)

    # ===== timestamps =====
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "duration_days IN (7,14,21,30)", name="chk_template_duration_days"
        ),
        CheckConstraint(
            "session_duration_minutes IN (15,30,45,60)",
            name="chk_template_session_duration",
        ),
        CheckConstraint(
            "frequency_max_days >= frequency_min_days",
            name="chk_template_frequency_days",
        ),
    )
