from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PracticeInsightResponse(BaseModel):
    """
    精選洞察 API response。
    insight 欄位直接儲存於 practices 表，此 schema 從 Practice ORM 物件轉換。
    """

    id: int
    title: str
    insight: str
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
