import uuid
from datetime import UTC, datetime
from typing import Any, Optional

from src.schemas.pageInfo import APIResponse, CursorPaginationInfo, ErrorInfo


def build_meta(extra: dict = None) -> dict:
    """統一處理 meta 欄位"""
    meta = {
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "requestId": f"req-{uuid.uuid4()}",
    }
    if extra:
        meta.update(extra)
    return meta


def _normalize_pagination(pagination: Any) -> Optional[dict]:
    if pagination is None:
        return None
    if isinstance(pagination, CursorPaginationInfo):
        return pagination.model_dump()
    if isinstance(pagination, dict):
        return CursorPaginationInfo.model_validate(pagination).model_dump()
    return None


def build_success_response(
    data: Any = None,
    pagination: Optional[Any] = None,
    cache_hit: bool = False,
    processing_time: int = 0,
) -> dict:
    """成功回傳統一格式"""
    resp = APIResponse(
        success=True,
        data=data,
        error=None,
        pagination=_normalize_pagination(pagination),
        cacheHit=cache_hit,
        processingTime=processing_time,
        **build_meta(),
    )
    return resp.model_dump()


def build_error_response(
    code: str = "INTERNAL_ERROR",
    message: str = "Unexpected error",
    details: Optional[dict] = None,
) -> dict:
    """錯誤回傳統一格式"""
    error = ErrorInfo(code=code, message=message, details=details)
    resp = APIResponse(
        success=False,
        data=None,
        error=error,
        pagination=None,
        cacheHit=False,
        processingTime=0,
        **build_meta(),
    )
    return resp.model_dump()
