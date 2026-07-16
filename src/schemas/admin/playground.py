from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"] = Field(..., description="發話方")
    content: str = Field(..., min_length=1, max_length=8000, description="訊息內容")


class PlaygroundChatRequest(BaseModel):
    model_id: int = Field(..., description="llm_models.id")
    system_prompt_id: Optional[int] = Field(
        None, description="system_prompts.id，不填則無 system prompt"
    )
    message: str = Field(
        ..., min_length=1, max_length=8000, description="使用者輸入的訊息"
    )
    history: Optional[list[ChatTurn]] = Field(
        None,
        max_length=60,
        description="先前的對話紀錄（依時間先後排序），提供時進行多輪對話",
    )
    max_tokens: Optional[int] = Field(
        None, ge=1, le=32000, description="最大輸出 token 數"
    )
    temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0, description="溫度（0=確定性，2=最隨機）"
    )
    top_p: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Nucleus sampling（0–1）"
    )
    top_k: Optional[int] = Field(None, ge=1, le=200, description="Top-K sampling")


class PlaygroundChatResponse(BaseModel):
    response: str
    model_used: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int


class PlaygroundInsightRequest(BaseModel):
    practice_id: int
    model_id: int
    save: bool = False
    system_prompt_id: Optional[int] = None
    system_prompt_override: Optional[str] = None
    include_user_profile: bool = True
    include_practice_info: bool = True
    include_checkin_stats: bool = True
    include_notable_notes: bool = True
    max_tokens: Optional[int] = Field(
        None, ge=1, le=32000, description="最大輸出 token 數"
    )
    temperature: Optional[float] = Field(
        None, ge=0.0, le=2.0, description="溫度（0=確定性，2=最隨機）"
    )
    top_p: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Nucleus sampling（0–1）"
    )
    top_k: Optional[int] = Field(None, ge=1, le=200, description="Top-K sampling")


class SaveInsightRequest(BaseModel):
    practice_id: int
    insight: str


class InsightCheckinStats(BaseModel):
    total: int
    max_streak: int
    top_weekdays: list[str]
    mood_summary: str


class PlaygroundInsightResponse(BaseModel):
    insight: str
    prompt_used: str
    checkin_stats: InsightCheckinStats
    user_profile_used: dict
    model_used: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    saved: bool
