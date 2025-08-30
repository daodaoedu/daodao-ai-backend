import uuid

from models import Base
from sqlalchemy import TIMESTAMP, Column, Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship


class AIReviewFeedback(Base):
    __tablename__ = "ai_review_feedbacks"
    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("review.id"), unique=True)
    task_id = Column(
        UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False
    )
    content = Column(Text)
    token_usage = Column(Float, default=0)
    style = Column(Text)
    thinking_method = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    review = relationship("Review", back_populates="ai_feedback")
