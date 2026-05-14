from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel


class AIQueryLogRead(BaseModel):
    id: int
    request_id: UUID
    backend: str
    model_name: Optional[str]
    context: Optional[str]
    user_id: Optional[int]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int]
    cost_usd: Optional[Decimal]
    latency_ms: Optional[int]
    status: str
    error_message: Optional[str]
    prompt_chars: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class AIQueryLogDetail(AIQueryLogRead):
    """包含完整 usage_detail JSONB 的詳細回應。"""

    usage_detail: Optional[Dict[str, Any]]


class OffsetPagination(BaseModel):
    total_count: int
    limit: int
    offset: int
    has_next: bool
