import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from src.dependencies import CacheDep, SessionDep, UserDep
from src.logger import AppLogger
from src.models.PracticeInsight import PracticeInsight
from src.models.User import User
from src.response_template import api_response_decorator
from src.schemas.insight import PracticeInsightResponse
from src.schemas.pageInfo import APIResponse

logger = AppLogger(__name__).get_logger()

router = APIRouter(prefix="/v1/users", tags=["insights"])

INSIGHTS_TTL = 300  # 5 分鐘快取


@router.get(
    "/insights",
    description="""
    取得當前登入用戶的精選洞察列表（需登入）。<br/>
    每個已完成的 Practice 會有一份由 AI 生成的個人成長洞察，
    每日 01:00 由排程自動生成。
    """,
    response_model=APIResponse,
)
@api_response_decorator
def get_my_insights(
    db: SessionDep,
    current_user: UserDep,
    cache: CacheDep,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
):
    if not current_user:
        raise HTTPException(status_code=401, detail="需要登入才能查看洞察")

    user: Optional[User] = (
        db.query(User).filter(User.external_id == current_user).first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="用戶不存在")

    cache_key = f"user_insights:{user.id}:{offset}:{limit}"
    cached = cache.client.get(cache_key)
    if cached:
        try:
            return {"data": json.loads(cached), "pagination": None, "cache_hit": True}
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(f"insight cache parse error key={cache_key}")

    stmt = (
        select(PracticeInsight)
        .where(PracticeInsight.user_id == user.id)
        .order_by(PracticeInsight.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    insights = list(db.execute(stmt).scalars().all())

    data = [
        PracticeInsightResponse.model_validate(ins).model_dump() for ins in insights
    ]

    cache.client.setex(cache_key, INSIGHTS_TTL, json.dumps(data, default=str))

    return {"data": data, "pagination": None, "cache_hit": False}
