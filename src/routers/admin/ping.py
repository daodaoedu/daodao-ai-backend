from fastapi import APIRouter

from src.dependencies import AdminDep, SessionDep
from src.response_template import api_response_decorator

router = APIRouter()


@router.get("/ping")
@api_response_decorator
def admin_ping(admin: AdminDep, db: SessionDep) -> dict:
    """Admin health check — 驗證 JWT 與 admin role。"""
    return {
        "data": {
            "status": "ok",
            "admin_id": admin.id,
            "admin_mongo_id": admin.mongo_id,
            "nickname": admin.nickname,
        },
        "pagination": None,
        "cache_hit": False,
    }
