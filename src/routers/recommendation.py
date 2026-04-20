import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from src.dependencies import CacheDep, SessionDep, UserDep
from src.logger import AppLogger
from src.middleware.limiter import limiter
from src.response_template import api_response_decorator
from src.schemas.api_response import build_success_response
from src.schemas.dashboard_recommendation import RecommendationFeedbackRequest
from src.schemas.pageInfo import APIResponse
from src.services.dashboard_recommendation_service import (
    get_topic_cards,
    submit_feedback,
)
from src.services.recommendation_service import get_recommendation_feed

logger = AppLogger(__name__).get_logger()

router = APIRouter(prefix="/v1/recommendation", tags=["recommendation"])

RECOMMENDATION_FEED_TTL = 60  # 1 分鐘


@router.get("/rank_feed", response_model=APIResponse)
@limiter.limit("60/minute")
@api_response_decorator
def recommendation_feed(
    request: Request,
    session: SessionDep,
    cache: CacheDep,
    after_id: Optional[int] = Query(
        None, description="上一次最後一筆的 id，作為 cursor"
    ),
    page_size: int = Query(20, description="每頁抓幾筆"),
    type: Optional[str] = Query(None, description="要抓哪些類型的 feed"),
):
    """
    推薦 feed API
    example:
    curl -X GET "http://localhost:8002/api/v1/recommendation/rank_feed?page_size=10" \
    -H "Authorization: Bearer <YOUR_TOKEN_ID>"
    """
    cache_key = f"recommendation_feed:after:{after_id or 0}:size:{page_size}:type:{type or 'all'}"

    cached = cache.client.get(cache_key)
    if cached:
        try:
            payload = json.loads(cached)
            logger.info(f"recommendation_feed cache_hit key={cache_key}")
            return {**payload, "cache_hit": True}
        except Exception:
            logger.warning(f"cache parse error for key={cache_key}, falling back to DB")

    posts, pagination = get_recommendation_feed(session, after_id, page_size, type)
    logger.info(
        f"recommendation_feed count={len(posts)}, next_cursor={pagination.cursors}"
    )

    payload = {
        "data": [p.model_dump() for p in posts],
        "pagination": pagination.model_dump(),
    }
    try:
        cache.client.set(
            cache_key, json.dumps(payload, default=str), ex=RECOMMENDATION_FEED_TTL
        )
    except Exception:
        logger.warning(f"cache write error for key={cache_key}, skipping cache")

    return {**payload, "cache_hit": False}


@router.get("/topic_cards")
@limiter.limit("30/minute")
def topic_cards(
    request: Request,
    session: SessionDep,
    user_id: UserDep,
    limit: int = Query(3, ge=1, le=10, description="回傳卡片數量"),
    exclude_ids: List[int] = Query([], description="排除的 practice id 清單"),
):
    """
    首頁個人化推薦主題卡片

    回傳與使用者興趣、專業領域或進行中主題相關的推薦卡片。
    已 hidden / dislike 的目標會自動排除。
    """
    if not user_id:
        return build_success_response(data=[])

    cards = get_topic_cards(session, user_id, limit=limit, exclude_ids=exclude_ids)
    return build_success_response(data=[c.model_dump() for c in cards])


@router.post("/topic_cards/{practice_id}/feedback")
@limiter.limit("60/minute")
def topic_card_feedback(
    request: Request,
    practice_id: str,
    body: RecommendationFeedbackRequest,
    session: SessionDep,
    user_id: UserDep,
):
    """
    對推薦卡片送出 like / dislike 回饋

    - like 再按一次 → 切換回 neutral
    - dislike 會同時標記 hidden，下次推薦自動排除
    """
    if not user_id:
        raise HTTPException(
            status_code=401, detail="Authentication required"
        )  # feedback 需要登入

    result = submit_feedback(session, user_id, practice_id, body.feedbackType)
    return build_success_response(data=result.model_dump())
