from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class AIServiceConfigCreate(BaseModel):
    service: str = Field(..., max_length=100)
    name: str = Field(..., max_length=200)
    model_id: int
    system_prompt_id: Optional[int] = None
    max_tokens: Optional[int] = Field(None, ge=1, le=32000)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    top_k: Optional[int] = Field(None, ge=1, le=200)
    is_active: bool = False
    notes: Optional[str] = None


class AIServiceConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    model_id: Optional[int] = None
    system_prompt_id: Optional[int] = None
    max_tokens: Optional[int] = Field(None, ge=1, le=32000)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    top_k: Optional[int] = Field(None, ge=1, le=200)
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class AIServiceConfigRead(BaseModel):
    id: int
    service: str
    name: str
    model_id: int
    system_prompt_id: Optional[int]
    max_tokens: Optional[int]
    temperature: Optional[Decimal]
    top_p: Optional[Decimal]
    top_k: Optional[int]
    is_active: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}
