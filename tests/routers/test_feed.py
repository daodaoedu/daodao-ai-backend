"""
Router-level tests for GET /api/v1/feed
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.dependencies import get_cache_client, get_current_user, get_db_session
from src.routers.feed import router

# ── minimal app wiring ────────────────────────────────────────


def _make_cache():
    cache = MagicMock()
    cache.client.get.return_value = None
    return cache


def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


app = FastAPI()
app.include_router(router, prefix="/api")
app.dependency_overrides[get_db_session] = lambda: _make_db()
app.dependency_overrides[get_current_user] = lambda: "test-user-ext-id"
app.dependency_overrides[get_cache_client] = lambda: _make_cache()


@pytest.fixture
def client():
    yield TestClient(app)


# ── helpers ───────────────────────────────────────────────────

PRACTICE_ITEM = {
    "type": "practice",
    "feed_reason": "new_practice",
    "data": {
        "id": "ext-p-1",
        "title": "Morning Yoga",
        "status": "active",
        "privacy_status": "public",
        "is_brewing": False,
        "practice_action": "yoga",
        "start_date": "2025-01-01",
        "end_date": None,
        "frequency_min_days": 1,
        "frequency_max_days": 1,
        "session_duration_minutes": 30,
        "created_at": "2025-06-01T08:00:00",
        "user": {"id": "u1", "name": "Alice", "photo_url": None},
        "reactions": [],
        "comment_count": 0,
    },
}

BREWING_PRACTICE_ITEM = {
    "type": "practice",
    "feed_reason": "new_release",
    "data": {
        "id": "ext-p-2",
        "title": "Brewing Practice",
        "status": "active",
        "privacy_status": "delayed",
        "is_brewing": True,
        "practice_action": "brew",
        "start_date": "2025-01-01",
        "end_date": None,
        "frequency_min_days": 1,
        "frequency_max_days": 1,
        "session_duration_minutes": 30,
        "created_at": "2025-06-01T08:00:00",
        "user": {"id": "u1", "name": "Alice", "photo_url": None},
        "reactions": [],
        "comment_count": 0,
    },
}

CHECKIN_ITEM = {
    "type": "checkin",
    "feed_reason": "checked_in",
    "data": {
        "id": "101",
        "checkin_date": "2025-06-01",
        "mood": "happy",
        "note": "Felt great!",
        "tags": [],
        "image_urls": [],
        "created_at": "2025-06-01T09:00:00",
        "practice": {"id": "ext-p-1", "title": "Morning Yoga"},
        "user": {"id": "u1", "name": "Alice", "photo_url": None},
        "reactions": [],
        "comment_count": 0,
        "comment_preview": [],
    },
}

SERVICE_PATH = "src.routers.feed.FeedService.get_feed"


# ─────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────


class TestGetFeed:

    def test_returns_200_with_mixed_feed(self, client):
        """Mixed practice + checkin items are returned correctly."""
        mock_return = {
            "data": [PRACTICE_ITEM, CHECKIN_ITEM],
            "next_cursor": "2025-06-01T08:00:00_1",
        }
        with patch(SERVICE_PATH, return_value=mock_return):
            resp = client.get("/api/v1/feed")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert len(body["data"]) == 2
        assert body["data"][0]["type"] == "practice"
        assert body["data"][1]["type"] == "checkin"
        assert body["pagination"]["hasNext"] is True
        assert body["pagination"]["count"] == 2

    def test_type_filter_checkin_only(self, client):
        """type=checkin query param is forwarded to FeedService."""
        mock_return = {"data": [CHECKIN_ITEM], "next_cursor": None}
        with patch(SERVICE_PATH, return_value=mock_return) as mock_svc:
            resp = client.get("/api/v1/feed?type=checkin")

        assert resp.status_code == 200
        _, kwargs = mock_svc.call_args
        assert kwargs["type_filter"].value == "checkin"

    def test_type_filter_practice_only(self, client):
        """type=practice query param is forwarded to FeedService."""
        mock_return = {"data": [PRACTICE_ITEM], "next_cursor": None}
        with patch(SERVICE_PATH, return_value=mock_return) as mock_svc:
            resp = client.get("/api/v1/feed?type=practice")

        assert resp.status_code == 200
        _, kwargs = mock_svc.call_args
        assert kwargs["type_filter"].value == "practice"

    def test_cursor_pagination(self, client):
        """cursor query param is forwarded to FeedService."""
        mock_return = {"data": [], "next_cursor": None}
        with patch(SERVICE_PATH, return_value=mock_return) as mock_svc:
            resp = client.get("/api/v1/feed?cursor=2025-06-01T08:00:00_1")

        assert resp.status_code == 200
        _, kwargs = mock_svc.call_args
        assert kwargs["cursor"] == "2025-06-01T08:00:00_1"
        body = resp.json()
        assert body["pagination"]["hasPrev"] is True

    def test_empty_feed(self, client):
        """Empty feed returns success with empty data list."""
        mock_return = {"data": [], "next_cursor": None}
        with patch(SERVICE_PATH, return_value=mock_return):
            resp = client.get("/api/v1/feed")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == []
        assert body["pagination"]["hasNext"] is False
        assert body["pagination"]["count"] == 0

    def test_feed_reason_new_practice(self, client):
        """practice with is_brewing=False has feed_reason=new_practice."""
        mock_return = {"data": [PRACTICE_ITEM], "next_cursor": None}
        with patch(SERVICE_PATH, return_value=mock_return):
            resp = client.get("/api/v1/feed")

        assert resp.status_code == 200
        item = resp.json()["data"][0]
        assert item["type"] == "practice"
        assert item["data"]["is_brewing"] is False
        assert item["feed_reason"] == "new_practice"

    def test_feed_reason_new_release(self, client):
        """practice with is_brewing=True has feed_reason=new_release."""
        mock_return = {"data": [BREWING_PRACTICE_ITEM], "next_cursor": None}
        with patch(SERVICE_PATH, return_value=mock_return):
            resp = client.get("/api/v1/feed")

        assert resp.status_code == 200
        item = resp.json()["data"][0]
        assert item["type"] == "practice"
        assert item["data"]["is_brewing"] is True
        assert item["feed_reason"] == "new_release"

    def test_feed_reason_checked_in(self, client):
        """checkin item has feed_reason=checked_in."""
        mock_return = {"data": [CHECKIN_ITEM], "next_cursor": None}
        with patch(SERVICE_PATH, return_value=mock_return):
            resp = client.get("/api/v1/feed")

        assert resp.status_code == 200
        item = resp.json()["data"][0]
        assert item["type"] == "checkin"
        assert item["feed_reason"] == "checked_in"
