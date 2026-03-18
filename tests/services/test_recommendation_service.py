"""
Unit tests for src.services.recommendation_service.get_recommendation_feed
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.services.recommendation_service import get_recommendation_feed


def _make_post(post_id: int):
    p = MagicMock()
    p.id = post_id
    return p


def _make_feed_info(item_id: int, item_type: str = "idea"):
    f = MagicMock()
    f.id = item_id
    f.type = item_type
    return f


# ─────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────

class TestGetRecommendationFeedValidation:

    def test_invalid_type_raises_400(self):
        session = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            get_recommendation_feed(session, after_id=None, page_size=20, type_filter="invalid")
        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize("valid_type", ["idea", "practice", "project"])
    def test_valid_types_do_not_raise(self, valid_type):
        session = MagicMock()
        with (
            patch("src.services.recommendation_service.get_feed", return_value=[]),
            patch("src.services.recommendation_service.get_posts", return_value=[]),
        ):
            posts, pagination = get_recommendation_feed(session, None, 20, valid_type)
        assert posts == []

    def test_none_type_does_not_raise(self):
        session = MagicMock()
        with (
            patch("src.services.recommendation_service.get_feed", return_value=[]),
            patch("src.services.recommendation_service.get_posts", return_value=[]),
        ):
            posts, _ = get_recommendation_feed(session, None, 20, None)
        assert posts == []


# ─────────────────────────────────────────────────────────────
# Feed building
# ─────────────────────────────────────────────────────────────

class TestGetRecommendationFeedBuild:

    def test_type_filter_passed_as_list_to_get_feed(self):
        session = MagicMock()
        with (
            patch("src.services.recommendation_service.get_feed", return_value=[]) as mock_get_feed,
            patch("src.services.recommendation_service.get_posts", return_value=[]),
        ):
            get_recommendation_feed(session, after_id=5, page_size=10, type_filter="practice")
        mock_get_feed.assert_called_once_with(after_id=5, page_size=10, types=["practice"])

    def test_none_type_passes_none_to_get_feed(self):
        session = MagicMock()
        with (
            patch("src.services.recommendation_service.get_feed", return_value=[]) as mock_get_feed,
            patch("src.services.recommendation_service.get_posts", return_value=[]),
        ):
            get_recommendation_feed(session, after_id=None, page_size=20, type_filter=None)
        mock_get_feed.assert_called_once_with(after_id=None, page_size=20, types=None)


# ─────────────────────────────────────────────────────────────
# Pagination
# ─────────────────────────────────────────────────────────────

class TestGetRecommendationFeedPagination:

    def test_empty_result_no_next_cursor(self):
        session = MagicMock()
        with (
            patch("src.services.recommendation_service.get_feed", return_value=[]),
            patch("src.services.recommendation_service.get_posts", return_value=[]),
        ):
            _, pagination = get_recommendation_feed(session, None, 20, None)
        assert pagination.hasNext is False
        assert pagination.count == 0
        assert pagination.cursors.end is None

    def test_has_next_when_full_page_returned(self):
        feed_items = [_make_feed_info(i) for i in range(1, 21)]  # 20 feed items
        posts = [_make_post(i) for i in range(1, 21)]
        session = MagicMock()
        with (
            patch("src.services.recommendation_service.get_feed", return_value=feed_items),
            patch("src.services.recommendation_service.get_posts", return_value=posts),
        ):
            _, pagination = get_recommendation_feed(session, after_id=0, page_size=20, type_filter=None)
        assert pagination.hasNext is True
        assert pagination.count == 20

    def test_no_next_when_partial_page_returned(self):
        feed_items = [_make_feed_info(i) for i in range(1, 5)]  # 4 items < page_size=20
        posts = [_make_post(i) for i in range(1, 5)]
        session = MagicMock()
        with (
            patch("src.services.recommendation_service.get_feed", return_value=feed_items),
            patch("src.services.recommendation_service.get_posts", return_value=posts),
        ):
            _, pagination = get_recommendation_feed(session, None, 20, None)
        assert pagination.hasNext is False

    def test_has_prev_when_after_id_provided(self):
        session = MagicMock()
        with (
            patch("src.services.recommendation_service.get_feed", return_value=[]),
            patch("src.services.recommendation_service.get_posts", return_value=[]),
        ):
            _, pagination = get_recommendation_feed(session, after_id=10, page_size=20, type_filter=None)
        assert pagination.hasPrev is True

    def test_no_prev_when_after_id_is_none(self):
        session = MagicMock()
        with (
            patch("src.services.recommendation_service.get_feed", return_value=[]),
            patch("src.services.recommendation_service.get_posts", return_value=[]),
        ):
            _, pagination = get_recommendation_feed(session, after_id=None, page_size=20, type_filter=None)
        assert pagination.hasPrev is False
