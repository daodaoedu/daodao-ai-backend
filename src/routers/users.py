from fastapi import APIRouter, Query
from typing import Optional, List
from src.dependencies import SessionDep, UserDep
from src.logger import AppLogger
from src.response_template import api_response_decorator
from src.schemas.pageInfo import APIResponse, CursorPaginationInfo
from src.utils.orm_to_dict import orm_to_dict
from src.services.practice.practice import PracticeService

logger = AppLogger(__name__).get_logger()


router = APIRouter(prefix="/v1/users", tags=["users"])


@router.get(
    "/practices", description="取得使用者的實踐貼文列表", response_model=APIResponse
)
@api_response_decorator
def get_my_practices(
    db: SessionDep,
    current_user: UserDep,
    # pagination
    limit: int = Query(20, ge=1, le=100),
    after_id: Optional[int] = Query(
        None, description="上一次最後一筆的 id，作為 cursor"
    ),
    offset: int = Query(0, ge=0),
    # search
    keyword: Optional[str] = Query(None, description="搜尋標題或內容"),
    search_fields: List[str] = Query(default=["title"]),
    # filter
    tags: Optional[List[str]] = Query(None),
    duration_min: Optional[int] = None,
    duration_max: Optional[int] = None,
    status: Optional[str] = None,
    # sort
    sort_by: str = Query(
        "newest_updated",
        description="newest_updated | oldest_updated | newest_created | oldest_created| recommended",
    ),
):
    # 會有filter, search, sort等功能

    # filter: 依照分類、標籤、狀態等條件篩選實踐貼文
    # search: 依照關鍵字搜尋實踐貼文的標題或
    # sort: 依據推薦演算法排序，或是使用者選擇的排序方式（例如：最新、最舊、最多讚等）
    # 如果是無痕頁面，會有預設的規則排序。按「最後一次打卡 (Check-in) 時間」或「實踐建立時間」降序排列。

    practices = PracticeService.get_practices(
        db=db,
        user_external_id=current_user,
        keyword=keyword,
        search_fields=search_fields,
        tags=tags,
        duration_min=duration_min,
        duration_max=duration_max,
        status=status,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )

    results = [orm_to_dict(p) for p in practices]

    for r in results:
        logger.info(f"get_my_practices result item: {r.get('title')}\n")
    next_cursor = results[-1].get("id") if results else None
    has_next = len(results) == limit
    logger.info(f"recommendation_feed next_cursor: {next_cursor}")
    logger.info(f"get_my_practices result count: {len(results)}")

    pagination = CursorPaginationInfo(
        cursors={
            "start": str(after_id) if after_id else None,
            "end": str(next_cursor) if next_cursor else None,
        },
        hasPrev=after_id is not None,
        hasNext=has_next,
        count=len(results),
    )

    return {
        "data": results,
        "pagination": pagination,
        "cache_hit": False,
    }
