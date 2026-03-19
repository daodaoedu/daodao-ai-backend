import math
from sqlalchemy import func
from datetime import datetime, timezone
from src.models import Practice, PracticeCheckIn
from src.dependencies import SessionDep
from src.logger import AppLogger

logger = AppLogger(__name__).get_logger()


def recommand_practices(db: SessionDep, user, query) -> list[Practice]:
    """
    Hybrid Practice Recommendation Ranking Model

    Mathematical Definition:

    Score = λ (ContentSignal + BehaviorSignal) + (1-λ) TimeDecaySignal

    ------------------------------------------------------------

    Content Signal:

        C =
        0.3R + 0.4P + 0.3T

        R = Resource Bonus (has_resources)
        P = progress_percentage / 100
        T = template existence

    ------------------------------------------------------------

    Behavior Signal:

        B = CheckinCount / max(ActiveDays, 1)

        ActiveDays = max(CurrentTime - FirstCheckin, 1)

    ------------------------------------------------------------

    Time Decay Signal:

        D = 1 / (1 + log(1 + d))

        d = max(CurrentTime - UpdatedTime, 1)

    ------------------------------------------------------------

    Final Model:

        Score = λ (C + B) + (1-λ) D

    Recommended Parameters:

        λ = 0.65
    """

    checkin_subq = (
        db.query(
            PracticeCheckIn.practice_id.label("practice_id"),
            func.count(PracticeCheckIn.id).label("checkin_count"),
            func.min(PracticeCheckIn.created_at).label("first_checkin"),
        )
        .filter(PracticeCheckIn.user_id == user.id)
        .group_by(PracticeCheckIn.practice_id)
        .subquery()
    )

    now = datetime.now(timezone.utc)

    practices = query.outerjoin(
        checkin_subq, Practice.id == checkin_subq.c.practice_id
    ).all()

    checkin_map = {}

    stats_rows = db.query(
        checkin_subq.c.practice_id,
        checkin_subq.c.checkin_count,
        checkin_subq.c.first_checkin,
    ).all()

    for row in stats_rows:
        checkin_map[row.practice_id] = {
            "checkin_count": row.checkin_count or 0,
            "first_checkin": row.first_checkin,
        }

    scored_posts = []

    for practice in practices:
        score = calculate_practice_score(practice, checkin_map, now)

        scored_posts.append((practice, score))

    scored_posts.sort(key=lambda x: x[1], reverse=True)

    for p, s in scored_posts:
        logger.info(f"Practice ID: {p.id}, Title: {p.title}, Score: {s}")

    return [p[0] for p in scored_posts]


def calculate_practice_score(practice, checkin_stats, now):
    """
    Compute Hybrid Ranking Score

    Score = λ(ContentSignal + BehaviorSignal) + (1-λ) TimeDecaySignal
    """

    lambda_weight = 0.65

    # -----------------------------
    # Content Signal
    # -----------------------------

    resource_bonus = 1 if practice.has_resources else 0

    progress_score = float(practice.progress_percentage or 0) / 100

    template_bonus = 1 if practice.template_id else 0

    content_score = 0.3 * resource_bonus + 0.4 * progress_score + 0.3 * template_bonus

    # -----------------------------
    # Behavior Signal
    # -----------------------------

    stats = checkin_stats.get(practice.id, {})

    checkin_count = stats.get("checkin_count", 0)
    first_checkin = stats.get("first_checkin", None)

    if first_checkin:
        active_days = max((now - first_checkin).days, 1)
        behavior_score = checkin_count / active_days
    else:
        behavior_score = 0

    # -----------------------------
    # Time Decay Signal
    # -----------------------------

    ref_time = practice.updated_at or practice.created_at

    if ref_time:
        days = max((now - ref_time).days, 1)
    else:
        days = 1

    time_decay = 1 / (1 + math.log(1 + days))

    # -----------------------------
    # Final Score
    # -----------------------------

    score = (
        lambda_weight * (content_score + behavior_score)
        + (1 - lambda_weight) * time_decay
    )

    return score
