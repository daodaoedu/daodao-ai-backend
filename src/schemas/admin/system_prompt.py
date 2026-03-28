from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SystemPromptCreate(BaseModel):
    name: str = Field(..., max_length=200)
    content: str
    is_active: bool = False


class SystemPromptUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    is_active: Optional[bool] = None


class SystemPromptRead(BaseModel):
    id: int
    name: str
    content: str
    is_active: bool
    version: int
    created_by: Optional[int]
    updated_by: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}
