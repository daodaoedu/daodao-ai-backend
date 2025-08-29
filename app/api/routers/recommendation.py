from fastapi import APIRouter, HTTPException, Query
from services.rank_feed import get_feed  # 你的 get_feed 函式
from api.schemas.recommendation import FeedResponse, FeedItem


router = APIRouter(prefix="/recommendation", tags=["recommendation"])

@router.get("/rank_feed", response_model=FeedResponse)
def recommendation_feed(limit: int = Query(100, description="最多取得幾筆 feed")):
    try:
        top_feed = get_feed(limit=limit)

        # 只取 id 與 type
        filtered_feed = [FeedItem(id=item.id, type=item.type) for item in top_feed]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    return FeedResponse(items=filtered_feed)