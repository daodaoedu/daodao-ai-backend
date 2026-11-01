"""#344: selected Lighthouse feed content must follow current membership."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.dependencies import get_cache_client, get_current_user, get_db_session
from src.routers.feed import router
from src.schemas.feed import FeedTypeFilter
from src.services.feed.feed_service import FeedService
from src.services.feed.space_filter import SpaceFilter


@pytest.mark.parametrize(
    "pool",
    [FeedService._fetch_practice_pool, FeedService._fetch_checkin_pool_with_counts],
)
def test_selected_cohort_pool_requires_private_lighthouse_membership(pool):
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    pool(db, None, None, 10, space_filter=SpaceFilter(cohort_ids=(57,)), requester_id=7)
    statement, params = db.execute.call_args[0]
    sql = str(statement)
    assert "p.privacy_status = 'private'" in sql
    assert "visibility_cohort_ids" in sql
    assert "visibility_requester_id" in sql
    assert "ce.status = 'joined'" in sql
    assert "pr.kind = :visibility_program_kind" in sql
    assert "AT TIME ZONE 'UTC'" in sql
    assert "co.end_date >=" in sql
    assert "90" in sql
    assert params["visibility_cohort_ids"] == [57]
    assert params["visibility_requester_id"] == 7
    assert params["visibility_program_kind"] == "lighthouse"
    assert "p.status IN ('active', 'completed')" in sql
    assert "cm.visibility = 'public'" in sql


@pytest.mark.parametrize(
    "space_filter,requester_id",
    [
        (None, 7),
        (SpaceFilter(personal=True), 7),
        (SpaceFilter(challenge=True), 7),
        (SpaceFilter(cohort_ids=(57,)), None),
    ],
)
@pytest.mark.parametrize(
    "pool",
    [FeedService._fetch_practice_pool, FeedService._fetch_checkin_pool_with_counts],
)
def test_no_private_bridge_without_explicit_cohort_and_authenticated_user(
    pool, space_filter, requester_id
):
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    pool(db, None, None, 10, space_filter=space_filter, requester_id=requester_id)
    sql = str(db.execute.call_args[0][0])
    assert "p.privacy_status = 'private'" not in sql
    assert "p.privacy_status = 'public'" in sql
    assert "p.privacy_status = 'delayed' AND p.status = 'completed'" in sql


def test_selected_cohort_never_serves_pre_membership_cache_or_writes_private_payload():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(id=7)
    cache = MagicMock()
    cache.client.get.return_value = json.dumps(
        {
            "data": [{"private": "STALE_PRIVATE_DATA"}],
            "pagination": {"hasNext": False, "count": 1},
        }
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: "user-7"
    app.dependency_overrides[get_cache_client] = lambda: cache
    db.execute.return_value.fetchall.return_value = (
        []
    )  # requester has exited: no joined cohorts
    with patch.object(FeedService, "get_feed", wraps=FeedService.get_feed) as get_feed:
        response = TestClient(app).get("/api/v1/feed?spaces=cohort:57")
    assert response.status_code == 200
    assert "STALE_PRIVATE_DATA" not in response.text
    assert response.json()["data"] == []
    get_feed.assert_called_once()
    cache.client.get.assert_not_called()
    cache.client.set.assert_not_called()


@pytest.mark.parametrize("feed_type", list(FeedTypeFilter))
def test_all_and_single_modes_forward_current_user_to_both_pools(feed_type):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(id=7)
    with (
        patch.object(FeedService, "_fetch_joined_cohort_ids", return_value={57}),
        patch.object(FeedService, "_fetch_practice_pool", return_value=[]) as practices,
        patch.object(
            FeedService, "_fetch_checkin_pool_with_counts", return_value=[]
        ) as checkins,
        patch.object(FeedService, "_fetch_social_graph", return_value=MagicMock()),
        patch.object(FeedService, "_load_ranking_weights", return_value={}),
    ):
        result = FeedService.get_feed(
            db,
            current_user_external_id="user-7",
            type_filter=feed_type,
            space_filter=SpaceFilter(cohort_ids=(57,)),
        )
    assert result["data"] == []
    expected = {
        FeedTypeFilter.ALL: [practices, checkins],
        FeedTypeFilter.PRACTICE: [practices],
        FeedTypeFilter.CHECKIN: [checkins],
    }
    for pool in expected[feed_type]:
        pool.assert_called_once()
        assert pool.call_args.kwargs["requester_id"] == 7
        assert pool.call_args.args[-1] == SpaceFilter(cohort_ids=(57,))


def test_public_feed_keeps_existing_cache_behavior():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(id=7)
    cache = MagicMock()
    cache.client.get.return_value = json.dumps(
        {"data": [{"public": "PUBLIC_CACHED_DATA"}], "pagination": None}
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: "user-7"
    app.dependency_overrides[get_cache_client] = lambda: cache
    with patch.object(
        FeedService,
        "get_feed",
        side_effect=AssertionError("public cache hit must avoid DB query"),
    ):
        response = TestClient(app).get("/api/v1/feed")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "PUBLIC_CACHED_DATA" in response.text
    cache.client.get.assert_called_once()


@pytest.mark.parametrize("feed_type", list(FeedTypeFilter))
def test_public_get_feed_entry_includes_private_joined_cohort_in_real_pool_queries(
    feed_type,
):
    """Exercise the unchanged public entry point; old pools silently omitted private rows."""
    from types import SimpleNamespace

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(id=7)
    captured = []

    def execute(statement, params=None):
        result = MagicMock()
        sql = str(statement)
        if "SELECT cohort_id FROM cohort_enrollments" in sql:
            result.fetchall.return_value = [SimpleNamespace(cohort_id=57)]
        else:
            captured.append((sql, params))
            result.fetchall.return_value = []
        return result

    db.execute.side_effect = execute
    with (
        patch.object(FeedService, "_fetch_social_graph", return_value=MagicMock()),
        patch.object(FeedService, "_load_ranking_weights", return_value={}),
    ):
        result = FeedService.get_feed(
            db,
            current_user_external_id="user-7",
            type_filter=feed_type,
            space_filter=SpaceFilter(cohort_ids=(57,)),
        )
    assert result["data"] == []
    assert len(captured) == (2 if feed_type == FeedTypeFilter.ALL else 1)
    for sql, params in captured:
        assert "p.privacy_status = 'private'" in sql
        assert "ce.status = 'joined'" in sql
        assert params["visibility_requester_id"] == 7
        assert params["visibility_cohort_ids"] == [57]
        assert params["visibility_program_kind"] == "lighthouse"
