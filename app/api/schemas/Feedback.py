from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class GenerateFeedbackRequest(BaseModel):
    reviewId: int
    style: Optional[str] = None
    thinkingMethod: Optional[str] = None


class GenerateFeedbackResponse(BaseModel):
    feedbackId: str
    content: str
    # generatedAt: datetime


class FeedbackDetailResponse(BaseModel):
    feedbackId: int
    reviewId: int
    style: Optional[str]
    thinkingMethod: Optional[str]
    content: str
    tokenUsage: float
    createdAt: datetime


class RateFeedbackRequest(BaseModel):
    rating: int  # 1~5
