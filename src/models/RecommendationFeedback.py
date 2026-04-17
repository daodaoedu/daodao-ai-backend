from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, TIMESTAMP, func

from src.models.base import Base


class RecommendationFeedback(Base):
    __tablename__ = "recommendation_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_type = Column(String(50), nullable=False)
    target_id = Column(Integer, nullable=False)
    feedback_type = Column(String(20), nullable=False)
    is_hidden = Column(Boolean, nullable=False, default=False)
    source = Column(String(100), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now())
