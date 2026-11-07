"""
Response contract tests for /v1/users/insights.
Validates response shapes against PracticeInsightResponse schema.
"""
import json
from unittest.mock import MagicMock
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.dependencies import get_cache_client, get_current_user, get_db_session
from src.routers.insight import router
from src.schemas.insight import PracticeInsightResponse

app = FastAPI()
app.include_router(router, prefix="/api")


def _fake_user(user_id=42):
    u = MagicMock()
    u.id = user_id
    return u


def _make_db(user=None, practices=None):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    if practices is not None:
        db.execute.return_value.scalars.return_value.all.return_value = practices
    return db


def _make_cache(cached_value=None):
    cache = MagicMock()
    cache.client.get.return_value = cached_value
    return cache


def _make_practice(id=1, title="每日閱讀", insight="你在閱讀中展現了持續力"):
    p = MagicMock()
    p.id = id
    p.title = title
    p.insight = insight
    p.updated_at = datetime(2026, 9, 1, 12, 0, 0)
    p.user_id = 42
    p.external_id = "ext-practice-1"
    p.status = "completed"
    p.deleted_at = None
    return p


@pytest.fixture
def client_authed():
    app.dependency_overrides[get_current_user] = lambda: "user-ext-1"
    app.dependency_overrides[get_db_session] = lambda: _make_db(
        user=_fake_user(), practices=[_make_practice()]
    )
    app.dependency_overrides[get_cache_client] = lambda: _make_cache()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_anon():
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_db_session] = lambda: _make_db()
    app.dependency_overrides[get_cache_client] = lambda: _make_cache()
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestInsights:
    def test_200_response_contains_valid_insight_items(self, client_authed):
        resp = client_authed.get("/api/v1/users/insights")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        for item in body["data"]:
            parsed = PracticeInsightResponse.model_validate(item)
            assert isinstance(parsed.title, str)
            assert isinstance(parsed.insight, str)

    def test_401_without_auth(self, client_anon):
        resp = client_anon.get("/api/v1/users/insights")
        assert resp.status_code == 401
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["details"]["status_code"] == 401

    def test_cache_hit_returns_cached_data(self):
        cached_data = [{"id": 1, "title": "閱讀", "insight": "很好", "updated_at": "2026-09-01T12:00:00"}]
        app.dependency_overrides[get_current_user] = lambda: "user-ext-1"
        app.dependency_overrides[get_db_session] = lambda: _make_db(user=_fake_user())
        app.dependency_overrides[get_cache_client] = lambda: _make_cache(
            cached_value=json.dumps(cached_data)
        )
        client = TestClient(app)
        resp = client.get("/api/v1/users/insights")
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == cached_data

    def test_no_internal_db_fields_in_response(self, client_authed):
        resp = client_authed.get("/api/v1/users/insights")
        body = resp.json()
        text = resp.text
        assert "user_id" not in text
        assert "deleted_at" not in text
        assert "external_id" not in text
