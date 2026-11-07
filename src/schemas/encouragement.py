from typing import Optional

from pydantic import BaseModel, Field


class GenerateEncouragementRequest(BaseModel):
    mood: Optional[str] = Field(None, max_length=20)
    note: Optional[str] = Field(None, max_length=600)
    practiceTitle: str = Field(..., max_length=100)
    learnerNickname: Optional[str] = Field(None, max_length=255)


class GenerateEncouragementResponse(BaseModel):
    draft: str
