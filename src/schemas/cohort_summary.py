from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CohortSummaryCohort(BaseModel):
    """場次基本資訊（由 daodao-server 組好後傳入）"""

    name: str
    programName: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    phase: Literal["not_started", "in_progress", "ended"] = "in_progress"
    participants: int = 0
    checkins: int = 0


class CohortSummaryEntry(BaseModel):
    """一筆去識別化後的打卡筆記或留言"""

    participant: str = Field(..., description="去識別化後的稱呼，例：參與者 3")
    practice: str = ""
    date: str = ""
    kind: Literal["checkin", "comment"] = "checkin"
    mood: Optional[str] = None
    text: str = Field(..., min_length=1, max_length=2000)


class GenerateCohortSummaryRequest(BaseModel):
    cohort: CohortSummaryCohort
    entries: List[CohortSummaryEntry] = Field(..., min_length=1, max_length=400)
    # 組織自帶 key：provider + apiKey 一起給才會用；否則走平台預設 backend
    provider: Optional[str] = None
    apiKey: Optional[str] = Field(default=None, min_length=8, max_length=512)


class GenerateCohortSummaryResponse(BaseModel):
    summary: str
    provider: str
    model: str
    usage: Dict[str, Any] = Field(default_factory=dict)
    promptVersion: str
