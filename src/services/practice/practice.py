from sqlalchemy import or_, select, func, literal

from src.models.Practice import Practice, PracticeStatus
from src.models.EntityTag import EntityTag
from src.models.Tag import Tag
from src.models.EntityResource import EntityResource
from src.models.Resource import Resource
from src.models.PracticeCheckIn import PracticeCheckIn
from src.models.User import User
from src.models.UserProfile import UserProfile
from src.services.practice.recommendation import recommand_practices
from src.logger import AppLogger


logger = AppLogger(__name__).get_logger()


class PracticeService:
    # =========================================================
    # Public API
    # =========================================================

    @staticmethod
    def get_practices(
        db,
        user_external_id,
        keyword=None,
        tags=None,
        duration_min=None,
        duration_max=None,
        status=None,
        sort_by="newest_updated",
        limit=20,
        offset=0,
    ):
        """
        Main Entry of Practice Query Service
        """
        if user_external_id:
            user = db.query(User).filter(User.external_id == user_external_id).first()
            if not user:
                return []
        else:
            logger.info("No current user, returning default list for practices")
            user = None

        query = db.query(Practice)
        query = PracticeService._remove_unwanted_status(query)
        query = PracticeService._build_base_query(query, keyword)

        query = PracticeService._apply_filters(
            query, tags, duration_min, duration_max, status
        )

        # ==============================
        # Ranking Routing
        # ==============================

        if sort_by == "recommended" and user:
            practices = recommand_practices(db=db, user=user, query=query)

        else:
            practices = PracticeService._apply_sort_and_pagination(
                query, sort_by, limit, offset
            )

        return practices

    @staticmethod
    def get_search_suggestions(db, user_id: int):
        """
        回傳搜尋建議：
        - popular_keywords：全站 practice 標籤使用次數 Top 10
        - interest_tags：根據使用者 skills / interests / tag_list 匹配的相關標籤
        """
        # ── 熱門關鍵字 ──────────────────────────────────────────
        popular_rows = (
            db.query(Tag.name, func.count(EntityTag.id).label("usage_count"))
            .join(EntityTag, EntityTag.tag_id == Tag.id)
            .filter(EntityTag.entity_type == literal("practice"))
            .group_by(Tag.name)
            .order_by(func.count(EntityTag.id).desc())
            .limit(10)
            .all()
        )
        popular_keywords = [row.name for row in popular_rows]

        # ── 興趣相關標籤 ─────────────────────────────────────────
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        candidate_terms = []
        if profile:
            candidate_terms.extend(profile.skills or [])
            candidate_terms.extend(profile.interests or [])

        user = db.query(User).filter(User.id == user_id).first()
        if user and user.tag_list:
            candidate_terms.extend(user.tag_list)

        # 去重，保留順序
        seen, unique_terms = set(), []
        for t in candidate_terms:
            if t and t not in seen:
                seen.add(t)
                unique_terms.append(t)

        interest_tags = []
        if unique_terms:
            ilike_conditions = [Tag.name.ilike(f"%{term}%") for term in unique_terms]
            interest_rows = (
                db.query(Tag.name)
                .join(EntityTag, EntityTag.tag_id == Tag.id)
                .filter(
                    EntityTag.entity_type == "practice",
                    or_(*ilike_conditions),
                )
                .distinct()
                .limit(10)
                .all()
            )
            interest_tags = [row.name for row in interest_rows]

        return {"popular_keywords": popular_keywords, "interest_tags": interest_tags}

    @staticmethod
    def get_practice_completions(db, prefix: str, limit: int = 10) -> list[dict]:
        """
        前綴補全：搜尋範圍與 keyword 搜尋一致，涵蓋所有欄位。

        回傳格式：[{"text": "...", "type": "tag|title|practice_action|resource|checkin_note", "usage_count": N}, ...]

        搜尋順序（優先度由高到低）：
          1. Tag.name          → 有 usage_count，最精準
          2. Practice.title    → 使用者最常以標題搜尋
          3. Resource.name     → 附件 / 資源名稱
          4. Practice.practice_action → 行動描述（長文，截取前 50 字）
          5. PracticeCheckIn.note    → checkin 筆記（長文，截取前 50 字）
        """
        pattern = f"{prefix}%"
        results: list[dict] = []
        seen: set[str] = set()

        def _add(text: str, source_type: str, usage_count: int | None = None):
            """去重後加入結果，長文截斷到 50 字。"""
            if not text:
                return
            text = text.strip()
            if len(text) > 50:
                text = text[:50]
            if text in seen:
                return
            seen.add(text)
            item = {"text": text, "type": source_type}
            if usage_count is not None:
                item["usage_count"] = usage_count
            results.append(item)

        # ── 1. Tag.name（按使用次數排序）────────────────────────────
        tag_rows = (
            db.query(Tag.name, func.count(EntityTag.id).label("usage_count"))
            .join(EntityTag, EntityTag.tag_id == Tag.id)
            .filter(
                EntityTag.entity_type == literal("practice"),
                Tag.name.ilike(pattern),
            )
            .group_by(Tag.name)
            .order_by(func.count(EntityTag.id).desc())
            .limit(limit)
            .all()
        )
        for row in tag_rows:
            _add(row.name, "tag", row.usage_count)

        # ── 2. Practice.title ────────────────────────────────────────
        title_rows = (
            db.query(Practice.title)
            .filter(
                Practice.title.ilike(pattern),
                Practice.status.notin_(
                    [PracticeStatus.DRAFT.value, PracticeStatus.ARCHIVED.value]
                ),
                Practice.deleted_at.is_(None),
            )
            .distinct()
            .limit(limit)
            .all()
        )
        for row in title_rows:
            _add(row.title, "title")

        # ── 3. Resource.name ─────────────────────────────────────────
        resource_rows = (
            db.query(Resource.name)
            .join(EntityResource, EntityResource.resource_id == Resource.id)
            .filter(
                EntityResource.entity_type == literal("practice"),
                Resource.name.ilike(pattern),
            )
            .distinct()
            .limit(limit)
            .all()
        )
        for row in resource_rows:
            _add(row.name, "resource")

        # ── 4. Practice.practice_action（長文截斷）───────────────────
        action_rows = (
            db.query(Practice.practice_action)
            .filter(
                Practice.practice_action.ilike(pattern),
                Practice.status.notin_(
                    [PracticeStatus.DRAFT.value, PracticeStatus.ARCHIVED.value]
                ),
                Practice.deleted_at.is_(None),
            )
            .distinct()
            .limit(limit)
            .all()
        )
        for row in action_rows:
            _add(row.practice_action, "practice_action")

        # ── 5. PracticeCheckIn.note（長文截斷）──────────────────────
        note_rows = (
            db.query(PracticeCheckIn.note)
            .filter(PracticeCheckIn.note.ilike(pattern))
            .distinct()
            .limit(limit)
            .all()
        )
        for row in note_rows:
            _add(row.note, "checkin_note")

        return results[:limit]

    @staticmethod
    def get_next_word_suggestions(db, query: str, limit: int = 5) -> list[dict]:
        """
        跨欄位 Co-occurrence：
        先在所有 keyword 搜尋欄位中找到符合 query 的 practice IDs，
        再從這些 practices 收集相關詞。

        搜尋範圍（與 keyword 一致）：
          title / practice_action / Tag.name / Resource.name / PracticeCheckIn.note

        回傳相關詞來源（排除 query 本身）：
          - tags      → 共現次數最多的 tag（最精準）
          - title     → 同 practice 的其他標題
          - resource  → 同 practice 的資源名稱

        回傳格式：[{"text": "正念", "type": "tag"}, {"text": "每日10分鐘", "type": "title"}, ...]
        """
        pattern = f"%{query}%"
        exclude = f"{query}"  # 排除 query 本身完全相符的結果

        # ── Step 1: 找所有符合 query 的 practice IDs（跨 5 個欄位）───────
        tag_match = (
            select(EntityTag.entity_id)
            .join(Tag, Tag.id == EntityTag.tag_id)
            .where(
                EntityTag.entity_type == literal("practice"),
                Tag.name.ilike(pattern),
            )
        )
        resource_match = (
            select(EntityResource.entity_id)
            .join(Resource, Resource.id == EntityResource.resource_id)
            .where(
                EntityResource.entity_type == literal("practice"),
                Resource.name.ilike(pattern),
            )
        )
        checkin_match = select(PracticeCheckIn.practice_id).where(
            PracticeCheckIn.note.ilike(pattern)
        )

        matching_ids = (
            db.query(Practice.id)
            .filter(
                Practice.deleted_at.is_(None),
                Practice.status.notin_(
                    [PracticeStatus.DRAFT.value, PracticeStatus.ARCHIVED.value]
                ),
                or_(
                    Practice.title.ilike(pattern),
                    Practice.practice_action.ilike(pattern),
                    Practice.id.in_(tag_match),
                    Practice.id.in_(resource_match),
                    Practice.id.in_(checkin_match),
                ),
            )
            .subquery()
        )

        # ── Step 2: 收集相關詞 ───────────────────────────────────────────
        results: list[dict] = []
        seen: set[str] = set()

        def _add(text: str, source_type: str):
            if not text:
                return
            text = text.strip()
            # 排除 query 本身（完全相符或被包含）
            if text.lower() == exclude.lower():
                return
            if text in seen:
                return
            seen.add(text)
            results.append({"text": text, "type": source_type})

        # 2-a. 共現 Tags（co_count 排序，最能反映使用者習慣）
        co_tags = (
            db.query(Tag.name, func.count(EntityTag.id).label("co_count"))
            .join(EntityTag, EntityTag.tag_id == Tag.id)
            .filter(
                EntityTag.entity_type == literal("practice"),
                EntityTag.entity_id.in_(select(matching_ids)),
                ~Tag.name.ilike(pattern),  # 排除 query 自身 tag
            )
            .group_by(Tag.name)
            .order_by(func.count(EntityTag.id).desc())
            .limit(limit)
            .all()
        )
        for row in co_tags:
            _add(row.name, "tag")

        # 2-b. 同 practices 的其他標題
        co_titles = (
            db.query(Practice.title)
            .filter(
                Practice.id.in_(select(matching_ids)),
                ~Practice.title.ilike(pattern),
            )
            .distinct()
            .limit(limit)
            .all()
        )
        for row in co_titles:
            _add(row.title, "title")

        # 2-c. 同 practices 的資源名稱
        co_resources = (
            db.query(Resource.name)
            .join(EntityResource, EntityResource.resource_id == Resource.id)
            .filter(
                EntityResource.entity_type == literal("practice"),
                EntityResource.entity_id.in_(select(matching_ids)),
                ~Resource.name.ilike(pattern),
            )
            .distinct()
            .limit(limit)
            .all()
        )
        for row in co_resources:
            _add(row.name, "resource")

        return results[:limit]

    @staticmethod
    def get_completions(db, prefix: str, limit: int = 10) -> dict:
        completions = PracticeService.get_practice_completions(db, prefix, limit)
        next_words = []
        if len(prefix) >= 2:
            next_words = PracticeService.get_next_word_suggestions(db, prefix, limit=5)
        return {
            "completions": completions,
            "next_word_suggestions": next_words,
            "query": prefix,
        }

    # =========================================================
    # Internal Query Builders
    # =========================================================

    @staticmethod
    def _build_base_query(query, keyword):
        if keyword:
            pattern = f"%{keyword}%"

            tag_exists = (
                select(EntityTag.id)
                .join(Tag, Tag.id == EntityTag.tag_id)
                .where(
                    EntityTag.entity_type == literal("practice"),
                    EntityTag.entity_id == Practice.id,
                    Tag.name.ilike(pattern),
                )
                .correlate(Practice)
                .exists()
            )
            resource_exists = (
                select(EntityResource.id)
                .join(Resource, Resource.id == EntityResource.resource_id)
                .where(
                    EntityResource.entity_type == "practice",
                    EntityResource.entity_id == Practice.id,
                    Resource.name.ilike(pattern),
                )
                .correlate(Practice)
                .exists()
            )
            checkin_exists = (
                select(PracticeCheckIn.id)
                .where(
                    PracticeCheckIn.practice_id == Practice.id,
                    PracticeCheckIn.note.ilike(pattern),
                    # Don't match checkin notes for brewing practices
                    ~(
                        (Practice.privacy_status == "delayed")
                        & (Practice.status == PracticeStatus.ACTIVE.value)
                    ),
                )
                .correlate(Practice)
                .exists()
            )
            query = query.filter(
                or_(
                    Practice.title.ilike(pattern),
                    Practice.practice_action.ilike(pattern),
                    tag_exists,
                    resource_exists,
                    checkin_exists,
                )
            )
            logger.info(
                str(query.statement.compile(compile_kwargs={"literal_binds": True}))
            )
        return query

    # =========================================================

    @staticmethod
    def _apply_filters(query, tags, duration_min, duration_max, status):
        if tags:
            logger.info(f"Applying tags filter: {tags}")
            # Get tag IDs from tag names
            tag_ids = query.session.query(Tag.id).filter(Tag.name.in_(tags)).all()
            tag_ids = [t.id for t in tag_ids]
            logger.info(f"Resolved tag IDs: {tag_ids}")
            if tag_ids:
                query = query.join(EntityTag, EntityTag.entity_id == Practice.id)
                query = query.filter(
                    EntityTag.entity_type == "practice", EntityTag.tag_id.in_(tag_ids)
                )
            else:
                logger.warning(f"No tag IDs found for tags: {tags}")

        if duration_min is not None:
            query = query.filter(Practice.duration_days >= duration_min)

        if duration_max is not None:
            query = query.filter(Practice.duration_days <= duration_max)

        if status:
            query = query.filter(Practice.status == status)

        return query

    # =========================================================

    @staticmethod
    def _remove_unwanted_status(query):
        return query.filter(
            Practice.status.notin_(
                [
                    PracticeStatus.DRAFT.value,
                    PracticeStatus.ARCHIVED.value,
                    PracticeStatus.NOT_STARTED.value,
                ]
            ),
            Practice.privacy_status != "private",
            Practice.deleted_at.is_(None),
        )

    # =========================================================

    @staticmethod
    def _apply_sort_and_pagination(query, sort_by, limit, offset):
        if sort_by == "newest_updated":
            query = query.order_by(Practice.updated_at.desc().nullslast())

        elif sort_by == "oldest_updated":
            query = query.order_by(Practice.updated_at.asc().nullsfirst())

        elif sort_by == "newest_created":
            query = query.order_by(Practice.created_at.desc().nullslast())

        elif sort_by == "oldest_created":
            query = query.order_by(Practice.created_at.asc().nullsfirst())

        return query.offset(offset).limit(limit).all()
