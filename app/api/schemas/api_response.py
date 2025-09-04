from datetime import datetime
import uuid
from typing import Any, Optional, Dict, Union
from api.schemas.pageInfo import CursorInfo, CursorPaginationInfo, ErrorInfo, APIResponse


def build_meta(extra: dict = None) -> dict:
    """統一處理 meta 欄位"""
    meta = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "requestId": f"req-{uuid.uuid4().hex[:8]}",
    }
    if extra:
        meta.update(extra)
    return meta


def build_success_response(
    data: Any = None,
    pagination: Optional[CursorPaginationInfo] = None,
    cache_hit: bool = False,
    processing_time: int = 0
) -> dict:
    """成功回傳統一格式"""
    resp = APIResponse(
        success=True,
        data=data,
        error=None,
        pagination=pagination,
        cacheHit=cache_hit,
        processingTime=processing_time,
        **build_meta()
    )
    return resp.dict()


def build_error_response(
    code: str = "INTERNAL_ERROR",
    message: str = "Unexpected error",
    details: Optional[dict] = None
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
        **build_meta()
    )
    return resp.dict()