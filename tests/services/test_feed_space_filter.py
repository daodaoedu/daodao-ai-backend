"""
主頁動態牆「依空間篩選」（daodao#213 FR-D3）的純邏輯測試。
"""

from unittest.mock import MagicMock

import pytest

from src.services.feed.feed_service import FeedService
from src.services.feed.space_filter import (
    SpaceFilter,
    build_space_clause,
    parse_space_filter,
    space_cache_token,
)


class TestParseSpaceFilter:

    @pytest.mark.parametrize("values", [None, []])
    def test_no_values_means_no_filter(self, values):
        assert parse_space_filter(values) is None

    def test_fixed_spaces(self):
        assert parse_space_filter(["personal", "challenge"]) == SpaceFilter(
            personal=True, challenge=True
        )

    def test_cohort_ids_are_deduped_and_sorted(self):
        parsed = parse_space_filter(["cohort:12", "cohort:3", "cohort:12"])
        assert parsed == SpaceFilter(cohort_ids=(3, 12))

    @pytest.mark.parametrize(
        "bad",
        ["", "all", "cohort:", "cohort:abc", "cohort:-1", "cohort:0", "Personal"],
    )
    def test_invalid_value_raises(self, bad):
        with pytest.raises(ValueError):
            parse_space_filter([bad])


class TestBuildSpaceClause:

    def test_none_filter_has_no_clause(self):
        assert build_space_clause(None, "p") == ("", {})

    def test_personal_only(self):
        clause, params = build_space_clause(SpaceFilter(personal=True), "p")
        assert clause == "(p.cohort_id IS NULL)"
        assert params == {}

    def test_challenge_only_joins_program_kind(self):
        clause, params = build_space_clause(SpaceFilter(challenge=True), "p")
        assert "programs" in clause
        assert "kind = :space_challenge_kind" in clause
        assert "p.cohort_id" in clause
        assert params == {"space_challenge_kind": "challenge"}

    def test_cohort_ids_bound_as_param(self):
        clause, params = build_space_clause(SpaceFilter(cohort_ids=(3, 12)), "p")
        assert clause == "(p.cohort_id = ANY(:space_cohort_ids))"
        assert params == {"space_cohort_ids": [3, 12]}

    def test_multiple_spaces_are_unioned_with_or(self):
        clause, params = build_space_clause(
            SpaceFilter(personal=True, challenge=True, cohort_ids=(7,)), "p"
        )
        assert clause.startswith("(") and clause.endswith(")")
        assert clause.count(" OR ") == 2
        assert params == {"space_challenge_kind": "challenge", "space_cohort_ids": [7]}


class TestSpaceCacheToken:

    def test_none_is_stable_placeholder(self):
        assert space_cache_token(None) == "__all__"

    def test_token_is_order_independent(self):
        a = parse_space_filter(["cohort:5", "personal", "cohort:2"])
        b = parse_space_filter(["personal", "cohort:2", "cohort:5"])
        assert space_cache_token(a) == space_cache_token(b)
        assert space_cache_token(a) == "personal,cohort:2,cohort:5"


class TestPoolsApplySpaceFilter:

    @staticmethod
    def _captured_sql(db):
        stmt, params = db.execute.call_args[0]
        return str(stmt), params

    def test_practice_pool_includes_space_clause(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        FeedService._fetch_practice_pool(
            db, None, None, 10, space_filter=SpaceFilter(cohort_ids=(9,))
        )
        sql, params = self._captured_sql(db)
        assert "p.cohort_id = ANY(:space_cohort_ids)" in sql
        assert params["space_cohort_ids"] == [9]
        # 隱私條件不因篩選放寬
        assert "p.privacy_status = 'public'" in sql

    def test_checkin_pool_includes_space_clause(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        FeedService._fetch_checkin_pool_with_counts(
            db, None, None, 10, space_filter=SpaceFilter(personal=True)
        )
        sql, _ = self._captured_sql(db)
        assert "(p.cohort_id IS NULL)" in sql
        assert "p.privacy_status = 'public'" in sql

    def test_pools_without_filter_unchanged(self):
        db = MagicMock()
        db.execute.return_value.fetchall.return_value = []
        FeedService._fetch_practice_pool(db, None, None, 10)
        sql, params = self._captured_sql(db)
        assert "cohort_id" not in sql
        assert "space_cohort_ids" not in params
