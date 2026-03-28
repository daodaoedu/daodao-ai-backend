from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class LLMModelCreate(BaseModel):
    provider: str = Field(..., max_length=50)
    model_name: str = Field(..., max_length=200)
    display_name: Optional[str] = Field(None, max_length=200)
    is_active: bool = True
    input_cost_per_1m: Decimal = Decimal("0")
    output_cost_per_1m: Decimal = Decimal("0")
    cached_input_cost_per_1m: Decimal = Decimal("0")
    notes: Optional[str] = None


class LLMModelUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None
    input_cost_per_1m: Optional[Decimal] = None
    output_cost_per_1m: Optional[Decimal] = None
    cached_input_cost_per_1m: Optional[Decimal] = None
    notes: Optional[str] = None


class LLMModelRead(BaseModel):
    id: int
    provider: str
    model_name: str
    display_name: Optional[str]
    is_active: bool
    input_cost_per_1m: Decimal
    output_cost_per_1m: Decimal
    cached_input_cost_per_1m: Decimal
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}
