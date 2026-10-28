import json
from typing import Annotated, Optional

from fastapi import APIRouter, Query
from pydantic import StringConstraints

from src.dependencies import SessionDep, UserDep, CacheDep
from src.logger import AppLogger
from src.models.User import User
from src.response_template import api_response_decorator
from src.auto_metrics import observe_api
from src.schemas.feed import FeedTypeFilter
from src.schemas.pageInfo import CursorPaginationInfo
from src.services.feed.feed_service import FeedService
from src.services.feed.space_filter import (
    SPACE_VALUE_PATTERN,
    parse_space_filter,
    space_cache_token,
)

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
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="每頁最多回傳幾張卡片；type=all 時會以完整循環單位（5～6 格）回傳",
    ),
    keyword: Optional[str] = Query(None, description="搜尋關鍵字"),
    tags: Optional[list[str]] = Query(None, description="標籤篩選"),
    type_filter: FeedTypeFilter = Query(
        FeedTypeFilter.ALL,
        alias="type",
        description="篩選類型: all | practice | checkin",
    ),
    spaces: Optional[
        list[Annotated[str, StringConstraints(pattern=SPACE_VALUE_PATTERN)]]
    ] = Query(
        None,
        max_length=20,
        description="空間篩選，可多選取聯集: personal | challenge | cohort:<cohort id>",
    ),
):
    space_filter = parse_space_filter(spaces)

    # ── 解析 user_id（沿用 /v1/users/practices pattern）──
    user_id: Optional[int] = None
    if current_user:
        _user = db.query(User).filter(User.external_id == current_user).first()
        user_id = _user.id if _user else None

    # Cohort selections may contain private content. Recheck current membership and
    # retention on every request, including after a member exits; never use stale cache.
    use_cache = user_id is not None and not (
        space_filter is not None and space_filter.cohort_ids
    )

    # ── cache（公開 feed 的登入用戶才 cache）──
    if use_cache:
        tags_str = ",".join(sorted(tags)) if tags else ""
        cache_key = (
            f"feed:user:{user_id}"
            f":kw:{keyword if keyword is not None else '__none__'}"
            f":tags:{tags_str}"
            f":type:{type_filter.value}"
            f":spaces:{space_cache_token(space_filter)}"
            f":limit:{limit}:cursor:{cursor or '0'}"
        )
        cached = cache.client.get(cache_key)
        if cached:
            try:
                payload = json.loads(cached)
                return {**payload, "cache_hit": True}
            except Exception:
                logger.warning(
                    f"cache parse error for key={cache_key}, falling back to DB"
                )

    # ── 實際查詢 ──
    result = FeedService.get_feed(
        db=db,
        current_user_external_id=current_user,
        cursor=cursor,
        limit=limit,
        keyword=keyword,
        tags=tags,
        type_filter=type_filter,
        space_filter=space_filter,
    )

    next_cursor = result.get("next_cursor")
    pagination = CursorPaginationInfo(
        cursors={
            "start": cursor,
            "end": next_cursor,
        },
        hasPrev=cursor is not None,
        hasNext=next_cursor is not None,
        count=len(result["data"]),
    )
    payload = {
        "data": result["data"],
        "pagination": pagination.model_dump(),
    }

    # ── 寫入 cache ──
    if use_cache:
        try:
            cache.client.set(
                cache_key, json.dumps(payload, default=str), ex=FEED_CACHE_TTL
            )
        except Exception:
            logger.warning(f"cache write error for key={cache_key}, skipping cache")

    return {**payload, "cache_hit": False}
