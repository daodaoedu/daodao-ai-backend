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
    practiceId: str  # practice.external_id (UUID)，用於 feedback API
    targetId: int    # practice.id，用於 exclude_ids 參數
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
    practiceId: str
    feedbackState: FeedbackState
