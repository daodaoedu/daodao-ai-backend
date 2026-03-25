"""
Feed Ranking Model

混合 Feed 推薦評分：同時處理 practice 和 checkin，基於社群關係個人化。

Score = W_social × Social + W_engage × Engagement + W_content × Content + W_decay × TimeDecay

Social Signal（個人化核心）:
    Connected user       → +1.0
    Following practice   → +0.8
    Following user       → +0.6
    Interaction count    → +0.1 × min(count, 10)

Engagement Signal:
    (reaction_count + comment_count × 2) / max(age_days, 1)

Content Signal:
    Practice: 0.3×有資源 + 0.4×進度% + 0.3×有模板
    Checkin:  0.4×有圖片 + 0.3×長文字(>20字) + 0.3×非中立mood

TimeDecay:
    1 / (1 + log(1 + days))

Weights:
    W_social=0.35, W_engage=0.30, W_content=0.15, W_decay=0.20
"""

import math
from datetime import datetime, timezone
from dataclasses import dataclass, field

# --- Weights ---
W_SOCIAL = 0.35
W_ENGAGE = 0.30
W_CONTENT = 0.15
W_DECAY = 0.20

# --- Social signal values ---
SOCIAL_CONNECTED = 1.0
SOCIAL_FOLLOW_PRACTICE = 0.8
SOCIAL_FOLLOW_USER = 0.6
SOCIAL_INTERACTION_WEIGHT = 0.1
SOCIAL_INTERACTION_CAP = 10


@dataclass
class UserSocialGraph:
    """當前用戶的社群關係，用於 feed 個人化評分。"""

    following_user_ids: set[int] = field(default_factory=set)
    following_practice_ids: set[int] = field(default_factory=set)
    connected_user_ids: set[int] = field(default_factory=set)
    interaction_counts: dict[int, int] = field(default_factory=dict)  # user_id → count

    def social_score_for_user(self, owner_user_id: int) -> float:
        """計算當前用戶對某內容 owner 的社群親密度分數。"""
        score = 0.0
        if owner_user_id in self.connected_user_ids:
            score += SOCIAL_CONNECTED
        if owner_user_id in self.following_user_ids:
            score += SOCIAL_FOLLOW_USER
        interaction = self.interaction_counts.get(owner_user_id, 0)
        score += SOCIAL_INTERACTION_WEIGHT * min(interaction, SOCIAL_INTERACTION_CAP)
        return score

    def is_following_practice(self, practice_id: int) -> bool:
        return practice_id in self.following_practice_ids


def score_practice(
    practice_row,
    reaction_count: int,
    comment_count: int,
    now: datetime,
    social_graph: UserSocialGraph | None = None,
    owner_user_id: int | None = None,
    practice_internal_id: int | None = None,
) -> float:
    """Score a practice feed item with social personalization."""

    # --- Social Signal ---
    social = 0.0
    if social_graph and owner_user_id:
        social = social_graph.social_score_for_user(owner_user_id)
        if practice_internal_id and social_graph.is_following_practice(practice_internal_id):
            social += SOCIAL_FOLLOW_PRACTICE

    # --- Content Signal ---
    resource_bonus = 1 if getattr(practice_row, "has_resources", False) else 0
    progress = float(getattr(practice_row, "progress_percentage", 0) or 0) / 100
    template_bonus = 1 if getattr(practice_row, "template_id", None) else 0
    content = 0.3 * resource_bonus + 0.4 * progress + 0.3 * template_bonus

    # --- Engagement Signal ---
    created_at = getattr(practice_row, "created_at", None) or getattr(
        practice_row, "sort_time", None
    )
    age_days = _days_since(created_at, now)
    engagement = (reaction_count + comment_count * 2) / max(age_days, 1)

    # --- Time Decay ---
    updated_at = getattr(practice_row, "updated_at", None) or created_at
    decay = _time_decay(_days_since(updated_at, now))

    return W_SOCIAL * social + W_ENGAGE * engagement + W_CONTENT * content + W_DECAY * decay


def score_checkin(
    checkin_row,
    reaction_count: int,
    comment_count: int,
    now: datetime,
    social_graph: UserSocialGraph | None = None,
    owner_user_id: int | None = None,
    practice_internal_id: int | None = None,
) -> float:
    """Score a checkin feed item with social personalization."""

    # --- Social Signal ---
    social = 0.0
    if social_graph and owner_user_id:
        social = social_graph.social_score_for_user(owner_user_id)
        if practice_internal_id and social_graph.is_following_practice(practice_internal_id):
            social += SOCIAL_FOLLOW_PRACTICE

    # --- Content Richness ---
    has_images = 1 if getattr(checkin_row, "image_urls", None) else 0
    note = getattr(checkin_row, "note", "") or ""
    has_rich_text = 1 if len(note) > 20 else 0
    mood = getattr(checkin_row, "mood", "neutral") or "neutral"
    has_mood = 1 if mood != "neutral" else 0
    content = 0.4 * has_images + 0.3 * has_rich_text + 0.3 * has_mood

    # --- Engagement Signal ---
    created_at = getattr(checkin_row, "created_at", None) or getattr(
        checkin_row, "sort_time", None
    )
    age_days = _days_since(created_at, now)
    engagement = (reaction_count + comment_count * 2) / max(age_days, 1)

    # --- Time Decay ---
    decay = _time_decay(_days_since(created_at, now))

    return W_SOCIAL * social + W_ENGAGE * engagement + W_CONTENT * content + W_DECAY * decay


def _days_since(dt, now: datetime) -> int:
    if dt is None:
        return 1
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max((now - dt).days, 1)


def _time_decay(days: int) -> float:
    return 1 / (1 + math.log(1 + days))
