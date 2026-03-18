import json
from collections import defaultdict
from fastapi import APIRouter, Query
from typing import Optional
from sqlalchemy import text
from src.dependencies import SessionDep, UserDep, CacheDep
from src.logger import AppLogger
from src.models.User import User
from src.response_template import api_response_decorator
from src.schemas.pageInfo import APIResponse, CursorPaginationInfo
from src.utils.orm_to_dict import orm_to_dict
from src.services.practice.practice import PracticeService
from src.auto_metrics import observe_api

logger = AppLogger(__name__).get_logger()


router = APIRouter(prefix="/v1/users", tags=["users"])


SUGGESTIONS_TTL = 600  # 10 分鐘
COMPLETIONS_TTL = 300  # 5 分鐘


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
    empty = {
        "data": {"popular_keywords": [], "interest_tags": []},
        "pagination": None,
        "cache_hit": False,
    }
    if not current_user:
        return empty

    user = db.query(User).filter(User.external_id == current_user).first()
    if not user:
        return empty

    cache_key = f"practice_suggestions:{user.id}"

    cached = cache.client.get(cache_key)
    if cached:
        suggestions = json.loads(cached)
        return {"data": suggestions, "pagination": None, "cache_hit": True}

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
    # 會有filter, search, sort等功能

    # filter: 依照分類、標籤、狀態等條件篩選實踐貼文
    # search: 依照關鍵字搜尋實踐貼文（標題、行動、標籤、資源、打卡內容）
    # sort: 依據推薦演算法排序，或是使用者選擇的排序方式（例如：最新、最舊、最多讚等）
    # 如果是無痕頁面，會有預設的規則排序。按「最後一次打卡 (Check-in) 時間」或「實踐建立時間」降序排列。

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

    # ── 2.1 Attach user info ───────────────────────────────────────────────
    practice_map = {p.id: p for p in practices}
    for r in results:
        practice = practice_map.get(r["id"])
        u = practice.user if practice else None
        r["user"] = {
            "id": str(u.external_id) if u and u.external_id else None,
            "name": u.nickname or "",
            "photo_url": u.contact.photo_url if u and u.contact else None,
        } if u else None

    # ── 2.2 Reactions aggregation (batch, not N+1) ────────────────────────
    if results:
        practice_ids = [r["id"] for r in results]
        ids_placeholder = ",".join(str(pid) for pid in practice_ids)
        reaction_rows = db.execute(
            text(
                f"""
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
                  AND r.target_id IN ({ids_placeholder})
                GROUP BY r.target_id, r.reaction_type
                """
            )
        ).fetchall()

        reactions_by_practice: dict = defaultdict(list)
        for row in reaction_rows:
            reactions_by_practice[row.target_id].append(
                {
                    "type": row.reaction_type,
                    "count": row.cnt,
                    "latestActorName": row.latest_actor_name,
                }
            )

        for r in results:
            r["reactions"] = reactions_by_practice.get(r["id"], [])

    # ── 2.4 Brewing card logic ────────────────────────────────────────────
    for r in results:
        is_brewing = (
            r.get("privacy_status") == "delayed" and r.get("status") == "active"
        )
        r["is_brewing"] = is_brewing

    for r in results:
        logger.info(f"get_my_practices result item: {r.get('title')}\n")
    next_cursor = results[-1].get("id") if results else None
    has_next = len(results) == limit
    logger.info(f"recommendation_feed next_cursor: {next_cursor}")
    logger.info(f"get_my_practices result count: {len(results)}")

    # 將 id 替換為 external_id（UUID），供前端用於 reactions 和頁面導航
    for r in results:
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

    return {
        "data": results,
        "pagination": pagination,
        "cache_hit": False,
    }
