import json
from typing import Optional

from fastapi import APIRouter, Query

from src.auto_metrics import observe_api
from src.dependencies import CacheDep, SessionDep, UserDep
from src.logger import AppLogger
from src.models.User import User
from src.response_template import api_response_decorator
from src.schemas.pageInfo import APIResponse, CursorPaginationInfo
from src.services.practice.practice import PracticeService
from src.utils.orm_to_dict import orm_to_dict

logger = AppLogger(__name__).get_logger()

router = APIRouter(prefix="/v1/users", tags=["users"])

SUGGESTIONS_TTL = 600  # 10 分鐘
COMPLETIONS_TTL = 300  # 5 分鐘
MY_PRACTICES_TTL = 120  # 2 分鐘

_EMPTY_SUGGESTIONS = {"popular_keywords": [], "interest_tags": []}


@router.get(
    "/practices/suggestions",
    description="取得搜尋建議關鍵字（近期熱門標籤 + 我的技能興趣相關標籤）",
    response_model=APIResponse,
)
@api_response_decorator
@observe_api
def get_practice_suggestions(
    db: SessionDep,
    current_user: UserDep,
    cache: CacheDep,
):
    if not current_user:
        return {"data": _EMPTY_SUGGESTIONS, "pagination": None, "cache_hit": False}

    user = db.query(User).filter(User.external_id == current_user).first()
    if not user:
        return {"data": _EMPTY_SUGGESTIONS, "pagination": None, "cache_hit": False}

    cache_key = f"practice_suggestions:{user.id}"
    cached = cache.client.get(cache_key)
    if cached:
        return {"data": json.loads(cached), "pagination": None, "cache_hit": True}

    suggestions = PracticeService.get_search_suggestions(db=db, user_id=user.id)
    cache.client.set(cache_key, json.dumps(suggestions), ex=SUGGESTIONS_TTL)
    return {"data": suggestions, "pagination": None, "cache_hit": False}


@router.get(
    "/practices/completions",
    description="關鍵字文字補全與預測下一個詞（輸入框即時補全用）",
    response_model=APIResponse,
)
@api_response_decorator
@observe_api
def get_practice_completions(
    db: SessionDep,
    current_user: UserDep,
    cache: CacheDep,
    q: str = Query(..., min_length=1, max_length=50, description="輸入前綴或完整詞"),
    limit: int = Query(10, ge=1, le=20, description="最多回傳幾個候選詞"),
):
    normalized_q = q.strip().lower()
    cache_key = f"practice_completions:q:{normalized_q}:limit:{limit}"

    cached = cache.client.get(cache_key)
    if cached:
        return {"data": json.loads(cached), "pagination": None, "cache_hit": True}

    result = PracticeService.get_completions(db=db, prefix=normalized_q, limit=limit)
    cache.client.set(cache_key, json.dumps(result), ex=COMPLETIONS_TTL)
    return {"data": result, "pagination": None, "cache_hit": False}


@router.get(
    "/practices", description="取得使用者的實踐貼文列表", response_model=APIResponse
)
@api_response_decorator
@observe_api
def get_my_practices(
    db: SessionDep,
    current_user: UserDep,
    cache: CacheDep,
    # pagination
    limit: int = Query(20, ge=1, le=100),
    after_id: Optional[int] = Query(
        None, description="上一次最後一筆的 id，作為 cursor"
    ),
    offset: int = Query(0, ge=0),
    # search
    keyword: Optional[str] = Query(
        None, description="多維度關鍵字搜尋（標題、行動、標籤、資源、打卡內容）"
    ),
    # filter
    tags: Optional[list[str]] = Query(None),
    duration_min: Optional[int] = None,
    duration_max: Optional[int] = None,
    status: Optional[str] = None,
    # sort
    sort_by: str = Query(
        "newest_updated",
        description="newest_updated | oldest_updated | newest_created | oldest_created| recommended",
    ),
):
    # ── cache key（只有登入用戶才 cache，anon 每次即時查詢）──
    user_id: Optional[int] = None
    if current_user:
        _user = db.query(User).filter(User.external_id == current_user).first()
        user_id = _user.id if _user else None

    if user_id:
        tags_str = ",".join(sorted(tags)) if tags else ""
        cache_key = (
            f"practices:user:{user_id}"
            f":kw:{keyword or ''}"
            f":tags:{tags_str}"
            f":dur:{duration_min or ''}-{duration_max or ''}"
            f":status:{status or ''}"
            f":sort:{sort_by}"
            f":limit:{limit}:after:{after_id or 0}:offset:{offset}"
        )
        cached = cache.client.get(cache_key)
        if cached:
            payload = json.loads(cached)
            return {**payload, "cache_hit": True}

    # ── 實際查詢 ──
    practices = PracticeService.get_practices(
        db=db,
        user_external_id=current_user,
        keyword=keyword,
        tags=tags,
        duration_min=duration_min,
        duration_max=duration_max,
        status=status,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )

    results = [orm_to_dict(p) for p in practices]

    next_cursor = results[-1].get("id") if results else None
    has_next = len(results) == limit
    logger.info(f"get_my_practices count={len(results)}, next_cursor={next_cursor}")

    pagination = CursorPaginationInfo(
        cursors={
            "start": str(after_id) if after_id else None,
            "end": str(next_cursor) if next_cursor else None,
        },
        hasPrev=after_id is not None,
        hasNext=has_next,
        count=len(results),
    )

    payload = {"data": results, "pagination": pagination}

    if user_id:
        cache.client.set(
            cache_key,
            json.dumps(
                {"data": results, "pagination": pagination.model_dump()}, default=str
            ),
            ex=MY_PRACTICES_TTL,
        )

    return {**payload, "cache_hit": False}
