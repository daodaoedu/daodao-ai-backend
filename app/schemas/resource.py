from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, HttpUrl


class ResourceBase(BaseModel):
    name: str
    url: HttpUrl
    image_url: Optional[HttpUrl]
    description: str
    video_url: Optional[HttpUrl]
    type: str
    cost: str
    level: str


class ResourceCreate(ResourceBase):
    major_category_id: Optional[int]
    sub_category_id: Optional[int]


class ResourceOut(ResourceBase):
    id: int
    external_id: UUID
    created_by: int
    major_category_id: Optional[int]
    sub_category_id: Optional[int]
    status: str
    created_at: datetime

    class Config:
        orm_mode = True


class TopReviewOut(BaseModel):
    review_id: int
    learning_review: int
    learning_feedback: Optional[str]
    created_at: datetime
    resource_id: int
    resource_name: str
    resource_url: str


class TopContributorOut(BaseModel):
    id: int
    nickname: Optional[str]
    resource_count: int


class TopCategoryOut(BaseModel):
    id: int
    name: str
    resource_count: int
