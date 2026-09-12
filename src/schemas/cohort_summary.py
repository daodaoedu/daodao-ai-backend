from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class CohortSummaryCohort(BaseModel):
    """場次基本資訊（由 daodao-server 組好後傳入）"""

    name: str = Field(..., max_length=200)
    programName: Optional[str] = Field(default=None, max_length=200)
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    phase: Literal["not_started", "in_progress", "ended"] = "in_progress"
    participants: int = 0
    checkins: int = 0


class CohortSummaryEntry(BaseModel):
    """一筆去識別化後的打卡筆記或留言"""

    participant: str = Field(
        ..., max_length=50, description="去識別化後的稱呼，例：參與者 3"
    )
    practice: str = Field(default="", max_length=200)
    date: str = Field(default="", max_length=40)
    kind: Literal["checkin", "comment"] = "checkin"
    mood: Optional[str] = Field(default=None, max_length=40)
    # 與 daodao-server 留言上限（5000）一致；超出 prompt 預算的部分由 _build_prompt 截掉
    text: str = Field(..., min_length=1, max_length=5000)


class GenerateCohortSummaryRequest(BaseModel):
    cohort: CohortSummaryCohort
    entries: List[CohortSummaryEntry] = Field(..., min_length=1, max_length=400)
    # 組織自帶 key：provider + apiKey 一起給才會用；否則走平台預設 backend
    provider: Optional[str] = Field(default=None, max_length=40)
    apiKey: Optional[str] = Field(default=None, min_length=8, max_length=512)

    @model_validator(mode="after")
    def _provider_and_key_together(self) -> "GenerateCohortSummaryRequest":
        if bool(self.provider) != bool(self.apiKey):
            raise ValueError("provider 與 apiKey 必須同時提供，或都不提供（走平台 AI）")
        return self


class GenerateCohortSummaryResponse(BaseModel):
    summary: str
    provider: str
    model: str
    usage: Dict[str, Any] = Field(default_factory=dict)
    promptVersion: str
