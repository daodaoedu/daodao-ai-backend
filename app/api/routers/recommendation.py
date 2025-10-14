from typing import Optional

from api.template import api_response_decorator
from core.limiter import limiter
from dependencies import SessionDep
from fastapi import APIRouter, HTTPException, Query, Request
from logger import AppLogger
from schemas.pageInfo import APIResponse, CursorPaginationInfo
from schemas.recommendation import FeedItem
from services.rank_feed import get_feed, get_posts

logger = AppLogger(__name__).get_logger()


router = APIRouter(prefix="/v1/recommendation", tags=["recommendation"])


@router.get("/rank_feed", response_model=APIResponse)
@limiter.limit("5/minute")
@api_response_decorator
def recommendation_feed(
    request: Request,
    session: SessionDep,  # ✅ FastAPI 會自動從 get_db_session() 拿 session
    # limit: int = Query(100, description="最多取得幾筆 feed"),
    after_id: Optional[int] = Query(
        None, description="上一次最後一筆的 id，作為 cursor"
    ),
    page_size: int = Query(20, description="每頁抓幾筆"),
    # types: Optional[str] = Query(
    #     None, description="要抓哪些類型的 feed"
    # )
):
    """
    推薦 feed API
    - JWT 驗證透過 get_current_user 自動處理
    example:
    curl -X POST "http://localhost:8002/api/recommendation/rank_feed?limit=10" \
    -H "accept: application/json" \
    -H "Authorization: Bearer <YOUR_TOKEN_ID>"

    """

    try:
        top_feed = get_feed(after_id=after_id, page_size=page_size)
        # 只取 id 與 type
        filtered_feed = [FeedItem(id=item.id, type=item.type) for item in top_feed]

        logger.info(f"recommendation_feed result: {len(filtered_feed)}")

        posts = get_posts(filtered_feed, session=session)

        # Cursor pagination info
        paginated_posts = posts
        next_cursor = paginated_posts[-1].id if paginated_posts else None
        has_next = len(paginated_posts) == page_size
        logger.info(f"recommendation_feed next_cursor: {next_cursor}")

    except Exception as e:
        logger.info(f"recommendation_feed error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    pagination = CursorPaginationInfo(
        cursors={
            "start": str(after_id) if after_id else None,
            "end": str(next_cursor) if next_cursor else None,
        },
        hasPrev=after_id is not None,
        hasNext=has_next,
        count=len(paginated_posts),
    )

    return {
        "data": paginated_posts,
        "pagination": pagination,
        "cache_hit": False,
    }
