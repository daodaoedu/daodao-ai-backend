from api.schemas.recommendation import FeedItem, FeedResponse
from api.schemas.api_response import APIResponse
from api.verify_jwt import get_current_user  # 你的 JWT Dependency
from core.limiter import limiter
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from logger import AppLogger
from services.rank_feed import get_feed  # 你的 get_feed 函式
from api.template import api_response_decorator
from dependencies import UserDep 

logger = AppLogger(__name__).get_logger()


router = APIRouter(prefix="/recommendation", tags=["recommendation"])


@router.post("/rank_feed", response_model=APIResponse)
@limiter.limit("5/minute")
@api_response_decorator
def recommendation_feed(
    request: Request, 
    current_user: UserDep,
    limit: int = Query(100, description="最多取得幾筆 feed"),
):
    """
    推薦 feed API
    - JWT 驗證透過 get_current_user 自動處理
    - current_user 內含 token payload
    example:
    curl -X POST "http://localhost:8002/api/recommendation/rank_feed?limit=10" \
    -H "accept: application/json" \
    -H "Authorization: Bearer <YOUR_TOKEN_ID>"

    """

    logger.info(f"current_user:  {current_user}")

    try:
        top_feed = get_feed(limit=limit)

        # 只取 id 與 type
        filtered_feed = [FeedItem(id=item.id, type=item.type) for item in top_feed]
    
        logger.info(f"recommendation_feed result: {len(filtered_feed)}")

    except Exception as e:
        logger.info(f"recommendation_feed error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"items": filtered_feed}
