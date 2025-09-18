import math
from datetime import datetime, timezone
from typing import List

import psycopg2
from api.schemas.recommendation import FeedInfo
from config import get_settings
from logger import AppLogger

logger = AppLogger(__name__).get_logger()


def get_feed(limit=100) -> List[FeedInfo]:
    """
    從資料庫抓取 idea / practice / project feed，計算 score 並回傳前 limit 筆結果。
    """
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
        SELECT i.id::text, 'idea' as type, i.content as title, i.created_at, i.updated_at,
               COUNT(er.entity_id) as resource_count, 0 as streak, 0 as progress_ratio, 1 as base_score
        FROM ideas i
        LEFT JOIN entity_resources er ON er.entity_id=i.id::text AND er.entity_type='idea'
        GROUP BY i.id
        UNION ALL
        SELECT p.id::text, 'practice', p.title, p.created_at, p.updated_at,
               COUNT(er.entity_id), COALESCE(p.streak,0), COALESCE(p.current_progress/NULLIF(p.total_amount,0),0), 2
        FROM practices p
        LEFT JOIN entity_resources er ON er.entity_id=p.id::text AND er.entity_type='practice'
        GROUP BY p.id
        UNION ALL
        SELECT pr.id::text, 'project', pr.title, pr.created_at, pr.updated_at,
               COUNT(er.entity_id), 0, 0, 3
        FROM project pr
        LEFT JOIN entity_resources er ON er.entity_id=pr.id::text AND er.entity_type='project'
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


# 範例使用
if __name__ == "__main__":
    top_100 = get_feed(limit=100)
    for item in top_100:
        logger.info(item.json())  # Pydantic 提供 json() 方便輸出
