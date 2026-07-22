from typing import Optional

from pydantic import BaseModel


class GenerateEncouragementRequest(BaseModel):
    mood: Optional[str] = None
    note: Optional[str] = None
    practiceTitle: str
    learnerNickname: Optional[str] = None


class GenerateEncouragementResponse(BaseModel):
    draft: str
