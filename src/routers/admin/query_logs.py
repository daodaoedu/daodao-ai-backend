from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.dependencies import AdminDep, SessionDep
from src.models.AIQueryLog import AIQueryLog
from src.response_template import api_response_decorator
from src.schemas.admin.query_log import (
    AIQueryLogDetail,
    AIQueryLogRead,
    OffsetPagination,
)

router = APIRouter()


@router.get("/query-logs")
@api_response_decorator
def list_query_logs(
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    backend: Optional[str] = Query(None),
    context: Optional[str] = Query(None),
    user_mongo_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """AI 查詢日誌列表（offset 分頁 + 多重篩選）。"""
    query = db.query(AIQueryLog)

    if backend:
        query = query.filter(AIQueryLog.backend == backend)
    if context:
        query = query.filter(AIQueryLog.context == context)
    if user_mongo_id:
        query = query.filter(AIQueryLog.user_mongo_id == user_mongo_id)
    if status:
        query = query.filter(AIQueryLog.status == status)
    if date_from:
        query = query.filter(AIQueryLog.created_at >= date_from)
    if date_to:
        query = query.filter(AIQueryLog.created_at < f"{date_to} 23:59:59.999999+00")

    total_count = query.count()
    logs = (
        query.order_by(AIQueryLog.created_at.desc()).offset(offset).limit(limit).all()
    )

    data: List[AIQueryLogRead] = [AIQueryLogRead.model_validate(log) for log in logs]
    pagination = OffsetPagination(
        total_count=total_count,
        limit=limit,
        offset=offset,
        has_next=(offset + limit) < total_count,
    )

    return {
        "data": [d.model_dump() for d in data],
        "pagination": pagination.model_dump(),
        "cache_hit": False,
    }


@router.get("/query-logs/{log_id}")
@api_response_decorator
def get_query_log(
    log_id: int,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    """單筆查詢日誌（含完整 usage_detail）。"""
    log = db.query(AIQueryLog).filter(AIQueryLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail=f"Query log {log_id} not found")

    return {
        "data": AIQueryLogDetail.model_validate(log).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }
