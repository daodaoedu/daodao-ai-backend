from typing import List

from pydantic import BaseModel


class FeedItem(BaseModel):
    id: str
    type: str
    model_config = {"from_attributes": True}


class FeedInfo(BaseModel):
    id: str
    type: str
    title: str
    score: float
    freshness_score: float
    activity_score: float


class FeedResponse(BaseModel):
    items: List[FeedItem]
