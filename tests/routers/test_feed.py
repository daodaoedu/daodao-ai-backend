"""
Router-level tests for GET /api/v1/feed
"""

import json
from collections import namedtuple
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from src.dependencies import get_cache_client, get_current_user, get_db_session
from src.routers.feed import router
from src.schemas.feed import SlotType
from src.services.feed.feed_service import FeedService

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

    def test_cache_hit_keeps_pagination_as_object(self, client):
        """Cache hit should preserve dict-shaped pagination and not fail validation."""
        cached_payload = {
            "data": [PRACTICE_ITEM],
            "pagination": {
                "cursors": {"start": None, "end": "2025-06-01T08:00:00_1"},
                "hasPrev": False,
                "hasNext": True,
                "count": 1,
            },
        }
        cache = _make_cache()
        cache.client.get.return_value = json.dumps(cached_payload)
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = MagicMock(id=123)
        app.dependency_overrides[get_cache_client] = lambda: cache
        app.dependency_overrides[get_db_session] = lambda: db

        try:
            resp = client.get("/api/v1/feed")
        finally:
            app.dependency_overrides[get_cache_client] = lambda: _make_cache()
            app.dependency_overrides[get_db_session] = lambda: _make_db()

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["cacheHit"] is True
        assert body["pagination"]["hasNext"] is True
        assert body["pagination"]["count"] == 1

    def test_cache_hit_with_legacy_string_pagination_falls_back_to_none(self, client):
        """Legacy cached string pagination should not crash the response wrapper."""
        cached_payload = {
            "data": [PRACTICE_ITEM],
            "pagination": "cursors=CursorInfo(start=None, end='2025-06-01T08:00:00_1') hasPrev=False hasNext=True count=1",
        }
        cache = _make_cache()
        cache.client.get.return_value = json.dumps(cached_payload)
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = MagicMock(id=123)
        app.dependency_overrides[get_cache_client] = lambda: cache
        app.dependency_overrides[get_db_session] = lambda: db

        try:
            resp = client.get("/api/v1/feed")
        finally:
            app.dependency_overrides[get_cache_client] = lambda: _make_cache()
            app.dependency_overrides[get_db_session] = lambda: _make_db()

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["cacheHit"] is True
        assert body["pagination"] is None

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


# ─────────────────────────────────────────────────────────────
# Helper namedtuples for service-level unit tests
# ─────────────────────────────────────────────────────────────

_CheckinRow = namedtuple(
    "_CheckinRow",
    ["item_id", "sort_time", "user_id", "reactions_count", "comments_count"],
)
_PracticeRow = namedtuple("_PracticeRow", ["item_id", "sort_time"])
_CheeredRow = namedtuple("_CheeredRow", ["item_type", "item_id", "sort_time"])


# ─────────────────────────────────────────────────────────────
# Task 5.4: Slot A 打卡則數判斷
# ─────────────────────────────────────────────────────────────


class TestSlotASelection:

    def test_hot_checkin_returns_one(self):
        """熱門打卡（reactions >= 1）→ Slot A 只放 1 則打卡。"""
        rows = [
            _CheckinRow(
                item_id=1,
                sort_time=None,
                user_id=10,
                reactions_count=1,
                comments_count=0,
            ),
            _CheckinRow(
                item_id=2,
                sort_time=None,
                user_id=20,
                reactions_count=0,
                comments_count=0,
            ),
        ]
        selected, consumed = FeedService._select_slot_a(rows)
        assert len(selected) == 1
        assert consumed == 1
        assert selected[0].item_id == 1

    def test_cold_start_two_different_users_returns_two(self):
        """冷啟動（reactions=0, comments=0, 候選池有 2 個不同 userId）→ Slot A 放 2 則打卡。"""
        rows = [
            _CheckinRow(
                item_id=1,
                sort_time=None,
                user_id=10,
                reactions_count=0,
                comments_count=0,
            ),
            _CheckinRow(
                item_id=2,
                sort_time=None,
                user_id=20,
                reactions_count=0,
                comments_count=0,
            ),
        ]
        selected, consumed = FeedService._select_slot_a(rows)
        assert len(selected) == 2
        assert consumed == 2
        assert {r.item_id for r in selected} == {1, 2}

    def test_pool_less_than_two_degrades_to_one(self):
        """候選池 < 2（只有 1 則）→ 降級為 1 則。"""
        rows = [
            _CheckinRow(
                item_id=1,
                sort_time=None,
                user_id=10,
                reactions_count=0,
                comments_count=0,
            ),
        ]
        selected, consumed = FeedService._select_slot_a(rows)
        assert len(selected) == 1
        assert consumed == 1

    def test_empty_pool_slot_a_skipped(self):
        """候選池為空 → Slot A 跳過（回傳 0 則）。"""
        selected, consumed = FeedService._select_slot_a([])
        assert len(selected) == 0
        assert consumed == 0


# ─────────────────────────────────────────────────────────────
# Task 5.4: Slot Pattern 循環順序驗證
# ─────────────────────────────────────────────────────────────


class TestSlotCycleOrder:

    def test_cycle_order_is_a_b_c_c_c(self):
        """API 回傳 items 順序符合 A→B→C→C→C 循環。"""
        checkin_rows = [
            _CheckinRow(
                item_id=101,
                sort_time=None,
                user_id=10,
                reactions_count=0,
                comments_count=0,
            ),
        ]
        practice_rows = [
            _PracticeRow(item_id=i, sort_time=None) for i in [201, 202, 203]
        ]
        # 無 cheered → fallback ActivityCard for Slot B
        cheered_rows: list = []

        slots, p_idx, c_idx = FeedService._assemble_slot_cycles(
            practice_rows, checkin_rows, cheered_rows, num_cycles=1
        )

        slot_types = [s["slot_type"] for s in slots]
        assert slot_types[0] == SlotType.A
        assert slot_types[1] == SlotType.B
        assert slot_types[2:] == [SlotType.C, SlotType.C, SlotType.C]


# ─────────────────────────────────────────────────────────────
# Task 6.3: Slot B ActivityCard 欄位驗證
# ─────────────────────────────────────────────────────────────

ACTIVITY_ITEM = {
    "type": "activity",
    "activity_type": "community_event",
    "event_text": "社群最近很活躍，快來看看大家在練什麼！",
    "label": "學習動態",
    "slot_type": "B",
}


class TestActivityCardSlotB:

    def test_slot_b_activity_card_fields(self, client):
        """Slot B 位置的 item 含 type='activity'、event_text 非空字串、label='學習動態'。"""
        mock_return = {
            "data": [
                {**CHECKIN_ITEM, "slot_type": "A"},
                ACTIVITY_ITEM,
                {**PRACTICE_ITEM, "slot_type": "C"},
                {**PRACTICE_ITEM, "slot_type": "C"},
                {**PRACTICE_ITEM, "slot_type": "C"},
            ],
            "next_cursor": None,
        }
        with patch(SERVICE_PATH, return_value=mock_return):
            resp = client.get("/api/v1/feed")

        assert resp.status_code == 200
        items = resp.json()["data"]
        slot_b = next((item for item in items if item.get("slot_type") == "B"), None)
        assert slot_b is not None, "Slot B item missing from response"
        assert slot_b["type"] == "activity"
        assert isinstance(slot_b.get("event_text"), str) and slot_b["event_text"] != ""
        assert slot_b["label"] == "學習動態"
