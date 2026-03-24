import json
from collections import defaultdict
from fastapi import APIRouter, Query
from typing import Optional
from sqlalchemy import bindparam, text
from src.dependencies import SessionDep, UserDep, CacheDep
from src.logger import AppLogger
from src.models.User import User
from src.response_template import api_response_decorator
from src.schemas.pageInfo import APIResponse, CursorPaginationInfo
from src.utils.orm_to_dict import orm_to_dict
from src.models.Practice import PracticePrivacyStatus, PracticeStatus
from src.services.practice.practice import PracticeService
from src.auto_metrics import observe_api

logger = AppLogger(__name__).get_logger()

router = APIRouter(prefix="/v1/users", tags=["users"])

SUGGESTIONS_TTL = 600  # 10 分鐘
COMPLETIONS_TTL = 300  # 5 分鐘
MY_PRACTICES_TTL = 120  # 2 分鐘

_EMPTY_SUGGESTIONS = {"popular_keywords": [], "interest_tags": []}


@router.get(
    "/practices/suggestions",
    description="""
    取得搜尋建議關鍵字（需登入使用者）。<br/>
    - **登入使用者**會回傳：<br/>
    `popular_keywords`: 近期熱門標籤<br/>
    `interest_tags`: 與使用者技能或興趣相關的標籤<br/>
    - **未登入使用者**會回傳空資料
    """,
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
        try:
            return {"data": json.loads(cached), "pagination": None, "cache_hit": True}
        except Exception:
            logger.warning(f"cache parse error for key={cache_key}, falling back to DB")

    suggestions = PracticeService.get_search_suggestions(db=db, user_id=user.id)
    try:
        cache.client.set(cache_key, json.dumps(suggestions), ex=SUGGESTIONS_TTL)
    except Exception:
        logger.warning(f"cache write error for key={cache_key}, skipping cache")
    return {"data": suggestions, "pagination": None, "cache_hit": False}


@router.get(
    "/practices/completions",
    description="""
    提供文字補全建議，支援輸入框即時建議
    """,
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
        try:
            return {"data": json.loads(cached), "pagination": None, "cache_hit": True}
        except Exception:
            logger.warning(f"cache parse error for key={cache_key}, falling back to DB")

    result = PracticeService.get_completions(db=db, prefix=normalized_q, limit=limit)
    try:
        cache.client.set(cache_key, json.dumps(result), ex=COMPLETIONS_TTL)
    except Exception:
        logger.warning(f"cache write error for key={cache_key}, skipping cache")
    return {"data": result, "pagination": None, "cache_hit": False}


@router.get(
    "/practices", description="""
    取得使用者的實踐貼文列表。<br/>
    - 登入用戶會有個人化排序與快取<br/>
    - 未登入用戶仍可取得貼文列表，但無個人化<br/>
    - 支援搜尋、過濾、排序與分頁<br/>
    - 每筆貼文包含使用者資訊、回應統計與是否延遲公開<br/>
    """,
    response_model=APIResponse
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
            f":kw:{keyword if keyword is not None else '__none__'}"
            f":tags:{tags_str}"
            f":dur:{duration_min if duration_min is not None else ''}-{duration_max if duration_max is not None else ''}"
            f":status:{status if status is not None else '__none__'}"
            f":sort:{sort_by}"
            f":limit:{limit}:after:{after_id or 0}:offset:{offset}"
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

    # ── 2.1 Reactions aggregation (batch) ────────────────────────────────
    practice_map = {p.id: p for p in practices}
    reactions_by_practice: dict = defaultdict(list)
    if results:
        practice_ids = [r["id"] for r in results]
        reaction_rows = db.execute(
            text(
                """
                SELECT
                    r.target_id,
                    r.reaction_type,
                    COUNT(*) AS cnt,
                    (
                        SELECT u2.nickname
                        FROM reactions r2
                        LEFT JOIN users u2 ON u2.id = r2.user_id
                        WHERE r2.target_type = 'practice'
                          AND r2.target_id = r.target_id
                          AND r2.reaction_type = r.reaction_type
                        ORDER BY r2.created_at DESC
                        LIMIT 1
                    ) AS latest_actor_name
                FROM reactions r
                WHERE r.target_type = 'practice'
                  AND r.target_id IN :practice_ids
                GROUP BY r.target_id, r.reaction_type
                """
            ).bindparams(bindparam("practice_ids", expanding=True)),
            {"practice_ids": practice_ids},
        ).fetchall()

        for row in reaction_rows:
            reactions_by_practice[row.target_id].append(
                {
                    "type": row.reaction_type,
                    "count": row.cnt,
                    "latestActorName": row.latest_actor_name,
                }
            )

    next_cursor = results[-1].get("id") if results else None
    has_next = len(results) == limit
    logger.info(f"get_my_practices count={len(results)}, next_cursor={next_cursor}")

    # ── 2.2 Enrich each result (user, reactions, brewing, id) ────────────
    for r in results:
        practice = practice_map.get(r["id"])
        u = practice.user if practice else None
        r["user"] = (
            {
                "id": str(u.external_id) if u and u.external_id else None,
                "name": u.nickname or "",
                "photo_url": u.contact.photo_url if u and u.contact else None,
            }
            if u
            else None
        )
        r["reactions"] = reactions_by_practice.get(r["id"], [])
        r["is_brewing"] = (
            r.get("privacy_status") == PracticePrivacyStatus.DELAYED.value
            and r.get("status") == PracticeStatus.ACTIVE.value
        )
        logger.info(f"get_my_practices result item: {r.get('title')}\n")
        # 將 id 替換為 external_id（UUID），供前端用於 reactions 和頁面導航
        r["id"] = r.get("external_id") or r["id"]

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
        try:
            cache.client.set(
                cache_key,
                json.dumps(
                    {"data": results, "pagination": pagination.model_dump()},
                    default=str,
                ),
                ex=MY_PRACTICES_TTL,
            )
        except Exception:
            logger.warning(f"cache write error for key={cache_key}, skipping cache")

    return {**payload, "cache_hit": False}
