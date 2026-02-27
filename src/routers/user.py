from fastapi import APIRouter, Query
from typing import Optional, List


from src.logger import AppLogger
from src.models.Practice import Practice
from src.response_template import api_response_decorator
from src.schemas.pageInfo import APIResponse
from src.dependencies import SessionDep, UserDep


logger = AppLogger(__name__).get_logger()


router = APIRouter(prefix="/v1/user", tags=["user"])


@router.get(
    "/practices", description="取得使用者的實踐貼文列表", response_model=APIResponse
)
@api_response_decorator
def get_my_practices(
    db: SessionDep,
    current_user: UserDep,
    # pagination
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    # search
    keyword: Optional[str] = Query(None, description="搜尋標題或內容"),
    search_fields: List[str] = Query(default=["title", "practice_action"]),
    # filter
    tags: Optional[List[str]] = Query(None),
    duration_min: Optional[int] = None,
    duration_max: Optional[int] = None,
    status: Optional[str] = None,
    # sort
    sort_by: str = Query(
        "newest", description="newest | oldest | most_liked | recommended"
    ),
):
    logger.info(f"get_my_practices: {current_user}")
    # 會有filter, search, sort等功能

    # filter: 依照分類、標籤、狀態等條件篩選實踐貼文
    # search: 依照關鍵字搜尋實踐貼文的標題或
    # sort: 依據推薦演算法排序，或是使用者選擇的排序方式（例如：最新、最舊、最多讚等）
    # 如果是無痕頁面，會有預設的規則排序。按「最後一次打卡 (Check-in) 時間」或「實踐建立時間」降序排列。
    query = db.query(Practice)

    # ===== Search =====
    if keyword:
        conditions = []

        if "title" in search_fields:
            conditions.append(Practice.title.ilike(f"%{keyword}%"))

        if "action" in search_fields:
            conditions.append(Practice.actions.cast(str).ilike(f"%{keyword}%"))

        if "tag" in search_fields:
            conditions.append(Practice.tags.cast(str).ilike(f"%{keyword}%"))

        if "resource" in search_fields:
            conditions.append(Practice.resources.cast(str).ilike(f"%{keyword}%"))

        # 🔴 隱私保護：排除延遲分享心得
        query = query.filter(not Practice.is_delayed_share)

        if conditions:
            from sqlalchemy import or_

            query = query.filter(or_(*conditions))

    logger.info(f"After search, query: {str(query)}")
    # ===== Filter =====
    if tags:
        for tag in tags:
            query = query.filter(Practice.tags.cast(str).ilike(f"%{tag}%"))

    if duration_min is not None:
        query = query.filter(Practice.duration_days >= duration_min)

    if duration_max is not None:
        query = query.filter(Practice.duration_days <= duration_max)

    if status:
        query = query.filter(Practice.status == status)

    logger.info(f"After filter, query: {str(query)}")
    # ===== Sort =====
    if sort_by == "newest_update":
        query = query.order_by(
            Practice.last_checkin_at.desc().nullslast(), Practice.created_at.desc()
        )

    elif sort_by == "oldest":
        query = query.order_by(Practice.created_at.asc())

    elif sort_by == "most_liked":
        query = query.order_by(Practice.like_count.desc())

    elif sort_by == "recommended":
        query = query.order_by(Practice.score.desc())
    logger.info(f"After sort, query: {str(query)}")
