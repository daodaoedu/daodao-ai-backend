from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class FeedRankingConfigCreate(BaseModel):
    name: str = Field(..., max_length=200)
    w_social: float = Field(0.35, ge=0.0, le=10.0)
    w_engagement: float = Field(0.30, ge=0.0, le=10.0)
    w_content: float = Field(0.15, ge=0.0, le=10.0)
    w_decay: float = Field(0.20, ge=0.0, le=10.0)
    w_freshness: float = Field(0.30, ge=0.0, le=10.0)
    freshness_window_hours: int = Field(72, ge=1, le=720)
    is_active: bool = False
    notes: Optional[str] = None


class FeedRankingConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    w_social: Optional[float] = Field(None, ge=0.0, le=10.0)
    w_engagement: Optional[float] = Field(None, ge=0.0, le=10.0)
    w_content: Optional[float] = Field(None, ge=0.0, le=10.0)
    w_decay: Optional[float] = Field(None, ge=0.0, le=10.0)
    w_freshness: Optional[float] = Field(None, ge=0.0, le=10.0)
    freshness_window_hours: Optional[int] = Field(None, ge=1, le=720)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class FeedRankingConfigRead(BaseModel):
    id: int
    name: str
    w_social: Decimal
    w_engagement: Decimal
    w_content: Decimal
    w_decay: Decimal
    w_freshness: Decimal
    freshness_window_hours: int
    is_active: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}
