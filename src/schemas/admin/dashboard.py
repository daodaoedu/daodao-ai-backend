from decimal import Decimal
from typing import List

from pydantic import BaseModel


class BackendStat(BaseModel):
    backend: str
    query_count: int
    cost_usd: Decimal
    total_tokens: int


class DailyStatPoint(BaseModel):
    date: str  # "YYYY-MM-DD"
    cost_usd: Decimal
    query_count: int
    total_tokens: int


class DashboardStatsRead(BaseModel):
    total_cost_usd: Decimal
    total_queries: int
    total_input_tokens: int
    total_output_tokens: int
    by_backend: List[BackendStat]
    daily_series: List[DailyStatPoint]
