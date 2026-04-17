from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class FeedbackState(str, Enum):
    LIKED = "liked"
    DISLIKED = "disliked"
    NEUTRAL = "neutral"


class FeedbackType(str, Enum):
    LIKE = "like"
    DISLIKE = "dislike"


class CreatorInfo(BaseModel):
    id: int
    name: str
    photo_url: Optional[str] = None


class TopicCardItem(BaseModel):
    recommendationId: str
    targetType: str
    targetId: int
    title: str
    description: Optional[str] = None
    creator: CreatorInfo
    tags: List[str]
    matchReasonCode: str
    matchReasonText: str
    feedbackState: FeedbackState
    isAiGenerated: bool = False


class RecommendationFeedbackRequest(BaseModel):
    feedbackType: FeedbackType


class RecommendationFeedbackResponse(BaseModel):
    recommendationId: str
    feedbackState: FeedbackState
