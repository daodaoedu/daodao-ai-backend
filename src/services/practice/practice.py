from sqlalchemy import or_

from src.models.Practice import Practice, PracticeStatus
from src.models.EntityTag import EntityTag
from src.models.User import User
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
        search_fields=None,
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
        query = PracticeService._build_base_query(query, keyword, search_fields)

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

    # =========================================================
    # Internal Query Builders
    # =========================================================

    @staticmethod
    def _build_base_query(query, keyword, search_fields):
        if keyword:
            conditions = []

            if search_fields and "title" in search_fields:
                conditions.append(Practice.title.ilike(f"%{keyword}%"))
            if "tag" in search_fields:
                # conditions.append(Practice.tags.cast(str).ilike(f"%{keyword}%"))
                pass  # tags 搜尋尚未實作

            if "resource" in search_fields:
                # conditions.append(Practice.resources.cast(str).ilike(f"%{keyword}%"))
                pass  # resources 搜尋尚未實作

            if conditions:
                query = query.filter(*conditions)

            logger.info(
                str(
                    query.filter(or_(*conditions)).statement.compile(
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
            )
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
