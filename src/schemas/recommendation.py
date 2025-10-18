from typing import List

from pydantic import BaseModel


class FeedItem(BaseModel):
    id: int
    type: str
    model_config = {"from_attributes": True}


class FeedInfo(BaseModel):
    id: int
    type: str
    title: str
    score: float
    freshness_score: float
    activity_score: float


class FeedResponse(BaseModel):
    items: List[FeedItem]
