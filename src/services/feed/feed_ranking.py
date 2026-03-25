"""
Feed Ranking Model

混合 Feed 推薦評分：同時處理 practice 和 checkin，支援個人化。

Practice Score:
    Score = λ (ContentSignal + BehaviorSignal + EngagementSignal) + (1-λ) TimeDecaySignal

    ContentSignal    = 0.3×有資源 + 0.4×進度% + 0.3×有模板
    BehaviorSignal   = user_checkin_count / max(active_days, 1)  ← 個人化
    EngagementSignal = (reaction_count + comment_count×2) / max(age_days, 1)
    TimeDecay        = 1 / (1 + log(1 + days_since_update))

Checkin Score:
    Score = λ (ContentRichness + EngagementSignal) + (1-λ) TimeDecaySignal

    ContentRichness  = 0.4×有圖片 + 0.3×有文字(>20字) + 0.3×有mood(非neutral)
    EngagementSignal = (reaction_count + comment_count×2) / max(age_days, 1)
    TimeDecay        = 1 / (1 + log(1 + days_since_creation))

Parameters:
    λ = 0.6
"""

import math
from datetime import datetime, timezone

LAMBDA_WEIGHT = 0.6


def score_practice(
    practice_row,
    reaction_count: int,
    comment_count: int,
    now: datetime,
    user_checkin_count: int = 0,
    user_first_checkin_at=None,
) -> float:
    """
    Score a practice feed item.

    user_checkin_count / user_first_checkin_at: 當前用戶對此 practice 的打卡資料（個人化）。
    沿用 recommendation.py 的 BehaviorSignal 設計。
    """

    # --- Content Signal ---
    resource_bonus = 1 if getattr(practice_row, "has_resources", False) else 0
    progress = float(getattr(practice_row, "progress_percentage", 0) or 0) / 100
    template_bonus = 1 if getattr(practice_row, "template_id", None) else 0
    content_score = 0.3 * resource_bonus + 0.4 * progress + 0.3 * template_bonus

    # --- Behavior Signal（個人化）---
    if user_checkin_count > 0 and user_first_checkin_at:
        active_days = _days_since(user_first_checkin_at, now)
        behavior_score = user_checkin_count / max(active_days, 1)
    else:
        behavior_score = 0

    # --- Engagement Signal（社群互動）---
    created_at = getattr(practice_row, "created_at", None) or getattr(
        practice_row, "sort_time", None
    )
    age_days = _days_since(created_at, now)
    engagement = (reaction_count + comment_count * 2) / max(age_days, 1)

    # --- Time Decay ---
    updated_at = getattr(practice_row, "updated_at", None) or created_at
    time_decay = _time_decay(_days_since(updated_at, now))

    return (
        LAMBDA_WEIGHT * (content_score + behavior_score + engagement)
        + (1 - LAMBDA_WEIGHT) * time_decay
    )


def score_checkin(
    checkin_row,
    reaction_count: int,
    comment_count: int,
    now: datetime,
) -> float:
    """Score a checkin feed item."""

    # --- Content Richness ---
    has_images = 1 if getattr(checkin_row, "image_urls", None) else 0
    note = getattr(checkin_row, "note", "") or ""
    has_rich_text = 1 if len(note) > 20 else 0
    mood = getattr(checkin_row, "mood", "neutral") or "neutral"
    has_mood = 1 if mood != "neutral" else 0
    content_score = 0.4 * has_images + 0.3 * has_rich_text + 0.3 * has_mood

    # --- Engagement Signal ---
    created_at = getattr(checkin_row, "created_at", None) or getattr(
        checkin_row, "sort_time", None
    )
    age_days = _days_since(created_at, now)
    engagement = (reaction_count + comment_count * 2) / max(age_days, 1)

    # --- Time Decay ---
    time_decay = _time_decay(_days_since(created_at, now))

    return LAMBDA_WEIGHT * (content_score + engagement) + (1 - LAMBDA_WEIGHT) * time_decay


def _days_since(dt, now: datetime) -> int:
    if dt is None:
        return 1
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max((now - dt).days, 1)


def _time_decay(days: int) -> float:
    return 1 / (1 + math.log(1 + days))
