import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import String
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
TARGET_TYPE = "practice"

REASON_BONUS = {
    "ongoing_practice": 1.0,
    "tag_match": 0.9,
    "professional_field": 0.8,
    "popular_content": 0.2,
}


def _get_practice_by_external_id(session: Session, practice_id: str) -> Practice:
    practice = (
        session.query(Practice)
        .filter(Practice.external_id == practice_id)
        .first()
    )
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")
    return practice


def _get_user_by_jwt_id(session: Session, jwt_id: str) -> User:
    """查找 user：依序嘗試 mongo_id → external_id（UUID 格式）。"""
    user = session.query(User).filter(User.mongo_id == jwt_id).first()
    if not user:
        user = (
            session.query(User)
            .filter(User.external_id.cast(String) == jwt_id)
            .first()
        )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _get_hidden_target_ids(session: Session, user_id: int) -> List[int]:
    rows = (
        session.query(RecommendationFeedback.target_id)
        .filter(
            RecommendationFeedback.user_id == user_id,
            RecommendationFeedback.target_type == TARGET_TYPE,
            RecommendationFeedback.source == RECOMMENDATION_SOURCE,
            RecommendationFeedback.is_hidden.is_(True),
        )
        .all()
    )
    return [r.target_id for r in rows]


def _get_feedback_state(session: Session, user_id: int, target_id: int) -> FeedbackState:
    record = (
        session.query(RecommendationFeedback)
        .filter(
            RecommendationFeedback.user_id == user_id,
            RecommendationFeedback.target_type == TARGET_TYPE,
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


def _practice_text(practice: Practice) -> str:
    parts = []
    if practice.title:
        parts.append(practice.title.lower())
    if practice.practice_action:
        parts.append(practice.practice_action.lower())
    return " ".join(parts)


def _resolve_match_reason(
    candidate: Practice,
    user: User,
    user_active_practices: List[Practice],
) -> tuple[str, str]:
    """Returns (reason_code, context_string_for_display)."""
    candidate_text = _practice_text(candidate)

    # 1. ongoing_practice：與 user 正在進行的主題相關
    for active_p in user_active_practices:
        title_words = [w for w in active_p.title.lower().split() if len(w) > 1]
        if any(w in candidate_text for w in title_words):
            return "ongoing_practice", active_p.title

    # 2. tag_match：符合 user 的標籤
    for tag in (user.tag_list or []):
        if tag.lower() in candidate_text:
            return "tag_match", tag

    # 3. professional_field：符合 user 的專業領域
    prof = (user.professional_field or "").strip()
    if prof and prof.lower() in candidate_text:
        return "professional_field", prof

    # 4. cold-start
    return "popular_content", ""


def _build_match_reason_text(reason_code: str, context: str) -> str:
    templates = {
        "ongoing_practice": f"因為您正在「{context}」",
        "tag_match": f"基於您的標籤「{context}」",
        "professional_field": f"符合您的專業領域「{context}」",
        "popular_content": "看看其他人都在實踐什麼",
    }
    return templates.get(reason_code, "看看其他人都在實踐什麼")


def _score_practice(practice: Practice, reason_code: str) -> float:
    now = datetime.now(timezone.utc)
    ref_time = practice.updated_at or practice.created_at
    if ref_time:
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
        days = max((now - ref_time).days, 1)
    else:
        days = 30

    freshness = 1 / (1 + math.log(1 + days))
    return freshness + REASON_BONUS.get(reason_code, 0.2)


def get_topic_cards(
    session: Session,
    mongo_id: str,
    limit: int = 3,
    exclude_ids: Optional[List[int]] = None,
) -> List[TopicCardItem]:
    user = _get_user_by_jwt_id(session, mongo_id)

    user_active_practices = (
        session.query(Practice)
        .filter(
            Practice.user_id == user.id,
            Practice.status == PracticeStatus.ACTIVE.value,
            Practice.deleted_at.is_(None),
        )
        .all()
    )

    hidden_ids = _get_hidden_target_ids(session, user.id)
    all_exclude = set(hidden_ids) | set(exclude_ids or [])

    query = session.query(Practice).filter(
        Practice.privacy_status == PracticePrivacyStatus.PUBLIC.value,
        Practice.status == PracticeStatus.ACTIVE.value,
        Practice.user_id != user.id,
        Practice.deleted_at.is_(None),
    )
    if all_exclude:
        query = query.filter(Practice.id.notin_(all_exclude))

    candidates = query.limit(limit * 10).all()

    if not candidates:
        logger.info(f"No candidate practices for user {user.id}")
        return []

    scored = []
    for p in candidates:
        reason_code, reason_context = _resolve_match_reason(p, user, user_active_practices)
        score = _score_practice(p, reason_code)
        scored.append((p, reason_code, reason_context, score))

    scored.sort(key=lambda x: x[3], reverse=True)

    cards = []
    for practice, reason_code, reason_context, _ in scored[:limit]:
        creator = practice.user or session.query(User).filter(User.id == practice.user_id).first()
        feedback_state = _get_feedback_state(session, user.id, practice.id)
        tags = [t.strip() for t in (practice.practice_action or "").split(",") if t.strip()]

        cards.append(
            TopicCardItem(
                practiceId=str(practice.external_id),
                targetId=practice.id,
                title=practice.title,
                description=practice.other_context,
                creator=CreatorInfo(
                    id=creator.id if creator else 0,
                    name=creator.nickname if creator else "",
                    photo_url=None,
                ),
                tags=tags,
                matchReasonCode=reason_code,
                matchReasonText=_build_match_reason_text(reason_code, reason_context),
                feedbackState=feedback_state,
                isAiGenerated=False,
            )
        )

    return cards


def submit_feedback(
    session: Session,
    mongo_id: str,
    practice_id: str,
    feedback_type: FeedbackType,
) -> RecommendationFeedbackResponse:
    user = _get_user_by_jwt_id(session, mongo_id)
    practice = _get_practice_by_external_id(session, practice_id)

    record = (
        session.query(RecommendationFeedback)
        .filter(
            RecommendationFeedback.user_id == user.id,
            RecommendationFeedback.target_type == TARGET_TYPE,
            RecommendationFeedback.target_id == practice.id,
            RecommendationFeedback.source == RECOMMENDATION_SOURCE,
        )
        .first()
    )

    if record:
        if record.feedback_type == feedback_type.value:
            session.delete(record)
            session.commit()
            return RecommendationFeedbackResponse(
                practiceId=practice_id,
                feedbackState=FeedbackState.NEUTRAL,
            )
        record.feedback_type = feedback_type.value
        record.is_hidden = feedback_type == FeedbackType.DISLIKE
        record.updated_at = datetime.now(timezone.utc)
    else:
        record = RecommendationFeedback(
            user_id=user.id,
            target_type=TARGET_TYPE,
            target_id=practice.id,
            feedback_type=feedback_type.value,
            is_hidden=feedback_type == FeedbackType.DISLIKE,
            source=RECOMMENDATION_SOURCE,
        )
        session.add(record)

    session.commit()

    new_state = FeedbackState.LIKED if feedback_type == FeedbackType.LIKE else FeedbackState.DISLIKED
    return RecommendationFeedbackResponse(
        practiceId=practice_id,
        feedbackState=new_state,
    )
