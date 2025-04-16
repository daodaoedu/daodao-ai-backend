from sqlalchemy import (
    Column, Integer, Text, ForeignKey, Float, TIMESTAMP, func)
from sqlalchemy.orm import relationship
from models import Base
from sqlalchemy.dialects.postgresql import UUID
import uuid

class AIReviewFeedback(Base):
    __tablename__ = "ai_review_feedbacks"
    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("review.id"), unique=True)
    task_id = Column(UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False)
    content = Column(Text)
    token_usage = Column(Float, default=0)
    style = Column(Text)
    thinking_method = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    review = relationship("Review", back_populates="ai_feedback")
