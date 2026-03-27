from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PracticeInsightResponse(BaseModel):
    id: int
    practice_id: int
    content: str
    llm_backend: str
    llm_cost: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}
