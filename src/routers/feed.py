from fastapi import APIRouter, Query
from typing import Optional

from src.dependencies import SessionDep, UserDep, CacheDep
from src.response_template import api_response_decorator
from src.auto_metrics import observe_api
from src.schemas.feed import FeedTypeFilter
from src.schemas.pageInfo import CursorPaginationInfo
from src.services.feed.feed_service import FeedService

router = APIRouter(prefix="/v1/feed", tags=["feed"])


@router.get(
    "",
    description="統一 Feed：混合展示實踐與打卡，按時間排序",
    response_model=None,
)
@api_response_decorator
@observe_api
def get_feed(
    db: SessionDep,
    current_user: UserDep,
    cache: CacheDep,
    cursor: Optional[str] = Query(None, description="分頁游標"),
    limit: int = Query(20, ge=1, le=100, description="每頁數量"),
    keyword: Optional[str] = Query(None, description="搜尋關鍵字"),
    tags: Optional[list[str]] = Query(None, description="標籤篩選"),
    type: FeedTypeFilter = Query(
        FeedTypeFilter.ALL, description="篩選類型: all | practice | checkin"
    ),
):
    result = FeedService.get_feed(
        db=db,
        current_user_external_id=current_user,
        cursor=cursor,
        limit=limit,
        keyword=keyword,
        tags=tags,
        type_filter=type,
    )

    next_cursor = result.get("next_cursor")
    return {
        "data": result["data"],
        "pagination": CursorPaginationInfo(
            cursors={
                "start": cursor,
                "end": next_cursor,
            },
            hasPrev=cursor is not None,
            hasNext=next_cursor is not None,
            count=len(result["data"]),
        ),
        "cache_hit": False,
    }
