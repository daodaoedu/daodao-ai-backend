from enum import Enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    TIMESTAMP,
    ForeignKey,
    ARRAY,
    CheckConstraint,
    func,
    UniqueConstraint,
)
from src.models.base import Base


class CheckinMood(str, Enum):
    GIVE_UP = "give_up"
    FRUSTRATED = "frustrated"
    BORED = "bored"
    NEUTRAL = "neutral"
    GOOD = "good"
    HAPPY = "happy"


class PracticeCheckin(Base):
    __tablename__ = "practice_checkins"

    id = Column(Integer, primary_key=True)

    practice_id = Column(
        Integer, ForeignKey("practices.id", ondelete="CASCADE"), nullable=False
    )

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    checkin_date = Column(Date, nullable=False)

    mood = Column(String(20))

    note = Column(String(300))

    image_urls = Column(ARRAY(String))

    og_image_url = Column(String(500))

    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "practice_id", "user_id", "checkin_date", name="uq_practice_daily_checkin"
        ),
        CheckConstraint(
            "array_length(image_urls,1) <= 3 OR image_urls IS NULL",
            name="chk_checkin_image_limit",
        ),
    )
