from sqlalchemy import (
    Column, Integer, Text)
from sqlalchemy.orm import relationship
from models import Base


class AIFeedback(Base):
    __tablename__ = "ai_feedbacks"
    id = Column(Integer, primary_key=True, index=True)
    # review_id = Column(Integer, ForeignKey("learning_reviews.id"), unique=True)
    content = Column(Text)
    # review = relationship("LearningReview", back_populates="feedback")
