import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import text

from src.dependencies import AdminDep, CacheDep, SessionDep
from src.response_template import api_response_decorator
from src.schemas.admin.dashboard import BackendStat, DailyStatPoint, DashboardStatsRead

router = APIRouter()

_DASHBOARD_TTL = 300  # 5 分鐘


@router.get("/dashboard/stats")
@api_response_decorator
def get_dashboard_stats(
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    cache: CacheDep,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD，預設 7 天前"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD，預設今天"),
) -> dict:
    """Dashboard 聚合統計：總費用、查詢數、token 數、按 backend 分組、每日趨勢。"""
    # 預設日期範圍：最近 7 天
    _date_to = date_to or date.today().isoformat()
    _date_from = date_from or (date.today() - timedelta(days=6)).isoformat()

    cache_key = f"admin:dashboard:{_date_from}:{_date_to}"
    cached = cache.client.get(cache_key)
    if cached:
        return {"data": json.loads(cached), "pagination": None, "cache_hit": True}

    # 整體統計
    total_row = db.execute(
        text(
            """
            SELECT
                COALESCE(SUM(cost_usd), 0)        AS total_cost_usd,
                COUNT(*)                           AS total_queries,
                COALESCE(SUM(input_tokens), 0)    AS total_input_tokens,
                COALESCE(SUM(output_tokens), 0)   AS total_output_tokens
            FROM admin_ai_query_logs
            WHERE created_at >= :date_from::date
              AND created_at <  :date_to::date + INTERVAL '1 day'
            """
        ),
        {"date_from": _date_from, "date_to": _date_to},
    ).fetchone()

    # 按 backend 分組
    backend_rows = db.execute(
        text(
            """
            SELECT
                backend,
                COUNT(*)                        AS query_count,
                COALESCE(SUM(cost_usd), 0)     AS cost_usd,
                COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM admin_ai_query_logs
            WHERE created_at >= :date_from::date
              AND created_at <  :date_to::date + INTERVAL '1 day'
            GROUP BY backend
            ORDER BY cost_usd DESC
            """
        ),
        {"date_from": _date_from, "date_to": _date_to},
    ).fetchall()

    # 每日趨勢
    daily_rows = db.execute(
        text(
            """
            SELECT
                DATE_TRUNC('day', created_at AT TIME ZONE 'UTC')::date AS day,
                COUNT(*)                        AS query_count,
                COALESCE(SUM(cost_usd), 0)     AS cost_usd,
                COALESCE(SUM(total_tokens), 0) AS total_tokens
            FROM admin_ai_query_logs
            WHERE created_at >= :date_from::date
              AND created_at <  :date_to::date + INTERVAL '1 day'
            GROUP BY day
            ORDER BY day ASC
            """
        ),
        {"date_from": _date_from, "date_to": _date_to},
    ).fetchall()

    result = DashboardStatsRead(
        total_cost_usd=Decimal(str(total_row.total_cost_usd)),
        total_queries=total_row.total_queries,
        total_input_tokens=total_row.total_input_tokens,
        total_output_tokens=total_row.total_output_tokens,
        by_backend=[
            BackendStat(
                backend=r.backend,
                query_count=r.query_count,
                cost_usd=Decimal(str(r.cost_usd)),
                total_tokens=r.total_tokens,
            )
            for r in backend_rows
        ],
        daily_series=[
            DailyStatPoint(
                date=str(r.day),
                cost_usd=Decimal(str(r.cost_usd)),
                query_count=r.query_count,
                total_tokens=r.total_tokens,
            )
            for r in daily_rows
        ],
    )

    payload = result.model_dump(mode="json")
    cache.client.set(cache_key, json.dumps(payload, default=str), ex=_DASHBOARD_TTL)
    return {"data": payload, "pagination": None, "cache_hit": False}
