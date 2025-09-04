from typing import Optional, List, Any
from pydantic import BaseModel

class CursorInfo(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None

class CursorPaginationInfo(BaseModel):
    cursors: Optional[CursorInfo] = None
    hasPrev: Optional[bool] = False
    hasNext: Optional[bool] = False
    count: Optional[int] = 0

class ErrorInfo(BaseModel):
    code: str
    message: str
    details: Optional[dict] = None

class APIResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[ErrorInfo] = None
    pagination: Optional[CursorPaginationInfo] = None
    timestamp: str
    requestId: str
    cacheHit: bool = False
    processingTime: int = 0
