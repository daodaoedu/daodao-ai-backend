"""
Tests for feed ranking freshness signal and configurable weights.
"""

from collections import namedtuple
from datetime import datetime, timedelta, timezone

from src.services.feed.feed_ranking import (
    DEFAULT_WEIGHTS,
    RankingWeights,
    score_checkin,
    score_practice,
)

NOW = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)

PracticeRow = namedtuple(
    "PracticeRow",
    [
        "created_at",
        "updated_at",
        "has_resources",
        "progress_percentage",
        "template_id",
        "is_featured",
    ],
    defaults=[False],
)
CheckinRow = namedtuple("CheckinRow", ["created_at", "image_urls", "note", "mood"])


def _practice(age_hours: float, is_featured: bool = False) -> PracticeRow:
    created = NOW - timedelta(hours=age_hours)
    return PracticeRow(
        created_at=created,
        updated_at=created,
        has_resources=False,
        progress_percentage=0,
        template_id=None,
        is_featured=is_featured,
    )


def _checkin(age_hours: float) -> CheckinRow:
    return CheckinRow(
        created_at=NOW - timedelta(hours=age_hours),
        image_urls=None,
        note="",
        mood="neutral",
    )


class TestFreshnessSignal:
    def test_new_practice_outscores_old_practice_with_equal_engagement(self):
        new_score = score_practice(_practice(1), 0, 0, NOW)
        old_score = score_practice(_practice(24 * 10), 0, 0, NOW)
        assert new_score > old_score

    def test_new_checkin_outscores_old_checkin_with_equal_engagement(self):
        new_score = score_checkin(_checkin(1), 0, 0, NOW)
        old_score = score_checkin(_checkin(24 * 10), 0, 0, NOW)
        assert new_score > old_score

    def test_freshness_boost_decays_within_window(self):
        fresh = score_practice(_practice(1), 0, 0, NOW)
        mid = score_practice(_practice(36), 0, 0, NOW)
        assert fresh > mid

    def test_no_freshness_boost_outside_window(self):
        weights = RankingWeights(w_freshness=1.0, freshness_window_hours=72)
        outside = score_practice(_practice(73), 0, 0, NOW, weights=weights)
        baseline = score_practice(
            _practice(73),
            0,
            0,
            NOW,
            weights=RankingWeights(w_freshness=0.0, freshness_window_hours=72),
        )
        assert outside == baseline

    def test_zero_freshness_weight_matches_legacy_score(self):
        legacy = RankingWeights(w_freshness=0.0)
        row = _practice(1)
        legacy_score = score_practice(row, 3, 2, NOW, weights=legacy)
        # legacy score = w_social×0 + w_engage×eng + w_content×0 + w_decay×decay
        assert legacy_score < score_practice(row, 3, 2, NOW, weights=DEFAULT_WEIGHTS)


class TestFeaturedSignal:
    def test_featured_practice_outscores_identical_non_featured(self):
        featured = score_practice(_practice(24 * 5, is_featured=True), 0, 0, NOW)
        normal = score_practice(_practice(24 * 5, is_featured=False), 0, 0, NOW)
        assert featured > normal

    def test_zero_featured_weight_disables_boost(self):
        weights = RankingWeights(w_featured=0.0)
        featured = score_practice(
            _practice(24 * 5, is_featured=True), 0, 0, NOW, weights=weights
        )
        normal = score_practice(
            _practice(24 * 5, is_featured=False), 0, 0, NOW, weights=weights
        )
        assert featured == normal

    def test_featured_boost_equals_weight(self):
        weights = RankingWeights(w_featured=0.5)
        featured = score_practice(
            _practice(24 * 5, is_featured=True), 0, 0, NOW, weights=weights
        )
        normal = score_practice(
            _practice(24 * 5, is_featured=False), 0, 0, NOW, weights=weights
        )
        assert abs((featured - normal) - 0.5) < 1e-9


class TestConfigurableWeights:
    def test_engagement_weight_override_changes_score(self):
        row = _practice(24 * 5)
        low = score_practice(row, 10, 10, NOW, weights=RankingWeights(w_engagement=0.1))
        high = score_practice(
            row, 10, 10, NOW, weights=RankingWeights(w_engagement=1.0)
        )
        assert high > low

    def test_default_weights_used_when_not_provided(self):
        row = _checkin(1)
        assert score_checkin(row, 0, 0, NOW) == score_checkin(
            row, 0, 0, NOW, weights=DEFAULT_WEIGHTS
        )

    def test_freshness_window_override(self):
        # 6 小時前的內容：在 4 小時視窗外、在 72 小時視窗內
        row = _practice(6)
        short_window = score_practice(
            row, 0, 0, NOW, weights=RankingWeights(freshness_window_hours=4)
        )
        long_window = score_practice(
            row, 0, 0, NOW, weights=RankingWeights(freshness_window_hours=72)
        )
        assert long_window > short_window


class TestLoadRankingWeights:
    def test_falls_back_to_defaults_when_no_active_config(self):
        from unittest.mock import MagicMock

        from src.services.feed.feed_service import FeedService

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert FeedService._load_ranking_weights(db) == DEFAULT_WEIGHTS

    def test_loads_weights_from_active_config(self):
        from unittest.mock import MagicMock

        from src.services.feed.feed_service import FeedService

        config = MagicMock()
        config.w_social = "0.10"
        config.w_engagement = "0.20"
        config.w_content = "0.30"
        config.w_decay = "0.40"
        config.w_freshness = "0.50"
        config.freshness_window_hours = 48
        config.w_featured = "0.60"

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = config
        weights = FeedService._load_ranking_weights(db)
        assert weights == RankingWeights(
            w_social=0.10,
            w_engagement=0.20,
            w_content=0.30,
            w_decay=0.40,
            w_freshness=0.50,
            freshness_window_hours=48,
            w_featured=0.60,
        )

    def test_falls_back_to_defaults_on_db_error(self):
        from unittest.mock import MagicMock

        from src.services.feed.feed_service import FeedService

        db = MagicMock()
        db.query.side_effect = RuntimeError("db down")
        assert FeedService._load_ranking_weights(db) == DEFAULT_WEIGHTS
