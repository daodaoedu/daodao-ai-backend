"""
Unit tests for PracticeService pure business methods:
  - get_search_suggestions(db, user_id)
  - get_completions(db, prefix, limit)
"""
from unittest.mock import MagicMock, patch

import pytest

from src.services.practice.practice import PracticeService


# ─────────────────────────────────────────────────────────────
# get_search_suggestions
# ─────────────────────────────────────────────────────────────

class TestGetSearchSuggestions:

    def test_returns_dict_with_expected_keys(self):
        db = MagicMock()
        # mock popular tags query
        db.query.return_value.join.return_value.filter.return_value \
            .group_by.return_value.order_by.return_value \
            .limit.return_value.all.return_value = []
        # mock UserProfile query
        db.query.return_value.filter.return_value.first.return_value = None

        result = PracticeService.get_search_suggestions(db=db, user_id=1)

        assert isinstance(result, dict)
        assert "popular_keywords" in result
        assert "interest_tags" in result

    def test_popular_keywords_is_list(self):
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value \
            .group_by.return_value.order_by.return_value \
            .limit.return_value.all.return_value = []
        db.query.return_value.filter.return_value.first.return_value = None

        result = PracticeService.get_search_suggestions(db=db, user_id=99)

        assert isinstance(result["popular_keywords"], list)
        assert isinstance(result["interest_tags"], list)

    def test_no_db_error_on_valid_call(self):
        """Service should not raise when DB returns empty results."""
        db = MagicMock()
        db.query.return_value.join.return_value.filter.return_value \
            .group_by.return_value.order_by.return_value \
            .limit.return_value.all.return_value = []
        db.query.return_value.filter.return_value.first.return_value = None

        # Should not raise
        PracticeService.get_search_suggestions(db=db, user_id=1)


# ─────────────────────────────────────────────────────────────
# get_completions
# ─────────────────────────────────────────────────────────────

class TestGetCompletions:

    def _mock_completions_db(self, completions_result=None, next_words_result=None):
        db = MagicMock()
        # get_practice_completions 和 get_next_word_suggestions 都依賴 db
        # 用 patch 在各 test 裡 mock 更精確的子方法
        return db

    def test_returns_dict_with_expected_keys(self):
        db = MagicMock()
        with (
            patch.object(PracticeService, "get_practice_completions", return_value=[]),
            patch.object(PracticeService, "get_next_word_suggestions", return_value=[]),
        ):
            result = PracticeService.get_completions(db=db, prefix="py", limit=10)

        assert "completions" in result
        assert "next_word_suggestions" in result
        assert "query" in result

    def test_query_field_matches_prefix(self):
        db = MagicMock()
        with (
            patch.object(PracticeService, "get_practice_completions", return_value=[]),
            patch.object(PracticeService, "get_next_word_suggestions", return_value=[]),
        ):
            result = PracticeService.get_completions(db=db, prefix="fast", limit=5)

        assert result["query"] == "fast"

    def test_short_prefix_skips_next_word_suggestions(self):
        """prefix 長度 < 2 時不呼叫 get_next_word_suggestions。"""
        db = MagicMock()
        with (
            patch.object(PracticeService, "get_practice_completions", return_value=[]) as mock_comp,
            patch.object(PracticeService, "get_next_word_suggestions", return_value=[]) as mock_next,
        ):
            PracticeService.get_completions(db=db, prefix="p", limit=10)

        mock_comp.assert_called_once()
        mock_next.assert_not_called()

    def test_long_prefix_calls_next_word_suggestions(self):
        """prefix 長度 >= 2 時呼叫 get_next_word_suggestions。"""
        db = MagicMock()
        with (
            patch.object(PracticeService, "get_practice_completions", return_value=[]),
            patch.object(PracticeService, "get_next_word_suggestions", return_value=["world"]) as mock_next,
        ):
            result = PracticeService.get_completions(db=db, prefix="py", limit=10)

        mock_next.assert_called_once()
        assert result["next_word_suggestions"] == ["world"]
