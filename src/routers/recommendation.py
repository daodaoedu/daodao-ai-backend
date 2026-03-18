import json
from typing import Optional

from fastapi import APIRouter, Query, Request

from src.dependencies import CacheDep, SessionDep
from src.logger import AppLogger
from src.middleware.limiter import limiter
from src.response_template import api_response_decorator
from src.schemas.pageInfo import APIResponse
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
        payload = json.loads(cached)
        logger.info(f"recommendation_feed cache_hit key={cache_key}")
        return {**payload, "cache_hit": True}

    posts, pagination = get_recommendation_feed(session, after_id, page_size, type)
    logger.info(
        f"recommendation_feed count={len(posts)}, next_cursor={pagination.cursors}"
    )

    payload = {
        "data": [p.dict() for p in posts],
        "pagination": pagination.model_dump(),
    }
    cache.client.set(
        cache_key, json.dumps(payload, default=str), ex=RECOMMENDATION_FEED_TTL
    )

    return {**payload, "cache_hit": False}
