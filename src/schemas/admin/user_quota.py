from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserQuotaRead(BaseModel):
    id: int
    user_id: int
    monthly_token_limit: int
    daily_token_limit: Optional[int]
    quota_month: Optional[int]
    is_enforced: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class UserQuotaUpsert(BaseModel):
    monthly_token_limit: int = Field(..., gt=0)
    daily_token_limit: Optional[int] = Field(None, gt=0)
    quota_month: Optional[int] = None  # YYYYMM，NULL = 永久預設
    is_enforced: bool = True


class UserWithQuotaRead(BaseModel):
    id: int
    mongo_id: Optional[str]
    nickname: Optional[str]
    external_id: Optional[str]
    role_id: Optional[int]
    current_month_tokens_used: int
    quota: Optional[UserQuotaRead]

    model_config = {"from_attributes": True}
