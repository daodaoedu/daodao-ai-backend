from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from src.models.base import Base  # 避免循環 import

# -------------------------------------------------------------------
# 1. 資料庫設定 (使用 PostgreSQL)
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# 2. 資料庫模型定義
# -------------------------------------------------------------------


class Review(Base):
    __tablename__ = "review"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("post.id", ondelete="CASCADE"), nullable=False)
    mood = Column(String(20), nullable=False)
    mood_description = Column(Text, nullable=True)
    stress_level = Column(SmallInteger, nullable=False)
    learning_review = Column(SmallInteger, nullable=False)
    learning_feedback = Column(Text, nullable=True)
    adjustment_plan = Column(Text, nullable=True)
    visibility = Column(String(10), default="private")

    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # 關聯到 AIReviewFeedback
    ai_feedback = relationship(
        "AIReviewFeedback", back_populates="review", uselist=False
    )

    # 限制 mood 和 visibility
    __table_args__ = (
        CheckConstraint(mood.in_(["happy", "calm", "anxious", "tired", "frustrated"])),
        CheckConstraint("stress_level BETWEEN 1 AND 10"),
        CheckConstraint("learning_review BETWEEN 1 AND 10"),
        CheckConstraint(visibility.in_(["public", "private"])),
    )
