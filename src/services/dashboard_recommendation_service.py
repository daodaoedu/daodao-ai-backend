import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.logger import AppLogger
from src.models.Practice import Practice, PracticePrivacyStatus, PracticeStatus
from src.models.RecommendationFeedback import RecommendationFeedback
from src.models.User import User
from src.schemas.dashboard_recommendation import (
    CreatorInfo,
    FeedbackState,
    FeedbackType,
    RecommendationFeedbackResponse,
    TopicCardItem,
)

logger = AppLogger(__name__).get_logger()

RECOMMENDATION_SOURCE = "dashboard_topic_recommendation"

MATCH_REASON_TEXT = {
    "professional_field": "符合你的專業領域",
    "explore_interest": "符合你想探索的方向",
    "ongoing_practice": "與你正在進行的主題相關",
    "popular_content": "社群熱門內容",
}


def _build_recommendation_id(target_type: str, target_id: int) -> str:
    return f"{target_type}:{target_id}"


def _parse_recommendation_id(recommendation_id: str) -> tuple[str, int]:
    parts = recommendation_id.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid recommendationId format")
    try:
        return parts[0], int(parts[1])
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid recommendationId format")


def _get_user_by_mongo_id(session: Session, mongo_id: str) -> User:
    user = session.query(User).filter(User.mongo_id == mongo_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _get_hidden_target_ids(session: Session, user_id: int) -> List[int]:
    rows = (
        session.query(RecommendationFeedback.target_id)
        .filter(
            RecommendationFeedback.user_id == user_id,
            RecommendationFeedback.target_type == "practice",
            RecommendationFeedback.source == RECOMMENDATION_SOURCE,
            RecommendationFeedback.is_hidden.is_(True),
        )
        .all()
    )
    return [r.target_id for r in rows]


def _get_feedback_state(
    session: Session, user_id: int, target_id: int
) -> FeedbackState:
    record = (
        session.query(RecommendationFeedback)
        .filter(
            RecommendationFeedback.user_id == user_id,
            RecommendationFeedback.target_type == "practice",
            RecommendationFeedback.target_id == target_id,
            RecommendationFeedback.source == RECOMMENDATION_SOURCE,
        )
        .first()
    )
    if not record:
        return FeedbackState.NEUTRAL
    if record.feedback_type == FeedbackType.LIKE:
        return FeedbackState.LIKED
    return FeedbackState.DISLIKED


def _extract_practice_keywords(practice: Practice) -> List[str]:
    keywords = []
    if practice.practice_action:
        keywords.extend(practice.practice_action.lower().split())
    if practice.title:
        keywords.extend(practice.title.lower().split())
    return keywords


def _resolve_match_reason(practice: Practice, user: User) -> str:
    keywords = _extract_practice_keywords(practice)
    user_tags = [t.lower() for t in (user.tag_list or [])]
    prof_field = (user.professional_field or "").lower()

    if prof_field and any(prof_field in kw or kw in prof_field for kw in keywords):
        return "professional_field"
    if user_tags and any(tag in " ".join(keywords) for tag in user_tags):
        return "explore_interest"
    return "popular_content"


def _score_practice(practice: Practice, user: User, match_reason: str) -> float:
    now = datetime.now(timezone.utc)

    ref_time = practice.updated_at or practice.created_at
    if ref_time:
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        days = max((now - ref_time).days, 1)
    else:
        days = 30

    freshness = 1 / (1 + math.log(1 + days))

    reason_bonus = {
        "professional_field": 1.0,
        "explore_interest": 0.8,
        "ongoing_practice": 0.6,
        "popular_content": 0.2,
    }
    return freshness + reason_bonus.get(match_reason, 0.2)


def get_topic_cards(
    session: Session,
    mongo_id: str,
    limit: int = 3,
    exclude_ids: Optional[List[int]] = None,
) -> List[TopicCardItem]:
    user = _get_user_by_mongo_id(session, mongo_id)

    hidden_ids = _get_hidden_target_ids(session, user.id)
    all_exclude = set(hidden_ids) | set(exclude_ids or [])

    query = (
        session.query(Practice)
        .filter(
            Practice.privacy_status == PracticePrivacyStatus.PUBLIC.value,
            Practice.status == PracticeStatus.ACTIVE.value,
            Practice.user_id != user.id,
            Practice.deleted_at.is_(None),
        )
    )
    if all_exclude:
        query = query.filter(Practice.id.notin_(all_exclude))

    practices = query.limit(limit * 10).all()

    if not practices:
        logger.info(f"No candidate practices for user {user.id}")
        return []

    scored = []
    for p in practices:
        reason = _resolve_match_reason(p, user)
        score = _score_practice(p, user, reason)
        scored.append((p, reason, score))

    scored.sort(key=lambda x: x[2], reverse=True)
    top = scored[:limit]

    cards = []
    for practice, reason, _ in top:
        creator = practice.user or session.query(User).filter(User.id == practice.user_id).first()
        feedback_state = _get_feedback_state(session, user.id, practice.id)

        tags = []
        if practice.practice_action:
            tags = [t.strip() for t in practice.practice_action.split(",") if t.strip()]

        cards.append(
            TopicCardItem(
                recommendationId=_build_recommendation_id("practice", practice.id),
                targetType="practice",
                targetId=practice.id,
                title=practice.title,
                description=practice.other_context,
                creator=CreatorInfo(
                    id=creator.id if creator else 0,
                    name=creator.nickname if creator else "",
                    photo_url=None,
                ),
                tags=tags,
                matchReasonCode=reason,
                matchReasonText=MATCH_REASON_TEXT[reason],
                feedbackState=feedback_state,
                isAiGenerated=False,
            )
        )

    return cards


def submit_feedback(
    session: Session,
    mongo_id: str,
    recommendation_id: str,
    feedback_type: FeedbackType,
) -> RecommendationFeedbackResponse:
    target_type, target_id = _parse_recommendation_id(recommendation_id)
    if target_type != "practice":
        raise HTTPException(status_code=400, detail=f"Unsupported target type: {target_type}")

    user = _get_user_by_mongo_id(session, mongo_id)

    record = (
        session.query(RecommendationFeedback)
        .filter(
            RecommendationFeedback.user_id == user.id,
            RecommendationFeedback.target_type == target_type,
            RecommendationFeedback.target_id == target_id,
            RecommendationFeedback.source == RECOMMENDATION_SOURCE,
        )
        .first()
    )

    if record:
        if record.feedback_type == feedback_type.value:
            # 同一 feedback 再按一次 → 切換回 neutral（刪除記錄）
            session.delete(record)
            session.commit()
            return RecommendationFeedbackResponse(
                recommendationId=recommendation_id,
                feedbackState=FeedbackState.NEUTRAL,
            )
        record.feedback_type = feedback_type.value
        record.is_hidden = feedback_type == FeedbackType.DISLIKE
        record.updated_at = datetime.now(timezone.utc)
    else:
        record = RecommendationFeedback(
            user_id=user.id,
            target_type=target_type,
            target_id=target_id,
            feedback_type=feedback_type.value,
            is_hidden=feedback_type == FeedbackType.DISLIKE,
            source=RECOMMENDATION_SOURCE,
        )
        session.add(record)

    session.commit()

    new_state = FeedbackState.LIKED if feedback_type == FeedbackType.LIKE else FeedbackState.DISLIKED
    return RecommendationFeedbackResponse(
        recommendationId=recommendation_id,
        feedbackState=new_state,
    )
