from typing import Optional

from pydantic import BaseModel, Field


class PlaygroundChatRequest(BaseModel):
    model_id: int = Field(..., description="llm_models.id")
    system_prompt_id: Optional[int] = Field(None, description="system_prompts.id，不填則無 system prompt")
    message: str = Field(..., min_length=1, description="使用者輸入的訊息")


class PlaygroundChatResponse(BaseModel):
    response: str
    model_used: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
