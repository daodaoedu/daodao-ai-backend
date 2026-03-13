from sqlalchemy import or_, select, func, literal

from src.models.Practice import Practice, PracticeStatus
from src.models.EntityTag import EntityTag, EntityTagType
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
        sort_by="newest",
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
            practices = query.all()

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
                str(
                    query.statement.compile(
                        compile_kwargs={"literal_binds": True}
                    )
                )
            )
        return query

    # =========================================================

    @staticmethod
    def _apply_filters(query, tags, duration_min, duration_max, status):
        if tags:
            query = query.join(EntityTag, EntityTag.entity_id == Practice.id)
            query = query.filter(
                EntityTag.entity_type == "practice", EntityTag.tag_id.in_(tags)
            )

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
                [PracticeStatus.DRAFT.value, PracticeStatus.ARCHIVED.value]
            ),
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
