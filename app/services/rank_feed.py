import math
from datetime import datetime, timezone
from typing import List
import click

import psycopg2
from api.schemas.recommendation import FeedInfo
from api.schemas.entity_resource_response import BasePost, InteractionStats, UserBasicInfo
from sqlalchemy.orm import Session
from models import Idea, Practice, Project, User, BasicInfo, EntityResource, Resource
from config import get_settings
from logger import AppLogger

logger = AppLogger(__name__).get_logger()


def get_feed(limit=100) -> List[FeedInfo]:
    """
    從資料庫抓取 idea / practice / project feed，計算 score 並回傳前 limit 筆結果。
    """
    print(f"limit: {limit}")
    # db_config = db_config or {}
    conn = psycopg2.connect(get_settings().postgresql.database_url)
    cur = conn.cursor()

    # 拉所有資料
    cur.execute(
        """
    SELECT id, type, title, created_at, updated_at,
           COALESCE(resource_count,0) as resource_count,
           COALESCE(streak,0) as streak,
           COALESCE(progress_ratio,0) as progress_ratio,
           base_score
    FROM (
        SELECT i.id, 'idea' as type, i.content as title, i.created_at, i.updated_at,
               COUNT(er.entity_id) as resource_count, 0 as streak, 0 as progress_ratio, 1 as base_score
        FROM ideas i
        LEFT JOIN entity_resources er ON er.entity_id=i.id AND er.entity_type='idea'
        GROUP BY i.id
        UNION ALL
        SELECT p.id, 'practice', p.title, p.created_at, p.updated_at,
               COUNT(er.entity_id), COALESCE(p.streak,0), COALESCE(p.current_progress/NULLIF(p.total_amount,0),0), 2
        FROM practices p
        LEFT JOIN entity_resources er ON er.entity_id=p.id AND er.entity_type='practice'
        GROUP BY p.id
        UNION ALL
        SELECT pr.id, 'project', pr.title, pr.created_at, pr.updated_at,
               COUNT(er.entity_id), 0, 0, 3
        FROM project pr
        LEFT JOIN entity_resources er ON er.entity_id=pr.id AND er.entity_type='project'
        GROUP BY pr.id
    ) combined
    """
    )

    rows = cur.fetchall()
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

    top_result = result[:limit]

    cur.close()
    conn.close()
    return top_result

def get_tags_from_post(post):
    """
    根據貼文類型（Idea / Practice / Project）取得標籤列表。
    """
    if hasattr(post, "custom_content_type") and post.custom_content_type:
        # Practice 類型
        return [t.strip() for t in post.custom_content_type.split(",") if t.strip()]
    
    elif hasattr(post, "strategy") or hasattr(post, "motivation") or hasattr(post, "outcome"):
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

def get_posts( id_type_list : List[dict] , session:Session)  -> List[BasePost]:
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
        'idea': Idea,
        'practice': Practice,
        'project': Project,
    }

    
    ret = []
    for item in id_type_list:
        post_type = item['type']
        post_id = item['id']
        model = type_map.get(post_type)
        if not model:
            continue
        
        post = session.get(model, post_id)
        if not post:
            continue
        
        user = session.get(User, post.user_id)
        basic_info = session.query(BasicInfo).filter_by(user_id=post.user_id).first()
        resources = (
            session.query(EntityResource, Resource)
            .join(Resource, Resource.id == EntityResource.resource_id)
            .filter(EntityResource.entity_id == post.id, EntityResource.entity_type == post_type)
            .all()
        )
        resource_pairs = {r.Resource.name: r.Resource.url for r in resources}
        share_list = basic_info.share_list.split(',') if basic_info.share_list else []
        
        ret.append(
            BasePost(
                id=post.id,
                type=post_type,
                content=getattr(post, "content", getattr(post, "content_type", "")),
                tags=get_tags_from_post(post),
                user=UserBasicInfo(
                    id=user.id,
                    name=user.nickname,
                    tag_list=user.tag_list,
                    share_list=share_list
                ),
                status=post.status,
                stats=InteractionStats( # TODO
                    like_count = 0,
                    comment_count = 0,
                    share_count = 0,
                    view_count = 0,
                ),
                created_at=post.created_at,
                updated_at=post.updated_at,
                resources=resource_pairs
            )
        )
    return ret



@click.command()
@click.option('-t', '--to', 'to', type=int, default=100, help='limit')
def main(to):
    top = get_feed(limit=to)
    for item in top:
        logger.info(item.json())  # Pydantic 提供 json() 方便輸出
    logger.info('-'*80)
    
    filtered_feed = [{"id":item.id, "type":item.type} for item in top]
    logger.info(f"filtered_feed: {filtered_feed}")
    logger.info('-'*80)
    
    from dependencies import get_db_session
    from db.factory import make_database
    posts = get_posts(
        filtered_feed,
        session=get_db_session(make_database())
    )
    logger.info(f"posts: {posts}")
        
    
# 範例使用
if __name__ == "__main__":
    main()