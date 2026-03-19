import math
from datetime import datetime, timezone
from typing import List, Optional

import click
import psycopg2
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.config import get_settings
from src.logger import AppLogger
from src.models import (
    BasicInfo,
    EntityResource,
    Idea,
    Practice,
    Project,
    Resource,
    User,
)
from src.schemas.entity_resource_response import (
    BasePost,
    InteractionStats,
    UserBasicInfo,
)
from src.schemas.recommendation import FeedInfo

logger = AppLogger(__name__).get_logger()


def get_feed(
    after_id: int = 10, page_size: int = 20, types: Optional[List[str]] = None
) -> List[FeedInfo]:
    """
    從資料庫抓取 idea / practice / project feed，計算 score，支援 cursor-based 分頁。
    """

    logger.info(f"after_id: {after_id}, types: {types}, page_size: {page_size}")

    if types is None:
        types = ["idea", "practice", "project"]

    # db_config = db_config or {}
    db_config = get_settings().postgresql
    conn = psycopg2.connect(
        user=db_config.db_user,
        password=db_config.db_password,
        host=db_config.db_host,
        port=db_config.db_port,
        dbname=db_config.db_name,
    )
    cur = conn.cursor()

    # SQL 片段動態生成
    sql_fragments = []
    if "idea" in types:
        sql_fragments.append(
            """
            SELECT i.id, 'idea' as type, i.content as title, i.created_at, i.updated_at,
                   COUNT(er.entity_id) as resource_count, 0 as streak, 0 as progress_ratio, 1 as base_score
            FROM ideas i
            LEFT JOIN entity_resources er ON er.entity_id=i.id AND er.entity_type='idea'
            GROUP BY i.id
            """
        )
    if "practice" in types:
        sql_fragments.append(
            """
            SELECT p.id, 'practice', p.title, p.created_at, p.updated_at,
                   COUNT(er.entity_id), 0, 0, 2
            FROM practices p
            JOIN users u ON u.id = p.user_id AND u.is_open_profile = true
            LEFT JOIN entity_resources er ON er.entity_id=p.id AND er.entity_type='practice'
            WHERE p.privacy_status = 'public'
            GROUP BY p.id
            """
        )
    if "project" in types:
        sql_fragments.append(
            """
            SELECT pr.id, 'project', pr.title, pr.created_at, pr.updated_at,
                   COUNT(er.entity_id), 0, 0, 3
            FROM project pr
            LEFT JOIN entity_resources er ON er.entity_id=pr.id AND er.entity_type='project'
            GROUP BY pr.id
            """
        )

    # 將 fragment 用 UNION ALL 合併
    combined_sql = " UNION ALL ".join(sql_fragments)

    if after_id is not None:
        final_sql = f"SELECT * FROM ({combined_sql}) combined WHERE id > %s ORDER BY id ASC LIMIT %s"
        cur.execute(final_sql, (after_id, page_size))
    else:
        final_sql = f"SELECT * FROM ({combined_sql}) combined ORDER BY id ASC LIMIT %s"
        cur.execute(final_sql, (page_size,))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    result = []

    for r in rows:
        (
            id,
            typ,
            title,
            created_at,
            updated_at,
            resource_count,
            streak,
            progress_ratio,
            base_score,
        ) = r

        # 使用 UTC aware datetime
        now = datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        days = (now - created_at).days

        # 計算新鮮度分數
        freshness_score = 1 / math.log(1 + days) if days > 0 else 0

        # 計算活動分數
        resource_count = float(resource_count)
        streak = float(streak)
        progress_ratio = float(progress_ratio)
        activity_score = resource_count * 1 + streak * 0.5 + progress_ratio * 2

        # 總分
        score = base_score + freshness_score + activity_score

        result.append(
            FeedInfo(
                id=id,
                type=typ,
                title=title,
                score=score,
                freshness_score=freshness_score,
                activity_score=activity_score,
            )
        )

    # 排序並取前 limit 筆
    result.sort(
        key=lambda x: (x.score, x.freshness_score, x.activity_score), reverse=True
    )

    return result


def get_start_end_date_from_post(post):
    # start_date 優先 start_date -> created_at -> now
    start_date = (
        getattr(post, "start_date", None)
        or getattr(post, "created_at", None)
        or datetime.utcnow()
    )

    # end_date 優先 end_date -> updated_at -> start_date
    end_date = (
        getattr(post, "end_date", None)
        or getattr(post, "updated_at", None)
        or start_date
    )

    return start_date, end_date


def get_tags_from_post(post):
    """
    根據貼文類型（Idea / Practice / Project）取得標籤列表。
    """
    if hasattr(post, "custom_content_type") and post.custom_content_type:
        # Practice 類型
        return [t.strip() for t in post.custom_content_type.split(",") if t.strip()]

    elif (
        hasattr(post, "strategy")
        or hasattr(post, "motivation")
        or hasattr(post, "outcome")
    ):
        # Project 類型
        tags = []
        for field in ["strategy", "motivation", "outcome"]:
            val = getattr(post, field, None)
            if val:
                if isinstance(val, list):
                    tags.extend(val)
                elif isinstance(val, str):
                    tags.extend([t.strip() for t in val.split(",") if t.strip()])
        return tags

    elif hasattr(post, "tag_list") and post.tag_list:
        # Idea 類型（未來可能有）
        return [t.strip() for t in post.tag_list.split(",") if t.strip()]

    return []


def get_posts(id_type_list: List[dict], session: Session) -> List[BasePost]:
    """
    根據多筆 {id, type} 清單，從資料庫撈出對應貼文內容（idea / practice / project），
    整合作者、標籤、資源、互動統計等資訊，並轉換成 BasePost 格式回傳。

    Args:
        id_type_list (List[dict]): 每筆資料包含 {'id': int, 'type': str}
        session (Session): SQLAlchemy 資料庫 session

    Returns:
        List[BasePost]: 統一格式的貼文資料清單
    """
    # [
    #     {
    #     "id": 19,
    #     "type": "project"
    #   },
    #   {
    #     "id": 36,
    #     "type": "project"
    #   },
    # ]
    type_map = {
        "idea": Idea,
        "practice": Practice,
        "project": Project,
    }

    ret = []
    for item in id_type_list:
        post_type = item.type
        post_id = item.id
        model = type_map.get(post_type)
        print(f"model {model}")
        if not model:
            continue

        post = session.get(model, post_id)

        if not post:
            continue

        logger.info(f"post {post}, {post.external_id} post_type = {post_type}")

        user = session.get(User, post.user_id)
        basic_info = session.query(BasicInfo).filter_by(id=user.basic_info_id).first()
        resources = (
            session.query(EntityResource, Resource)
            .join(Resource, Resource.id == EntityResource.resource_id)
            .filter(
                EntityResource.entity_id == post_id,
                func.lower(EntityResource.entity_type) == post_type.lower(),
            )
            .distinct()
            .all()
        )
        logger.info(f"resources {resources}")
        resource_pairs = {r.Resource.name: r.Resource.url for r in resources}
        share_list = basic_info.share_list.split(",") if basic_info.share_list else []

        start_date, end_date = get_start_end_date_from_post(post)

        ret.append(
            BasePost(
                id=str(post.external_id),
                type=post_type,
                title=(
                    (post.content[:120] + "...") if post_type == "idea" else post.title
                ),
                content=getattr(post, "content", getattr(post, "content_type", "")),
                tags=get_tags_from_post(post),
                user=UserBasicInfo(
                    id=user.id,
                    name=user.nickname,
                    tag_list=user.tag_list,
                    share_list=share_list,
                ),
                status=post.status,
                stats=InteractionStats(  # TODO
                    like_count=0,
                    comment_count=0,
                    share_count=0,
                    view_count=0,
                ),
                created_at=start_date,
                updated_at=end_date,
                resources=resource_pairs,
            )
        )
    return ret


@click.command()
@click.option("-t", "--to", "to", type=int, default=100, help="limit")
def main(to):
    top = get_feed(page_size=to, types=["idea", "practice", "project"])
    for item in top:
        logger.info(item.json())  # Pydantic 提供 json() 方便輸出
    logger.info("-" * 80)

    # filtered_feed = [{"id": item.id, "type": item.type} for item in top]
    from src.schemas.recommendation import FeedItem

    filtered_feed = [FeedItem(id=item.id, type=item.type) for item in top]
    logger.info(f"filtered_feed: {filtered_feed}")
    logger.info("-" * 80)

    from contextlib import contextmanager

    from src.db.factory import make_database

    @contextmanager
    def get_sync_session() -> Session:
        """
        提供 CLI / script 可用的同步 Session。
        自動啟動與關閉資料庫連線。
        """
        db = make_database()
        db.startup()
        try:
            with db.get_session() as session:
                yield session
        finally:
            db.teardown()

    with get_sync_session() as session:
        posts = get_posts(filtered_feed, session=session)
        # logger.info(f"posts: {posts}")
        for post in posts:
            logger.info(f"BasePost :{post.json()}")


# 範例使用
if __name__ == "__main__":
    main()
