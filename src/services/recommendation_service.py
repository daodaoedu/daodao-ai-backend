from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.schemas.pageInfo import CursorPaginationInfo
from src.schemas.recommendation import FeedItem
from src.services.rank_feed import get_feed, get_posts

VALID_FEED_TYPES = {"idea", "practice", "project"}


def get_recommendation_feed(
    session: Session,
    after_id: Optional[int],
    page_size: int,
    type_filter: Optional[str],
) -> tuple[list, CursorPaginationInfo]:
    """
    Fetch, score, and paginate recommendation feed.

    Raises HTTPException(400) when type_filter is not a valid feed type.
    Returns (posts, pagination).
    """
    if type_filter and type_filter not in VALID_FEED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="type must be one of ['idea', 'practice', 'project']",
        )

    top_feed = get_feed(
        after_id=after_id,
        page_size=page_size,
        types=[type_filter] if type_filter else None,
    )

    posts = get_posts(
        [FeedItem(id=item.id, type=item.type) for item in top_feed],
        session=session,
    )

    next_cursor = posts[-1].id if posts else None
    pagination = CursorPaginationInfo(
        cursors={
            "start": str(after_id) if after_id else None,
            "end": str(next_cursor) if next_cursor else None,
        },
        hasPrev=after_id is not None,
        hasNext=len(posts) == page_size,
        count=len(posts),
    )

    return posts, pagination
