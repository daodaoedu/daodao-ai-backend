from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from src.dependencies import AdminDep, SessionDep
from src.models.User import User
from src.models.UserTokenQuota import UserTokenQuota
from src.response_template import api_response_decorator
from src.schemas.admin.user_quota import (
    UserQuotaRead,
    UserQuotaUpsert,
    UserWithQuotaRead,
)

router = APIRouter()


def _get_current_month_tokens(db, user_id: int) -> int:
    """計算該 user 當月已使用的 total_tokens。"""
    # 透過 mongo_id join AIQueryLog（AIQueryLog 存的是 mongo_id）
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.mongo_id:
        return 0

    row = db.execute(
        text(
            """
            SELECT COALESCE(SUM(total_tokens), 0) AS used
            FROM admin_ai_query_logs
            WHERE user_mongo_id = :mongo_id
              AND DATE_TRUNC('month', created_at AT TIME ZONE 'UTC')
                  = DATE_TRUNC('month', NOW() AT TIME ZONE 'UTC')
            """
        ),
        {"mongo_id": user.mongo_id},
    ).fetchone()
    return int(row.used) if row else 0


@router.get("/users")
@api_response_decorator
def list_users_with_quota(
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="搜尋 nickname 或 mongo_id"),
) -> dict:
    """列出所有用戶（含當月 token 使用量與配額）。"""
    query = db.query(User)
    if search:
        query = query.filter(
            User.nickname.ilike(f"%{search}%") | User.mongo_id.ilike(f"%{search}%")
        )

    total = query.count()
    users = query.order_by(User.id.desc()).offset(offset).limit(limit).all()

    result = []
    for user in users:
        quota = (
            db.query(UserTokenQuota)
            .filter(
                UserTokenQuota.user_id == user.id, UserTokenQuota.quota_month.is_(None)
            )
            .first()
        )
        used = _get_current_month_tokens(db, user.id)
        result.append(
            UserWithQuotaRead(
                id=user.id,
                mongo_id=user.mongo_id,
                nickname=getattr(user, "nickname", None),
                external_id=str(user.external_id) if user.external_id else None,
                role_id=user.role_id,
                current_month_tokens_used=used,
                quota=UserQuotaRead.model_validate(quota) if quota else None,
            ).model_dump()
        )

    return {
        "data": result,
        "pagination": {
            "total_count": total,
            "limit": limit,
            "offset": offset,
            "has_next": (offset + limit) < total,
        },
        "cache_hit": False,
    }


@router.get("/users/{user_id}/quota")
@api_response_decorator
def get_user_quota(
    user_id: int,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    """取得用戶的配額設定與當月使用量。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    quota = (
        db.query(UserTokenQuota)
        .filter(UserTokenQuota.user_id == user_id, UserTokenQuota.quota_month.is_(None))
        .first()
    )
    used = _get_current_month_tokens(db, user_id)

    return {
        "data": {
            "user_id": user_id,
            "current_month_tokens_used": used,
            "quota": (
                UserQuotaRead.model_validate(quota).model_dump() if quota else None
            ),
        },
        "pagination": None,
        "cache_hit": False,
    }


@router.put("/users/{user_id}/quota")
@api_response_decorator
def upsert_user_quota(
    user_id: int,
    body: UserQuotaUpsert,
    admin: AdminDep,  # noqa: ARG001
    db: SessionDep,
) -> dict:
    """設定（upsert）用戶 token 配額。"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    quota = (
        db.query(UserTokenQuota)
        .filter(
            UserTokenQuota.user_id == user_id,
            UserTokenQuota.quota_month == body.quota_month,
        )
        .first()
    )

    if quota:
        quota.monthly_token_limit = body.monthly_token_limit
        quota.daily_token_limit = body.daily_token_limit
        quota.is_enforced = body.is_enforced
    else:
        quota = UserTokenQuota(
            user_id=user_id,
            monthly_token_limit=body.monthly_token_limit,
            daily_token_limit=body.daily_token_limit,
            quota_month=body.quota_month,
            is_enforced=body.is_enforced,
        )
        db.add(quota)

    db.commit()
    db.refresh(quota)
    return {
        "data": UserQuotaRead.model_validate(quota).model_dump(),
        "pagination": None,
        "cache_hit": False,
    }
