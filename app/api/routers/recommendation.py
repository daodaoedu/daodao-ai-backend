from api.schemas.recommendation import FeedItem, FeedResponse
from api.verify_jwt import get_current_user  # 你的 JWT Dependency
from fastapi import APIRouter, Depends, HTTPException, Query
from logger import AppLogger
from services.rank_feed import get_feed  # 你的 get_feed 函式

logger = AppLogger(__name__).get_logger()


router = APIRouter(prefix="/recommendation", tags=["recommendation"])


@router.get("/rank_feed", response_model=FeedResponse)
def recommendation_feed(
    limit: int = Query(100, description="最多取得幾筆 feed"),
    current_user: dict = Depends(get_current_user),  # 自動取得驗證後的 payload
):
    """
    推薦 feed API
    - JWT 驗證透過 get_current_user 自動處理
    - current_user 內含 token payload
    example:
    curl -H "Authorization: Bearer 2345r64teryrhd" \
     "http://localhost:8002/api/recommendation/rank_feed?limit=10"
    """

    logger.info(f"current_user: {current_user['_id']}")

    try:
        top_feed = get_feed(limit=limit)

        # 只取 id 與 type
        filtered_feed = [FeedItem(id=item.id, type=item.type) for item in top_feed]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return FeedResponse(items=filtered_feed)
