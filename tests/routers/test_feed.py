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
        orig_cache = app.dependency_overrides.get(get_cache_client)
        orig_db = app.dependency_overrides.get(get_db_session)
        app.dependency_overrides[get_cache_client] = lambda: cache
        app.dependency_overrides[get_db_session] = lambda: db

        try:
            resp = client.get("/api/v1/feed")
        finally:
            if orig_cache is not None:
                app.dependency_overrides[get_cache_client] = orig_cache
            else:
                app.dependency_overrides.pop(get_cache_client, None)
            if orig_db is not None:
                app.dependency_overrides[get_db_session] = orig_db
            else:
                app.dependency_overrides.pop(get_db_session, None)

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
        orig_cache = app.dependency_overrides.get(get_cache_client)
        orig_db = app.dependency_overrides.get(get_db_session)
        app.dependency_overrides[get_cache_client] = lambda: cache
        app.dependency_overrides[get_db_session] = lambda: db

        try:
            resp = client.get("/api/v1/feed")
        finally:
            if orig_cache is not None:
                app.dependency_overrides[get_cache_client] = orig_cache
            else:
                app.dependency_overrides.pop(get_cache_client, None)
            if orig_db is not None:
                app.dependency_overrides[get_db_session] = orig_db
            else:
                app.dependency_overrides.pop(get_db_session, None)

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


class TestSpaceFilterParam:
    """daodao#213 FR-D3：spaces 參數（personal / challenge / cohort:<id>）"""

    def test_spaces_forwarded_as_parsed_filter(self, client):
        mock_return = {"data": [], "next_cursor": None}
        with patch(SERVICE_PATH, return_value=mock_return) as mock_svc:
            resp = client.get("/api/v1/feed?spaces=personal&spaces=cohort:42")

        assert resp.status_code == 200
        _, kwargs = mock_svc.call_args
        space_filter = kwargs["space_filter"]
        assert space_filter.personal is True
        assert space_filter.challenge is False
        assert space_filter.cohort_ids == (42,)

    def test_no_spaces_forwards_none(self, client):
        mock_return = {"data": [], "next_cursor": None}
        with patch(SERVICE_PATH, return_value=mock_return) as mock_svc:
            resp = client.get("/api/v1/feed")

        assert resp.status_code == 200
        _, kwargs = mock_svc.call_args
        assert kwargs["space_filter"] is None

    def test_invalid_space_returns_422(self, client):
        with patch(SERVICE_PATH) as mock_svc:
            resp = client.get("/api/v1/feed?spaces=cohort:abc")

        assert resp.status_code == 422
        mock_svc.assert_not_called()

    def test_oversized_cohort_id_returns_422(self, client):
        with patch(SERVICE_PATH) as mock_svc:
            resp = client.get(f"/api/v1/feed?spaces=cohort:{'9' * 4301}")

        assert resp.status_code == 422
        mock_svc.assert_not_called()

    def test_too_many_spaces_returns_422(self, client):
        qs = "&".join(f"spaces=cohort:{i}" for i in range(1, 22))
        with patch(SERVICE_PATH) as mock_svc:
            resp = client.get(f"/api/v1/feed?{qs}")

        assert resp.status_code == 422
        mock_svc.assert_not_called()

    def test_cache_key_includes_spaces(self, client):
        cache = _make_cache()
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = MagicMock(id=123)
        orig_cache = app.dependency_overrides.get(get_cache_client)
        orig_db = app.dependency_overrides.get(get_db_session)
        app.dependency_overrides[get_cache_client] = lambda: cache
        app.dependency_overrides[get_db_session] = lambda: db
        try:
            with patch(SERVICE_PATH, return_value={"data": [], "next_cursor": None}):
                client.get("/api/v1/feed?spaces=challenge&spaces=personal")
                client.get("/api/v1/feed")
        finally:
            app.dependency_overrides[get_cache_client] = orig_cache
            app.dependency_overrides[get_db_session] = orig_db

        keys = [c[0][0] for c in cache.client.get.call_args_list]
        filtered_key, unfiltered_key = keys
        assert ":spaces:personal,challenge" in filtered_key
        assert ":spaces:__all__" in unfiltered_key


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

    def test_cold_first_hot_second_returns_one(self):
        """第一則冷啟動，但第二則有 reactions → 兩則不都是冷啟動，只取 1 則。"""
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
                reactions_count=2,
                comments_count=0,
            ),
        ]
        selected, consumed = FeedService._select_slot_a(rows)
        assert len(selected) == 1
        assert consumed == 1
        assert selected[0].item_id == 1

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
    @pytest.mark.parametrize("num_cycles", [1, 2])
    def test_cycle_order_is_a_c_without_activity_cards(self, num_cycles):
        checkins = [
            _CheckinRow(i, None, i, 1, 0) for i in range(101, 104)
        ]
        practices = [_PracticeRow(i, None) for i in range(201, 204)]
        slots, p_idx, c_idx, last = FeedService._assemble_slot_cycles(
            practices, checkins, num_cycles=num_cycles
        )
        assert [slot["slot_type"] for slot in slots] == [
            SlotType.A, SlotType.C
        ] * num_cycles
        assert all(slot["item_type"] != "activity" for slot in slots)
        assert p_idx == c_idx == num_cycles
        assert last == practices[num_cycles - 1]

    @pytest.mark.parametrize("budget, consumed", [(1, 0), (2, 1), (3, 1), (4, 2)])
    def test_budget_keeps_complete_cycles_and_cursors(self, budget, consumed):
        checkins = [_CheckinRow(i, None, i, 1, 0) for i in range(101, 104)]
        practices = [_PracticeRow(i, None) for i in range(201, 204)]
        slots, p_idx, c_idx, last = FeedService._assemble_slot_cycles(
            practices, checkins, num_cycles=2, max_items=budget
        )
        assert [slot["slot_type"] for slot in slots] == [
            SlotType.A, SlotType.C
        ] * consumed
        assert p_idx == c_idx == consumed
        assert last == (practices[consumed - 1] if consumed else None)

    @pytest.mark.parametrize("pool", ["practice", "checkin", "empty"])
    def test_missing_pool_does_not_invent_activity_cards(self, pool):
        practices = [_PracticeRow(201, None)] if pool == "practice" else []
        checkins = [_CheckinRow(101, None, 1, 1, 0)] if pool == "checkin" else []
        slots, p_idx, c_idx, _ = FeedService._assemble_slot_cycles(
            practices, checkins, num_cycles=1
        )
        expected = {"practice": [SlotType.C], "checkin": [SlotType.A], "empty": []}
        assert [slot["slot_type"] for slot in slots] == expected[pool]
        assert p_idx == len(practices)
        assert c_idx == len(checkins)


# Legacy cached activity cards remain readable by the response schema.
ACTIVITY_ITEM = {
    "type": "activity",
    "activity_type": "community_event",
    "event_type": "reaction",
    "event_id": "123",
    "event_text": "社群最近很活躍，快來看看大家在練什麼！",
    "label": "學習動態",
    "slot_type": "B",
    "practice_id": "ext-p-1",
    "checkin_id": "101",
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
        assert slot_b["practice_id"] == "ext-p-1"
        assert slot_b["checkin_id"] == "101"
