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
    FeedReasonType,
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
        """Assemble feed in A→B→C slot cycles (1:1:1 ratio)."""
        (
            p_cursor_time,
            p_cursor_id,
            c_cursor_time,
            c_cursor_id,
            _,
            _,
        ) = FeedService._parse_dual_cursor(cursor)

        # 1:1 cycle: each cycle = 1 checkin + 1 practice
        max_cycles = max(1, limit // 2)

        # Rule ③ skips up to 2 practices per cycle → need 3x buffer + 1 to detect has_next.
        practice_rows = FeedService._fetch_practice_pool(
            db, p_cursor_time, p_cursor_id, max_cycles * 3 + 1, keyword, tags
        )
        # Extra buffer for checkins so cold-start cycles never starve.
        checkin_rows = FeedService._fetch_checkin_pool_with_counts(
            db, c_cursor_time, c_cursor_id, max_cycles * 2 + 4, keyword, tags
        )

        # Personalized ranking: re-sort pools by social + engagement score.
        social_graph = FeedService._fetch_social_graph(db, user_id) if user_id else None
        weights = FeedService._load_ranking_weights(db)
        practice_rows, checkin_rows = FeedService._apply_ranking(
            practice_rows, checkin_rows, social_graph, weights
        )

        slot_assignments, p_idx, c_idx, last_consumed_practice = (
            FeedService._assemble_slot_cycles(
                practice_rows,
                checkin_rows,
                max_cycles,
                max_items=limit,
            )
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

        social_user_ids = set()
        if social_graph:
            social_user_ids = (
                social_graph.connected_user_ids | social_graph.following_user_ids
            )
        cheered_practice_ids = FeedService._batch_fetch_cheered_practice_ids(
            db, practice_ids, social_user_ids
        )

        items = []
        for slot in slot_assignments:
            item_type = slot["item_type"]
            item_id = slot["item_id"]
            slot_type = slot["slot_type"]

            if item_type == "practice" and item_id in practices_map:
                item = practices_map[item_id]
                item["reactions"] = reactions_map.get(("practice", item_id), [])
                comment_data = comments_map.get(("practice", item_id), {})
                item["comment_count"] = comment_data.get("count", 0)
                if item.get("is_featured"):
                    feed_reason = FeedReasonType.featured
                elif item.get("is_brewing"):
                    feed_reason = FeedReasonType.new_release
                elif item_id in cheered_practice_ids:
                    feed_reason = FeedReasonType.cheered
                else:
                    feed_reason = FeedReasonType.new_practice
                items.append(
                    {
                        "type": "practice",
                        "data": item,
                        "feed_reason": feed_reason,
                        "slot_type": slot_type,
                    }
                )

            elif item_type == "checkin" and item_id in checkins_map:
                item = checkins_map[item_id]
                item["reactions"] = reactions_map.get(("checkin", item_id), [])
                comment_data = comments_map.get(("checkin", item_id), {})
                item["comment_count"] = comment_data.get("count", 0)
                item["comment_preview"] = comment_data.get("preview", [])
                items.append(
                    {
                        "type": "checkin",
                        "data": item,
                        "feed_reason": FeedReasonType.checked_in,
                        "slot_type": slot_type,
                    }
                )

        # has_next: practice 或 checkin 任一 pool 還有剩餘就繼續分頁
        has_next = p_idx < len(practice_rows) or c_idx < len(checkin_rows)
        next_cursor = None
        if has_next:
            p_last = ""
            # 用最後 evaluated 的 practice 作為 cursor，確保跳過所有已處理的（含 Rule ③ 跳過的）
            p_ref = practice_rows[p_idx - 1] if p_idx > 0 else None
            if p_ref is not None:
                p_ts = p_ref.sort_time.isoformat() if p_ref.sort_time else ""
                p_last = f"{p_ts}_{p_ref.item_id}"
            c_last = ""
            if c_idx > 0:
                last_c = checkin_rows[c_idx - 1]
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

            social_user_ids: set[int] = set()
            if user_id:
                social_graph = FeedService._fetch_social_graph(db, user_id)
                social_user_ids = (
                    social_graph.connected_user_ids | social_graph.following_user_ids
                )
            cheered_practice_ids = FeedService._batch_fetch_cheered_practice_ids(
                db, practice_ids, social_user_ids
            )

            items = []
            for row in rows:
                if row.item_id in practices_map:
                    item = practices_map[row.item_id]
                    item["reactions"] = reactions_map.get(("practice", row.item_id), [])
                    comment_data = comments_map.get(("practice", row.item_id), {})
                    item["comment_count"] = comment_data.get("count", 0)
                    if item.get("is_featured"):
                        feed_reason = FeedReasonType.featured
                    elif item.get("is_brewing"):
                        feed_reason = FeedReasonType.new_release
                    elif row.item_id in cheered_practice_ids:
                        feed_reason = FeedReasonType.cheered
                    else:
                        feed_reason = FeedReasonType.new_practice
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
    ) -> tuple[
        Optional[str],
        Optional[int],
        Optional[str],
        Optional[int],
        Optional[str],
        Optional[int],
    ]:
        """Parse cursor: '{practice_part}|{checkin_part}[|ignored_legacy_part]'."""
        if not cursor:
            return None, None, None, None, None, None
        parts = cursor.split("|", 2)
        p_time, p_id = FeedService._parse_cursor_part(
            parts[0] if len(parts) > 0 else ""
        )
        c_time, c_id = FeedService._parse_cursor_part(
            parts[1] if len(parts) > 1 else ""
        )
        ch_time, ch_id = FeedService._parse_cursor_part(
            parts[2] if len(parts) > 2 else ""
        )
        return p_time, p_id, c_time, c_id, ch_time, ch_id

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
            "(p.privacy_status = 'public' OR (p.privacy_status = 'delayed' AND p.status = 'completed'))",
            "p.status IN ('active', 'completed')",
            "p.deleted_at IS NULL",
            # Rule ④: 主題實踐需在 30 天內有打卡紀錄才出現
            "EXISTS ("
            "  SELECT 1 FROM practice_checkins pc"
            "  WHERE pc.practice_id = p.id"
            "    AND pc.created_at >= NOW() - INTERVAL '30 days'"
            ")",
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
                "(p.title ILIKE :keyword ESCAPE '\\' OR p.practice_action ILIKE :keyword ESCAPE '\\')"
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
            SELECT
                p.id AS item_id,
                p.created_at AS sort_time,
                p.user_id,
                p.updated_at,
                (COALESCE(p.is_featured, FALSE)
                    AND (p.featured_start_at IS NULL OR p.featured_start_at <= NOW())
                    AND (p.featured_end_at IS NULL OR p.featured_end_at > NOW())
                ) AS is_featured,
                COUNT(DISTINCT r.id) AS reactions_count,
                COUNT(DISTINCT cm.id) AS comments_count
            FROM practices p
            LEFT JOIN reactions r ON r.target_type = 'practice' AND r.target_id = p.id
            LEFT JOIN comments cm
                ON cm.target_type = 'practice' AND cm.target_id = p.id
                AND cm.visibility = 'public'
            WHERE {where_sql}
            GROUP BY p.id, p.created_at, p.user_id, p.updated_at,
                p.is_featured, p.featured_start_at, p.featured_end_at
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
            "(p.privacy_status = 'public' OR (p.privacy_status = 'delayed' AND p.status = 'completed'))",
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
            where_clauses.append("c.note ILIKE :keyword ESCAPE '\\'")
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
                c.practice_id,
                COUNT(DISTINCT r.id) AS reactions_count,
                COUNT(DISTINCT cm.id) AS comments_count
            FROM practice_checkins c
            JOIN practices p ON p.id = c.practice_id
            LEFT JOIN reactions r ON r.target_type = 'checkin' AND r.target_id = c.id
            LEFT JOIN comments cm
                ON cm.target_type = 'checkin' AND cm.target_id = c.id
                AND cm.visibility = 'public'
            WHERE {where_sql}
            GROUP BY c.id, c.created_at, c.user_id, c.practice_id
            ORDER BY c.created_at DESC, c.id DESC
            LIMIT :limit
        """
        return db.execute(text(sql), bind_params).fetchall()

    # =========================================================================
    # Social Graph
    # =========================================================================

    @staticmethod
    def _fetch_social_graph(db: Session, user_id: int):
        """Load current user's social relationships for feed personalization."""
        from src.services.feed.feed_ranking import UserSocialGraph

        following_users = db.execute(
            text(
                "SELECT target_id FROM follows"
                " WHERE follower_id = :uid AND target_type = 'user'"
            ),
            {"uid": user_id},
        ).fetchall()

        following_practices = db.execute(
            text(
                "SELECT target_id FROM follows"
                " WHERE follower_id = :uid AND target_type = 'practice'"
            ),
            {"uid": user_id},
        ).fetchall()

        connections = db.execute(
            text(
                "SELECT CASE WHEN user_a_id = :uid THEN user_b_id ELSE user_a_id END AS other_id"
                " FROM connections WHERE user_a_id = :uid OR user_b_id = :uid"
            ),
            {"uid": user_id},
        ).fetchall()

        interactions = db.execute(
            text(
                """
                SELECT c.user_id AS target_user_id, COUNT(*) AS cnt
                FROM reactions r
                JOIN practice_checkins c ON c.id = r.target_id
                WHERE r.target_type = 'checkin' AND r.user_id = :uid
                GROUP BY c.user_id
                """
            ),
            {"uid": user_id},
        ).fetchall()

        return UserSocialGraph(
            following_user_ids={r.target_id for r in following_users},
            following_practice_ids={r.target_id for r in following_practices},
            connected_user_ids={r.other_id for r in connections},
            interaction_counts={r.target_user_id: r.cnt for r in interactions},
        )

    @staticmethod
    def _load_ranking_weights(db: Session):
        """讀取 admin 後台設定的 active 排序權重；查無或失敗時退回程式碼預設值。"""
        from src.services.feed.feed_ranking import DEFAULT_WEIGHTS, RankingWeights

        try:
            from src.models.FeedRankingConfig import FeedRankingConfig

            config = (
                db.query(FeedRankingConfig)
                .filter(FeedRankingConfig.is_active.is_(True))
                .first()
            )
            if config:
                return RankingWeights(
                    w_social=float(config.w_social),
                    w_engagement=float(config.w_engagement),
                    w_content=float(config.w_content),
                    w_decay=float(config.w_decay),
                    w_freshness=float(config.w_freshness),
                    freshness_window_hours=int(config.freshness_window_hours),
                    w_featured=float(config.w_featured),
                )
        except Exception:
            logger.warning(
                "failed to load feed_ranking_configs, falling back to defaults",
                exc_info=True,
            )
            # 失敗的查詢會讓交易進入 aborted 狀態，必須 rollback
            # 否則同一 session 的後續 feed 查詢全數失敗
            try:
                db.rollback()
            except Exception:
                logger.warning("rollback after config load failure also failed")
        return DEFAULT_WEIGHTS

    @staticmethod
    def _apply_ranking(
        practice_rows: list,
        checkin_rows: list,
        social_graph,
        weights=None,
    ) -> tuple[list, list]:
        """Re-score and re-sort practice and checkin pools by personalized score."""
        from datetime import datetime, timezone

        from src.services.feed.feed_ranking import (
            DEFAULT_WEIGHTS,
            score_checkin,
            score_practice,
        )

        weights = weights or DEFAULT_WEIGHTS
        now = datetime.now(timezone.utc)

        scored_p = [
            (
                score_practice(
                    practice_row=row,
                    reaction_count=getattr(row, "reactions_count", 0) or 0,
                    comment_count=getattr(row, "comments_count", 0) or 0,
                    now=now,
                    social_graph=social_graph,
                    owner_user_id=getattr(row, "user_id", None),
                    practice_internal_id=row.item_id,
                    weights=weights,
                ),
                row,
            )
            for row in practice_rows
        ]
        scored_p.sort(key=lambda x: x[0], reverse=True)

        scored_c = [
            (
                score_checkin(
                    checkin_row=row,
                    reaction_count=getattr(row, "reactions_count", 0) or 0,
                    comment_count=getattr(row, "comments_count", 0) or 0,
                    now=now,
                    social_graph=social_graph,
                    owner_user_id=getattr(row, "user_id", None),
                    weights=weights,
                ),
                row,
            )
            for row in checkin_rows
        ]
        scored_c.sort(key=lambda x: x[0], reverse=True)

        return [r for _, r in scored_p], [r for _, r in scored_c]

    # =========================================================================

    @staticmethod
    def _select_slot_a(available: list) -> tuple[list, int]:
        """
        Select 1 or 2 checkins for Slot A from the front of the available pool.

        Priority:
          1. Hot (reactions >= 1 or comments >= 1) → 1 item
          2. Both items are cold (reactions=0, comments=0) and from different user_ids → 2 items
          3. Fallback → 1 item; empty pool → 0 items (skip slot)
        """
        if not available:
            return [], 0

        first = available[0]
        is_hot = first.reactions_count >= 1 or first.comments_count >= 1

        if is_hot:
            return [first], 1

        # Cold start: both items must be cold AND from different owners
        if len(available) >= 2:
            second = available[1]
            second_is_cold = second.reactions_count == 0 and second.comments_count == 0
            if second_is_cold and second.user_id != first.user_id:
                return [first, second], 2

        return [first], 1

    @staticmethod
    def _assemble_slot_cycles(
        practice_rows: list,
        checkin_rows: list,
        num_cycles: int,
        max_items: Optional[int] = None,
    ) -> tuple[list[dict], int, int, object]:
        """
        Assemble A→C cycles (1:1).

        Slot A: checkin(s) — skipped if pool empty.
        Slot C: 1 practice per cycle — Rule ③: skip practices whose practice_id
                was already assigned to Slot A on this page.

        Returns (slot_assignments, p_idx_consumed, c_idx_consumed, last_consumed_practice_row).
        """
        shown_practice_ids: set[int] = set()
        slots: list[dict] = []
        p_idx = 0
        c_idx = 0
        last_consumed_practice = None

        for _ in range(num_cycles):
            cycle_slots: list[dict] = []
            consumed_checkins = 0

            # Slot A: checkins (skip if pool empty)
            if c_idx < len(checkin_rows):
                a_rows, consumed_checkins = FeedService._select_slot_a(
                    checkin_rows[c_idx:]
                )
                for row in a_rows:
                    if hasattr(row, "practice_id") and row.practice_id is not None:
                        shown_practice_ids.add(row.practice_id)
                    cycle_slots.append(
                        {
                            "slot_type": SlotType.A,
                            "item_type": "checkin",
                            "item_id": row.item_id,
                            "feed_source": "original",
                        }
                    )

            # Slot C: advance past practices already shown in Slot A (Rule ③)
            while (
                p_idx < len(practice_rows)
                and practice_rows[p_idx].item_id in shown_practice_ids
            ):
                p_idx += 1

            if p_idx < len(practice_rows):
                row = practice_rows[p_idx]
                cycle_slots.append(
                    {
                        "slot_type": SlotType.C,
                        "item_type": "practice",
                        "item_id": row.item_id,
                        "feed_source": "original",
                    }
                )

            if not cycle_slots:
                break

            if max_items is not None and len(slots) + len(cycle_slots) > max_items:
                break

            slots.extend(cycle_slots)
            c_idx += consumed_checkins
            if p_idx < len(practice_rows):
                last_consumed_practice = practice_rows[p_idx]
                p_idx += 1

        return slots, p_idx, c_idx, last_consumed_practice

    # =========================================================================
    # Batch fetch helpers
    # =========================================================================

    @staticmethod
    def _batch_fetch_cheered_practice_ids(
        db: Session, practice_ids: list[int], social_user_ids: set[int]
    ) -> set[int]:
        """Return practice IDs where any connection/follow has reacted to a checkin."""
        if not practice_ids or not social_user_ids:
            return set()
        rows = db.execute(
            text(
                """
                SELECT DISTINCT c.practice_id
                FROM reactions r
                JOIN practice_checkins c ON c.id = r.target_id
                WHERE r.target_type = 'checkin'
                  AND c.practice_id IN :practice_ids
                  AND r.user_id IN :social_user_ids
                """
            ).bindparams(
                bindparam("practice_ids", expanding=True),
                bindparam("social_user_ids", expanding=True),
            ),
            {"practice_ids": practice_ids, "social_user_ids": list(social_user_ids)},
        ).fetchall()
        return {r.practice_id for r in rows}

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
                    (COALESCE(p.is_featured, FALSE)
                        AND (p.featured_start_at IS NULL OR p.featured_start_at <= NOW())
                        AND (p.featured_end_at IS NULL OR p.featured_end_at > NOW())
                    ) AS is_featured,
                    p.practice_action,
                    p.start_date::text AS start_date,
                    p.end_date::text AS end_date,
                    p.frequency_min_days,
                    p.frequency_max_days,
                    p.session_duration_minutes,
                    p.created_at,
                    u.external_id AS user_external_id,
                    u.nickname AS user_name,
                    ct.photo_url AS user_photo_url,
                    u.custom_id AS user_custom_id
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
                "is_featured": bool(r.is_featured),
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
                    "custom_id": r.user_custom_id,
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
                    ct.photo_url AS user_photo_url,
                    u.custom_id AS user_custom_id
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
                    "custom_id": r.user_custom_id,
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
                           ct.photo_url AS user_photo_url,
                           u.custom_id AS user_custom_id
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
                            "custom_id": r.user_custom_id,
                        },
                    }
                )
        return result
