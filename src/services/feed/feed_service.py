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
from src.schemas.feed import (
    ActivityType,
    FeedReasonType,
    FeedSortBy,
    FeedTypeFilter,
    SlotType,
)

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
        統一 feed 查詢：混合 practice + checkin。

        type_filter=ALL → Slot Pattern (A→B→C→C→C 循環)
        type_filter=PRACTICE|CHECKIN → 單類型時序回傳

        current_user_external_id 用於 Router 層 per-user cache key。
        """
        user_id: int | None = None
        if current_user_external_id:
            _user = (
                db.query(User)
                .filter(User.external_id == current_user_external_id)
                .first()
            )
            user_id = _user.id if _user else None

        if type_filter == FeedTypeFilter.ALL:
            return FeedService._get_feed_slot_pattern(
                db, user_id, cursor, limit, keyword, tags
            )
        return FeedService._get_feed_single_type(
            db, user_id, cursor, limit, keyword, tags, type_filter
        )

    # =========================================================================
    # Slot Pattern Feed (type_filter=ALL)
    # =========================================================================

    @staticmethod
    def _get_feed_slot_pattern(
        db: Session,
        user_id: Optional[int],
        cursor: Optional[str],
        limit: int,
        keyword: Optional[str],
        tags: Optional[list[str]],
    ) -> dict:
        """Assemble feed in A→B→C→C→C slot cycles."""
        p_cursor_time, p_cursor_id, c_cursor_time, c_cursor_id = (
            FeedService._parse_dual_cursor(cursor)
        )

        max_cycles = max(1, limit // 5)

        # Fetch one extra cycle to determine whether another完整循環 still exists.
        practice_rows = FeedService._fetch_practice_pool(
            db, p_cursor_time, p_cursor_id, max_cycles * 3 + 3, keyword, tags
        )
        checkin_rows = FeedService._fetch_checkin_pool_with_counts(
            db, c_cursor_time, c_cursor_id, max_cycles * 2 + 2, keyword, tags
        )

        # Fetch cheered pool for Slot B (one per cycle)
        cheered_rows = FeedService._fetch_cheered_pool(db, max_cycles, keyword, tags)

        slot_assignments, p_idx, c_idx = FeedService._assemble_slot_cycles(
            practice_rows,
            checkin_rows,
            cheered_rows,
            max_cycles,
            max_items=limit,
        )

        if not slot_assignments:
            return {"data": [], "next_cursor": None}

        practice_ids = [
            s["item_id"] for s in slot_assignments if s["item_type"] == "practice"
        ]
        checkin_ids = [
            s["item_id"] for s in slot_assignments if s["item_type"] == "checkin"
        ]

        practices_map = FeedService._batch_fetch_practices(db, practice_ids)
        checkins_map = FeedService._batch_fetch_checkins(db, checkin_ids)
        reactions_map = FeedService._batch_fetch_reactions(
            db, {"practice": practice_ids, "checkin": checkin_ids}
        )
        comments_map = FeedService._batch_fetch_comments(
            db, {"practice": practice_ids, "checkin": checkin_ids}
        )

        items = []
        for slot in slot_assignments:
            item_type = slot["item_type"]
            item_id = slot["item_id"]
            slot_type = slot["slot_type"]
            feed_source = slot.get("feed_source", "original")

            if item_type == "activity":
                # Slot B ActivityCard injected directly
                items.append(slot["card"])
                continue

            if item_type == "practice" and item_id in practices_map:
                item = practices_map[item_id]
                item["reactions"] = reactions_map.get(("practice", item_id), [])
                comment_data = comments_map.get(("practice", item_id), {})
                item["comment_count"] = comment_data.get("count", 0)
                if feed_source == "cheered":
                    feed_reason = FeedReasonType.cheered
                    latest_actor_name = FeedService._get_latest_actor_name(
                        item["reactions"]
                    )
                else:
                    feed_reason = (
                        FeedReasonType.new_release
                        if item.get("is_brewing")
                        else FeedReasonType.new_practice
                    )
                    latest_actor_name = None
                feed_item: dict = {
                    "type": "practice",
                    "data": item,
                    "feed_reason": feed_reason,
                    "slot_type": slot_type,
                }
                if latest_actor_name is not None:
                    feed_item["latest_actor_name"] = latest_actor_name
                items.append(feed_item)

            elif item_type == "checkin" and item_id in checkins_map:
                item = checkins_map[item_id]
                item["reactions"] = reactions_map.get(("checkin", item_id), [])
                comment_data = comments_map.get(("checkin", item_id), {})
                item["comment_count"] = comment_data.get("count", 0)
                item["comment_preview"] = comment_data.get("preview", [])
                if feed_source == "cheered":
                    feed_reason = FeedReasonType.cheered
                    latest_actor_name = FeedService._get_latest_actor_name(
                        item["reactions"]
                    )
                else:
                    feed_reason = FeedReasonType.checked_in
                    latest_actor_name = None
                feed_item = {
                    "type": "checkin",
                    "data": item,
                    "feed_reason": feed_reason,
                    "slot_type": slot_type,
                }
                if latest_actor_name is not None:
                    feed_item["latest_actor_name"] = latest_actor_name
                items.append(feed_item)

        has_next = len(practice_rows) >= p_idx + 3
        next_cursor = None
        if has_next:
            p_last = ""
            if p_idx > 0:
                last_p = practice_rows[min(p_idx, len(practice_rows)) - 1]
                p_ts = last_p.sort_time.isoformat() if last_p.sort_time else ""
                p_last = f"{p_ts}_{last_p.item_id}"
            c_last = ""
            if c_idx > 0:
                last_c = checkin_rows[min(c_idx, len(checkin_rows)) - 1]
                c_ts = last_c.sort_time.isoformat() if last_c.sort_time else ""
                c_last = f"{c_ts}_{last_c.item_id}"
            next_cursor = f"{p_last}|{c_last}"

        logger.info(f"feed (slot): {len(items)} items, has_next={has_next}")
        return {"data": items, "next_cursor": next_cursor}

    # =========================================================================
    # Single-type Feed (type_filter=PRACTICE or CHECKIN)
    # =========================================================================

    @staticmethod
    def _get_feed_single_type(
        db: Session,
        user_id: Optional[int],
        cursor: Optional[str],
        limit: int,
        keyword: Optional[str],
        tags: Optional[list[str]],
        type_filter: FeedTypeFilter,
    ) -> dict:
        cursor_time, cursor_id = FeedService._parse_cursor_part(cursor or "")

        if type_filter == FeedTypeFilter.PRACTICE:
            rows = FeedService._fetch_practice_pool(
                db, cursor_time, cursor_id, limit + 1, keyword, tags
            )
            has_next = len(rows) > limit
            rows = rows[:limit]

            practice_ids = [r.item_id for r in rows]
            practices_map = FeedService._batch_fetch_practices(db, practice_ids)
            reactions_map = FeedService._batch_fetch_reactions(
                db, {"practice": practice_ids, "checkin": []}
            )
            comments_map = FeedService._batch_fetch_comments(
                db, {"practice": practice_ids, "checkin": []}
            )

            items = []
            for row in rows:
                if row.item_id in practices_map:
                    item = practices_map[row.item_id]
                    item["reactions"] = reactions_map.get(("practice", row.item_id), [])
                    comment_data = comments_map.get(("practice", row.item_id), {})
                    item["comment_count"] = comment_data.get("count", 0)
                    feed_reason = (
                        FeedReasonType.new_release
                        if item.get("is_brewing")
                        else FeedReasonType.new_practice
                    )
                    items.append(
                        {
                            "type": "practice",
                            "data": item,
                            "feed_reason": feed_reason,
                            "slot_type": SlotType.C,
                        }
                    )

        else:  # CHECKIN
            rows = FeedService._fetch_checkin_pool_with_counts(
                db, cursor_time, cursor_id, limit + 1, keyword, tags
            )
            has_next = len(rows) > limit
            rows = rows[:limit]

            checkin_ids = [r.item_id for r in rows]
            checkins_map = FeedService._batch_fetch_checkins(db, checkin_ids)
            reactions_map = FeedService._batch_fetch_reactions(
                db, {"practice": [], "checkin": checkin_ids}
            )
            comments_map = FeedService._batch_fetch_comments(
                db, {"practice": [], "checkin": checkin_ids}
            )

            items = []
            for row in rows:
                if row.item_id in checkins_map:
                    item = checkins_map[row.item_id]
                    item["reactions"] = reactions_map.get(("checkin", row.item_id), [])
                    comment_data = comments_map.get(("checkin", row.item_id), {})
                    item["comment_count"] = comment_data.get("count", 0)
                    item["comment_preview"] = comment_data.get("preview", [])
                    items.append(
                        {
                            "type": "checkin",
                            "data": item,
                            "feed_reason": FeedReasonType.checked_in,
                            "slot_type": SlotType.A,
                        }
                    )

        next_cursor = None
        if has_next and rows:
            last = rows[-1]
            ts = last.sort_time.isoformat() if last.sort_time else ""
            next_cursor = f"{ts}_{last.item_id}"

        logger.info(
            f"feed (single-type={type_filter.value}): {len(items)} items, has_next={has_next}"
        )
        return {"data": items, "next_cursor": next_cursor}

    # =========================================================================
    # Slot Pattern Helpers
    # =========================================================================

    @staticmethod
    def _parse_cursor_part(part: str) -> tuple[Optional[str], Optional[int]]:
        if not part:
            return None, None
        parts = part.rsplit("_", 1)
        if len(parts) == 2:
            try:
                return parts[0], int(parts[1])
            except ValueError:
                pass
        return None, None

    @staticmethod
    def _parse_dual_cursor(
        cursor: Optional[str],
    ) -> tuple[Optional[str], Optional[int], Optional[str], Optional[int]]:
        """Parse dual cursor format: '{practice_part}|{checkin_part}'."""
        if not cursor:
            return None, None, None, None
        if "|" in cursor:
            p_part, c_part = cursor.split("|", 1)
        else:
            p_part, c_part = cursor, ""
        p_time, p_id = FeedService._parse_cursor_part(p_part)
        c_time, c_id = FeedService._parse_cursor_part(c_part)
        return p_time, p_id, c_time, c_id

    @staticmethod
    def _fetch_practice_pool(
        db: Session,
        cursor_time: Optional[str],
        cursor_id: Optional[int],
        limit: int,
        keyword: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list:
        where_clauses = [
            "p.privacy_status = 'public'",
            "p.status IN ('active', 'completed')",
            "p.deleted_at IS NULL",
        ]
        bind_params: dict = {"limit": limit}

        if cursor_time and cursor_id is not None:
            where_clauses.append(
                "(p.created_at < CAST(:p_cursor_time AS timestamptz)"
                " OR (p.created_at = CAST(:p_cursor_time AS timestamptz) AND p.id < :p_cursor_id))"
            )
            bind_params["p_cursor_time"] = cursor_time
            bind_params["p_cursor_id"] = cursor_id

        if keyword:
            escaped = (
                keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            where_clauses.append(
                "(p.title ILIKE :keyword OR p.practice_action ILIKE :keyword)"
            )
            bind_params["keyword"] = f"%{escaped}%"

        if tags:
            where_clauses.append(
                "EXISTS (SELECT 1 FROM entity_tags et JOIN tags t ON t.id = et.tag_id"
                " WHERE et.entity_type = 'practice'"
                " AND et.entity_id = p.id AND t.name = ANY(:tags))"
            )
            bind_params["tags"] = tags

        where_sql = " AND ".join(where_clauses)
        sql = f"""
            SELECT p.id AS item_id, p.created_at AS sort_time
            FROM practices p
            WHERE {where_sql}
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT :limit
        """
        return db.execute(text(sql), bind_params).fetchall()

    @staticmethod
    def _fetch_checkin_pool_with_counts(
        db: Session,
        cursor_time: Optional[str],
        cursor_id: Optional[int],
        limit: int,
        keyword: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list:
        """Fetch checkins with reactions_count + comments_count for Slot A count logic."""
        where_clauses = [
            "p.privacy_status = 'public'",
            "p.status IN ('active', 'completed')",
            "p.deleted_at IS NULL",
        ]
        bind_params: dict = {"limit": limit}

        if cursor_time and cursor_id is not None:
            where_clauses.append(
                "(c.created_at < CAST(:c_cursor_time AS timestamptz)"
                " OR (c.created_at = CAST(:c_cursor_time AS timestamptz) AND c.id < :c_cursor_id))"
            )
            bind_params["c_cursor_time"] = cursor_time
            bind_params["c_cursor_id"] = cursor_id

        if keyword:
            escaped = (
                keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            where_clauses.append("c.note ILIKE :keyword")
            bind_params["keyword"] = f"%{escaped}%"

        if tags:
            where_clauses.append(
                "EXISTS (SELECT 1 FROM entity_tags et JOIN tags t ON t.id = et.tag_id"
                " WHERE et.entity_type = 'practice' AND et.entity_id = c.practice_id"
                " AND t.name = ANY(:tags))"
            )
            bind_params["tags"] = tags

        where_sql = " AND ".join(where_clauses)
        sql = f"""
            SELECT
                c.id AS item_id,
                c.created_at AS sort_time,
                c.user_id,
                COUNT(DISTINCT r.id) AS reactions_count,
                COUNT(DISTINCT cm.id) AS comments_count
            FROM practice_checkins c
            JOIN practices p ON p.id = c.practice_id
            LEFT JOIN reactions r ON r.target_type = 'checkin' AND r.target_id = c.id
            LEFT JOIN comments cm
                ON cm.target_type = 'checkin' AND cm.target_id = c.id
                AND cm.visibility = 'public'
            WHERE {where_sql}
            GROUP BY c.id, c.created_at, c.user_id
            ORDER BY c.created_at DESC, c.id DESC
            LIMIT :limit
        """
        return db.execute(text(sql), bind_params).fetchall()

    @staticmethod
    def _fetch_cheered_pool(
        db: Session,
        limit: int,
        keyword: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list:
        """
        Fetch recently cheered practices and checkins for Slot B.

        Uses MAX(r.created_at) as sort_time, DISTINCT ON (item_type, item_id)
        to avoid duplicates. Returns mixed practice + checkin rows ordered by
        the most recent reaction time.
        """
        practice_where = [
            "p.privacy_status = 'public'",
            "p.status IN ('active', 'completed')",
            "p.deleted_at IS NULL",
        ]
        checkin_where = [
            "p.privacy_status = 'public'",
            "p.status IN ('active', 'completed')",
            "p.deleted_at IS NULL",
        ]
        bind_params: dict = {"limit": limit}

        if keyword:
            escaped = (
                keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            practice_where.append(
                "(p.title ILIKE :keyword OR p.practice_action ILIKE :keyword)"
            )
            checkin_where.append("c.note ILIKE :keyword")
            bind_params["keyword"] = f"%{escaped}%"

        if tags:
            practice_where.append(
                "EXISTS (SELECT 1 FROM entity_tags et JOIN tags t ON t.id = et.tag_id"
                " WHERE et.entity_type = 'practice' AND et.entity_id = p.id"
                " AND t.name = ANY(:tags))"
            )
            checkin_where.append(
                "EXISTS (SELECT 1 FROM entity_tags et JOIN tags t ON t.id = et.tag_id"
                " WHERE et.entity_type = 'practice' AND et.entity_id = c.practice_id"
                " AND t.name = ANY(:tags))"
            )
            bind_params["tags"] = tags

        p_where_sql = " AND ".join(practice_where)
        c_where_sql = " AND ".join(checkin_where)

        sql = f"""
            SELECT item_type, item_id, sort_time
            FROM (
                SELECT DISTINCT ON (item_type, item_id)
                    item_type, item_id, sort_time
                FROM (
                    SELECT
                        'practice' AS item_type,
                        r.target_id AS item_id,
                        MAX(r.created_at) AS sort_time
                    FROM reactions r
                    JOIN practices p ON p.id = r.target_id
                    WHERE r.target_type = 'practice'
                      AND {p_where_sql}
                    GROUP BY r.target_id
                    UNION ALL
                    SELECT
                        'checkin' AS item_type,
                        r.target_id AS item_id,
                        MAX(r.created_at) AS sort_time
                    FROM reactions r
                    JOIN practice_checkins c ON c.id = r.target_id
                    JOIN practices p ON p.id = c.practice_id
                    WHERE r.target_type = 'checkin'
                      AND {c_where_sql}
                    GROUP BY r.target_id
                ) combined
                ORDER BY item_type, item_id, sort_time DESC
            ) deduped
            ORDER BY sort_time DESC
            LIMIT :limit
        """
        return db.execute(text(sql), bind_params).fetchall()

    @staticmethod
    def _get_latest_actor_name(reactions: list[dict]) -> Optional[str]:
        """Extract the latest actor name from a reactions list."""
        for r in reactions:
            name = r.get("latestActorName")
            if name:
                return name
        return None

    @staticmethod
    def _build_activity_card_slot() -> Optional[dict]:
        """Build a Slot B ActivityCard dict with community stats (no DB needed)."""
        return {
            "type": "activity",
            "activity_type": ActivityType.COMMUNITY_EVENT.value,
            "event_text": "社群最近很活躍，快來看看大家在練什麼！",
            "label": "學習動態",
            "slot_type": SlotType.B,
        }

    @staticmethod
    def _select_slot_a(available: list) -> tuple[list, int]:
        """
        Select 1 or 2 checkins for Slot A from the front of the available pool.

        Priority:
          1. Hot (reactions >= 1 or comments >= 1) → 1 item
          2. Cold start, pool >= 2, different user_ids → 2 items
          3. Fallback → 1 item; empty pool → 0 items (skip slot)
        """
        if not available:
            return [], 0

        first = available[0]
        is_hot = first.reactions_count >= 1 or first.comments_count >= 1

        if is_hot:
            return [first], 1

        # Cold start: two items with different owners
        if len(available) >= 2 and available[1].user_id != first.user_id:
            return [first, available[1]], 2

        return [first], 1

    @staticmethod
    def _assemble_slot_cycles(
        practice_rows: list,
        checkin_rows: list,
        cheered_rows: list,
        num_cycles: int,
        max_items: Optional[int] = None,
    ) -> tuple[list[dict], int, int]:
        """
        Assemble A→B→C→C→C cycles.

        Slot A: checkin(s) — skipped if pool empty.
        Slot B: ActivityCard (cheered item or community stats card) — skipped if unavailable.
        Slot C: 3 practices per cycle — stops if fewer than 3 remain.

        Returns (slot_assignments, p_idx_consumed, c_idx_consumed).
        """
        slots: list[dict] = []
        p_idx = 0
        c_idx = 0
        ch_idx = 0

        for _ in range(num_cycles):
            # Slot C requires 3 practices; stop if not enough
            if p_idx + 3 > len(practice_rows):
                break

            cycle_slots: list[dict] = []
            consumed_checkins = 0

            # Slot A: checkins (skip if pool empty)
            if c_idx < len(checkin_rows):
                a_rows, consumed_checkins = FeedService._select_slot_a(
                    checkin_rows[c_idx:]
                )
                for row in a_rows:
                    cycle_slots.append(
                        {
                            "slot_type": SlotType.A,
                            "item_type": "checkin",
                            "item_id": row.item_id,
                            "feed_source": "original",
                        }
                    )

            # Slot B: one item per cycle, falling back to ActivityCard
            if ch_idx < len(cheered_rows):
                ch_row = cheered_rows[ch_idx]
                cycle_slots.append(
                    {
                        "slot_type": SlotType.B,
                        "item_type": ch_row.item_type,
                        "item_id": ch_row.item_id,
                        "feed_source": "cheered",
                    }
                )
            else:
                activity_card = FeedService._build_activity_card_slot()
                if activity_card:
                    cycle_slots.append(
                        {
                            "slot_type": SlotType.B,
                            "item_type": "activity",
                            "item_id": 0,
                            "feed_source": "activity",
                            "card": activity_card,
                        }
                    )

            # Slot C: 3 practices
            for i in range(3):
                cycle_slots.append(
                    {
                        "slot_type": SlotType.C,
                        "item_type": "practice",
                        "item_id": practice_rows[p_idx + i].item_id,
                        "feed_source": "original",
                    }
                )

            if (
                max_items is not None
                and len(slots) + len(cycle_slots) > max_items
                and slots
            ):
                break

            slots.extend(cycle_slots)
            c_idx += consumed_checkins
            if ch_idx < len(cheered_rows):
                ch_idx += 1
            p_idx += 3

        return slots, p_idx, c_idx

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
