"""
Feed Service

統一 Feed 查詢：混合 practice + checkin，按時間排序。
沿用 routers/users.py 的 practice 查詢與 enrichment 模式。
"""

from typing import Optional

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from src.logger import AppLogger
from src.schemas.feed import FeedTypeFilter

logger = AppLogger(__name__).get_logger()


class FeedService:
    @staticmethod
    def get_feed(
        db: Session,
        current_user_external_id: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: int = 20,
        keyword: Optional[str] = None,
        tags: Optional[list[str]] = None,
        type_filter: FeedTypeFilter = FeedTypeFilter.ALL,
    ) -> dict:
        """
        統一 feed 查詢：混合 practice + checkin，按時間排序。

        1. UNION query: practices + checkins → sorted by created_at
        2. Batch enrich: reactions, comments, user info
        3. Cursor pagination on (sort_time, item_id)
        """
        # --- 1. Parse cursor ---
        cursor_time = None
        cursor_id = None
        if cursor:
            parts = cursor.rsplit("_", 1)
            if len(parts) == 2:
                cursor_time = parts[0]
                try:
                    cursor_id = int(parts[1])
                except ValueError:
                    cursor_time = None

        # --- 2. Build UNION query dynamically based on type_filter ---
        practice_subquery = """
            SELECT
                'practice' AS item_type,
                p.id AS item_id,
                p.created_at AS sort_time
            FROM practices p
            WHERE p.privacy_status = 'public'
              AND p.status IN ('active', 'completed')
              AND p.deleted_at IS NULL
        """

        checkin_subquery = """
            SELECT
                'checkin' AS item_type,
                c.id AS item_id,
                c.created_at AS sort_time
            FROM practice_checkins c
            JOIN practices p ON p.id = c.practice_id
            WHERE p.privacy_status = 'public'
              AND p.status IN ('active', 'completed')
              AND p.deleted_at IS NULL
        """

        # Keyword filter
        if keyword:
            # Escape ILIKE special chars to prevent unintended wildcard matches
            escaped = (
                keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            kw_param = f"%{escaped}%"
            practice_subquery += """
              AND (p.title ILIKE :keyword OR p.practice_action ILIKE :keyword)
            """
            checkin_subquery += """
              AND (c.note ILIKE :keyword)
            """
        else:
            kw_param = None

        # Tags filter (via entity_tags table)
        if tags:
            practice_subquery += """
              AND EXISTS (
                  SELECT 1 FROM entity_tags et
                  JOIN tags t ON t.id = et.tag_id
                  WHERE et.entity_type = 'practice'
                    AND et.entity_id = p.id
                    AND t.name = ANY(:tags)
              )
            """
            # Checkin: filter by parent practice's tags
            checkin_subquery += """
              AND EXISTS (
                  SELECT 1 FROM entity_tags et
                  JOIN tags t ON t.id = et.tag_id
                  WHERE et.entity_type = 'practice'
                    AND et.entity_id = c.practice_id
                    AND t.name = ANY(:tags)
              )
            """

        # Assemble UNION based on type_filter
        parts = []
        if type_filter in (FeedTypeFilter.ALL, FeedTypeFilter.PRACTICE):
            parts.append(practice_subquery)
        if type_filter in (FeedTypeFilter.ALL, FeedTypeFilter.CHECKIN):
            parts.append(checkin_subquery)

        if not parts:
            return {"data": [], "next_cursor": None}

        union_sql = " UNION ALL ".join(parts)

        feed_sql = f"""
            WITH feed AS (
                {union_sql}
            )
            SELECT item_type, item_id, sort_time
            FROM feed
            WHERE (CAST(:cursor_time AS timestamptz) IS NULL
                   OR sort_time < CAST(:cursor_time AS timestamptz)
                   OR (sort_time = CAST(:cursor_time AS timestamptz) AND item_id < :cursor_id))
            ORDER BY sort_time DESC, item_id DESC
            LIMIT :limit
        """

        bind_params = {
            "cursor_time": cursor_time,
            "cursor_id": cursor_id if cursor_id is not None else 0,
            "limit": limit + 1,
        }
        if kw_param:
            bind_params["keyword"] = kw_param
        if tags:
            bind_params["tags"] = tags

        rows = db.execute(text(feed_sql), bind_params).fetchall()

        has_next = len(rows) > limit
        rows = rows[:limit]

        # --- 3. Separate IDs by type ---
        practice_ids = [r.item_id for r in rows if r.item_type == "practice"]
        checkin_ids = [r.item_id for r in rows if r.item_type == "checkin"]

        # --- 4. Batch fetch ---
        practices_map = FeedService._batch_fetch_practices(db, practice_ids)
        checkins_map = FeedService._batch_fetch_checkins(db, checkin_ids)
        reactions_map = FeedService._batch_fetch_reactions(
            db, {"practice": practice_ids, "checkin": checkin_ids}
        )
        comments_map = FeedService._batch_fetch_comments(
            db, {"practice": practice_ids, "checkin": checkin_ids}
        )

        # --- 5. Assemble feed items ---
        items = []
        for row in rows:
            if row.item_type == "practice" and row.item_id in practices_map:
                item = practices_map[row.item_id]
                item["reactions"] = reactions_map.get(("practice", row.item_id), [])
                comment_data = comments_map.get(("practice", row.item_id), {})
                item["comment_count"] = comment_data.get("count", 0)
                items.append({"type": "practice", "data": item})

            elif row.item_type == "checkin" and row.item_id in checkins_map:
                item = checkins_map[row.item_id]
                item["reactions"] = reactions_map.get(("checkin", row.item_id), [])
                comment_data = comments_map.get(("checkin", row.item_id), {})
                item["comment_count"] = comment_data.get("count", 0)
                item["comment_preview"] = comment_data.get("preview", [])
                items.append({"type": "checkin", "data": item})

        # --- 6. Build next_cursor ---
        next_cursor = None
        if has_next and rows:
            last = rows[-1]
            ts = last.sort_time.isoformat() if last.sort_time else ""
            next_cursor = f"{ts}_{last.item_id}"

        logger.info(f"feed: {len(items)} items, has_next={has_next}")
        return {"data": items, "next_cursor": next_cursor}

    # =========================================================================
    # Batch fetch helpers
    # =========================================================================

    @staticmethod
    def _batch_fetch_practices(db: Session, ids: list[int]) -> dict:
        """Batch fetch practices with user info (沿用 routers/users.py pattern)"""
        if not ids:
            return {}

        rows = db.execute(
            text(
                """
                SELECT
                    p.id,
                    p.external_id,
                    p.title,
                    p.status,
                    p.privacy_status,
                    p.practice_action,
                    p.start_date::text AS start_date,
                    p.end_date::text AS end_date,
                    p.frequency_min_days,
                    p.frequency_max_days,
                    p.session_duration_minutes,
                    p.created_at,
                    u.external_id AS user_external_id,
                    u.nickname AS user_name,
                    ct.photo_url AS user_photo_url
                FROM practices p
                JOIN users u ON u.id = p.user_id
                LEFT JOIN contacts ct ON ct.id = u.id
                WHERE p.id IN :ids
            """
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        ).fetchall()

        result = {}
        for r in rows:
            is_brewing = r.privacy_status == "delayed" and r.status == "active"
            result[r.id] = {
                "id": str(r.external_id),
                "title": r.title,
                "status": r.status,
                "privacy_status": r.privacy_status,
                "is_brewing": is_brewing,
                "practice_action": r.practice_action,
                "start_date": r.start_date,
                "end_date": r.end_date,
                "frequency_min_days": r.frequency_min_days,
                "frequency_max_days": r.frequency_max_days,
                "session_duration_minutes": r.session_duration_minutes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "user": {
                    "id": str(r.user_external_id) if r.user_external_id else None,
                    "name": r.user_name or "",
                    "photo_url": r.user_photo_url,
                },
            }
        return result

    @staticmethod
    def _batch_fetch_checkins(db: Session, ids: list[int]) -> dict:
        """Batch fetch checkins with practice title + user info"""
        if not ids:
            return {}

        rows = db.execute(
            text(
                """
                SELECT
                    c.id,
                    c.checkin_date::text AS checkin_date,
                    c.mood,
                    c.note,
                    c.image_urls,
                    c.created_at,
                    p.external_id AS practice_external_id,
                    p.title AS practice_title,
                    u.external_id AS user_external_id,
                    u.nickname AS user_name,
                    ct.photo_url AS user_photo_url
                FROM practice_checkins c
                JOIN practices p ON p.id = c.practice_id
                JOIN users u ON u.id = c.user_id
                LEFT JOIN contacts ct ON ct.id = u.id
                WHERE c.id IN :ids
            """
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        ).fetchall()

        result = {}
        for r in rows:
            result[r.id] = {
                "id": str(r.id),
                "checkin_date": r.checkin_date,
                "mood": r.mood,
                "note": r.note or "",
                "tags": [],  # checkin 自身無 tags，可透過 practice tags 衍生
                "image_urls": r.image_urls or [],
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "practice": {
                    "id": str(r.practice_external_id),
                    "title": r.practice_title,
                },
                "user": {
                    "id": str(r.user_external_id) if r.user_external_id else None,
                    "name": r.user_name or "",
                    "photo_url": r.user_photo_url,
                },
            }
        return result

    @staticmethod
    def _batch_fetch_reactions(db: Session, target_ids: dict) -> dict:
        """Batch fetch reactions (沿用 routers/users.py lines 188-211 pattern)"""
        result: dict = {}
        for target_type, ids in target_ids.items():
            if not ids:
                continue
            rows = db.execute(
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
                            WHERE r2.target_type = :target_type
                              AND r2.target_id = r.target_id
                              AND r2.reaction_type = r.reaction_type
                            ORDER BY r2.created_at DESC
                            LIMIT 1
                        ) AS latest_actor_name
                    FROM reactions r
                    WHERE r.target_type = :target_type
                      AND r.target_id IN :ids
                    GROUP BY r.target_id, r.reaction_type
                """
                ).bindparams(bindparam("ids", expanding=True)),
                {"target_type": target_type, "ids": ids},
            ).fetchall()

            for r in rows:
                key = (target_type, r.target_id)
                if key not in result:
                    result[key] = []
                result[key].append(
                    {
                        "type": r.reaction_type,
                        "count": r.cnt,
                        "latestActorName": r.latest_actor_name,
                    }
                )
        return result

    @staticmethod
    def _batch_fetch_comments(db: Session, target_ids: dict) -> dict:
        """Batch fetch comment counts + 2 preview comments per item"""
        result: dict = {}
        for target_type, ids in target_ids.items():
            if not ids:
                continue

            # 1. Counts
            count_rows = db.execute(
                text(
                    """
                    SELECT target_id, COUNT(*) AS cnt
                    FROM comments
                    WHERE target_type = :target_type
                      AND target_id IN :ids
                      AND visibility = 'public'
                    GROUP BY target_id
                """
                ).bindparams(bindparam("ids", expanding=True)),
                {"target_type": target_type, "ids": ids},
            ).fetchall()

            for r in count_rows:
                result[(target_type, r.target_id)] = {"count": r.cnt, "preview": []}

            # 2. Preview (latest 2 per target) using LATERAL join
            preview_rows = db.execute(
                text(
                    """
                    SELECT sub.target_id, sub.id, sub.content, sub.created_at,
                           u.external_id AS user_external_id,
                           u.nickname AS user_name,
                           ct.photo_url AS user_photo_url
                    FROM (
                        SELECT DISTINCT target_id AS target_id
                        FROM comments
                        WHERE target_type = :target_type
                          AND target_id IN :ids
                          AND visibility = 'public'
                    ) targets
                    CROSS JOIN LATERAL (
                        SELECT id, content, created_at, user_id, target_id
                        FROM comments
                        WHERE target_type = :target_type
                          AND target_id = targets.target_id
                          AND visibility = 'public'
                        ORDER BY created_at DESC
                        LIMIT 2
                    ) sub
                    JOIN users u ON u.id = sub.user_id
                    LEFT JOIN contacts ct ON ct.id = u.id
                """
                ).bindparams(bindparam("ids", expanding=True)),
                {"target_type": target_type, "ids": ids},
            ).fetchall()

            for r in preview_rows:
                key = (target_type, r.target_id)
                if key not in result:
                    result[key] = {"count": 0, "preview": []}
                result[key]["preview"].append(
                    {
                        "id": str(r.id),
                        "content": r.content,
                        "created_at": (
                            r.created_at.isoformat() if r.created_at else None
                        ),
                        "user": {
                            "id": (
                                str(r.user_external_id) if r.user_external_id else None
                            ),
                            "name": r.user_name or "",
                            "photo_url": r.user_photo_url,
                        },
                    }
                )
        return result
