import json

from fastapi import APIRouter, Query
from typing import Optional

from src.dependencies import SessionDep, UserDep, CacheDep
from src.logger import AppLogger
from src.models.User import User
from src.response_template import api_response_decorator
from src.auto_metrics import observe_api
from src.schemas.feed import FeedSortBy, FeedTypeFilter
from src.schemas.pageInfo import CursorPaginationInfo
from src.services.feed.feed_service import FeedService

logger = AppLogger(__name__).get_logger()

router = APIRouter(prefix="/v1/feed", tags=["feed"])

FEED_CACHE_TTL = 120  # 2 分鐘


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
    # ── 解析 user_id（沿用 /v1/users/practices pattern）──
    user_id: Optional[int] = None
    if current_user:
        _user = db.query(User).filter(User.external_id == current_user).first()
        user_id = _user.id if _user else None

    # ── cache（登入用戶才 cache）──
    if user_id:
        tags_str = ",".join(sorted(tags)) if tags else ""
        cache_key = (
            f"feed:user:{user_id}"
            f":kw:{keyword if keyword is not None else '__none__'}"
            f":tags:{tags_str}"
            f":type:{type.value}"
            f":limit:{limit}:cursor:{cursor or '0'}"
        )
        cached = cache.client.get(cache_key)
        if cached:
            try:
                payload = json.loads(cached)
                return {**payload, "cache_hit": True}
            except Exception:
                logger.warning(f"cache parse error for key={cache_key}, falling back to DB")

    # ── 登入用戶自動啟用推薦排序 ──
    sort_by = FeedSortBy.RECOMMENDED if user_id else FeedSortBy.NEWEST

    # ── 實際查詢 ──
    result = FeedService.get_feed(
        db=db,
        current_user_external_id=current_user,
        cursor=cursor,
        limit=limit,
        keyword=keyword,
        tags=tags,
        type_filter=type,
        sort_by=sort_by,
    )

    next_cursor = result.get("next_cursor")
    payload = {
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
    }

    # ── 寫入 cache ──
    if user_id:
        try:
            cache.client.set(cache_key, json.dumps(payload, default=str), ex=FEED_CACHE_TTL)
        except Exception:
            logger.warning(f"cache write error for key={cache_key}, skipping cache")

    return {**payload, "cache_hit": False}
