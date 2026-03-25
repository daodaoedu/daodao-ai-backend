"""
Feed Service

統一 Feed 查詢：混合 practice + checkin，按時間排序。
沿用 routers/users.py 的 practice 查詢與 enrichment 模式。
"""

from typing import Optional

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from src.logger import AppLogger
from src.models.User import User
from src.schemas.feed import FeedSortBy, FeedTypeFilter

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
        sort_by: FeedSortBy = FeedSortBy.NEWEST,
    ) -> dict:
        """
        統一 feed 查詢：混合 practice + checkin，按時間排序。

        1. UNION query: practices + checkins → sorted by created_at
        2. Batch enrich: reactions, comments, user info
        3. Cursor pagination on (sort_time, item_id)

        current_user_external_id 用於：
        - Router 層 per-user cache key
        - 推薦排序的個人化 BehaviorSignal（用戶對 practice 的打卡頻率）
        TODO v2：
        - 在 feed response 中內嵌 currentUserReaction（減少前端 N+1）
        - 過濾已封鎖用戶的內容
        """
        # --- 0. Resolve user_id for personalization ---
        user_id: int | None = None
        if current_user_external_id:
            _user = (
                db.query(User)
                .filter(User.external_id == current_user_external_id)
                .first()
            )
            user_id = _user.id if _user else None

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
                items.append(
                    {
                        "type": "practice",
                        "data": item,
                        "_row": row,
                    }
                )

            elif row.item_type == "checkin" and row.item_id in checkins_map:
                item = checkins_map[row.item_id]
                item["reactions"] = reactions_map.get(("checkin", row.item_id), [])
                comment_data = comments_map.get(("checkin", row.item_id), {})
                item["comment_count"] = comment_data.get("count", 0)
                item["comment_preview"] = comment_data.get("preview", [])
                items.append(
                    {
                        "type": "checkin",
                        "data": item,
                        "_row": row,
                    }
                )

        # --- 5.5 Recommended sort ---
        if sort_by == FeedSortBy.RECOMMENDED and items:
            items = FeedService._apply_recommended_sort(items, db, user_id=user_id)

        # Strip internal _row before returning
        for item in items:
            item.pop("_row", None)

        # --- 6. Build next_cursor ---
        next_cursor = None
        if has_next and rows:
            last = rows[-1]
            ts = last.sort_time.isoformat() if last.sort_time else ""
            next_cursor = f"{ts}_{last.item_id}"

        logger.info(f"feed: {len(items)} items, has_next={has_next}")
        return {"data": items, "next_cursor": next_cursor}

    # =========================================================================
    # Ranking
    # =========================================================================

    @staticmethod
    def _apply_recommended_sort(
        items: list[dict],
        db: Session,
        user_id: Optional[int] = None,
    ) -> list[dict]:
        """Apply recommendation scoring with social graph personalization."""
        from datetime import datetime, timezone

        from src.services.feed.feed_ranking import (
            UserSocialGraph,
            score_checkin,
            score_practice,
        )

        now = datetime.now(timezone.utc)

        # --- 1. Build user's social graph (3 batch queries) ---
        social_graph = UserSocialGraph()
        if user_id:
            # 1a. Follows
            follow_rows = db.execute(
                text(
                    "SELECT target_type, target_id FROM follows WHERE follower_id = :uid"
                ),
                {"uid": user_id},
            ).fetchall()
            for r in follow_rows:
                if r.target_type == "user":
                    social_graph.following_user_ids.add(r.target_id)
                elif r.target_type == "practice":
                    social_graph.following_practice_ids.add(r.target_id)

            # 1b. Connections (normalized: user_a_id < user_b_id)
            conn_rows = db.execute(
                text(
                    """
                    SELECT user_a_id, user_b_id FROM connections
                    WHERE user_a_id = :uid OR user_b_id = :uid
                """
                ),
                {"uid": user_id},
            ).fetchall()
            for r in conn_rows:
                other = r.user_b_id if r.user_a_id == user_id else r.user_a_id
                social_graph.connected_user_ids.add(other)

            # 1c. Interaction counts
            interact_rows = db.execute(
                text(
                    """
                    SELECT user_a_id, user_b_id, count FROM interaction_counts
                    WHERE user_a_id = :uid OR user_b_id = :uid
                """
                ),
                {"uid": user_id},
            ).fetchall()
            for r in interact_rows:
                other = r.user_b_id if r.user_a_id == user_id else r.user_a_id
                social_graph.interaction_counts[other] = r.count or 0

        # --- 2. Batch fetch extra practice fields ---
        practice_ids = [it["_row"].item_id for it in items if it["type"] == "practice"]
        practice_extra = {}
        if practice_ids:
            rows = db.execute(
                text(
                    """
                    SELECT id, user_id, has_resources, progress_percentage, template_id, updated_at
                    FROM practices WHERE id IN :ids
                """
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": practice_ids},
            ).fetchall()
            for r in rows:
                practice_extra[r.id] = r

        # --- 3. Batch fetch checkin owner info ---
        checkin_ids = [it["_row"].item_id for it in items if it["type"] == "checkin"]
        checkin_extra = {}
        if checkin_ids:
            rows = db.execute(
                text(
                    """
                    SELECT c.id, c.user_id, c.practice_id, c.image_urls, c.note, c.mood
                    FROM practice_checkins c WHERE c.id IN :ids
                """
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": checkin_ids},
            ).fetchall()
            for r in rows:
                checkin_extra[r.id] = r

        # --- 4. Score each item ---
        scored = []
        for item in items:
            row = item["_row"]
            reactions = item["data"].get("reactions", [])
            reaction_count = sum(r.get("count", 0) for r in reactions)
            comment_count = item["data"].get("comment_count", 0)

            if item["type"] == "practice":
                extra = practice_extra.get(row.item_id)
                owner_id = extra.user_id if extra else None
                s = score_practice(
                    extra or row,
                    reaction_count,
                    comment_count,
                    now,
                    social_graph=social_graph if user_id else None,
                    owner_user_id=owner_id,
                    practice_internal_id=row.item_id,
                )
            else:
                extra = checkin_extra.get(row.item_id)
                owner_id = extra.user_id if extra else None
                practice_id = extra.practice_id if extra else None
                s = score_checkin(
                    extra or row,
                    reaction_count,
                    comment_count,
                    now,
                    social_graph=social_graph if user_id else None,
                    owner_user_id=owner_id,
                    practice_internal_id=practice_id,
                )

            scored.append((s, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored]

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
                LEFT JOIN contacts ct ON ct.id = u.contact_id
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
                LEFT JOIN contacts ct ON ct.id = u.contact_id
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
                    LEFT JOIN contacts ct ON ct.id = u.contact_id
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
