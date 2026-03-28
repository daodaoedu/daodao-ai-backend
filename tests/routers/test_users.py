"""
Router-level tests for /v1/users/practices/suggestions
                    and /v1/users/practices/completions

Strategy:
  - mock PracticeService pure methods (get_search_suggestions / get_completions)
  - mock db.query(User) for user lookup
  - mock cache.client.get / set for cache read-through
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.dependencies import get_cache_client, get_current_user, get_db_session
from src.routers.users import router

# ── minimal app wiring ────────────────────────────────────────
app = FastAPI()
app.include_router(router, prefix="/api")
app.state.limiter = Limiter(key_func=get_remote_address)


def _fake_user(user_id: int = 42):
    u = MagicMock()
    u.id = user_id
    return u


def _make_db(user=None):
    """Mock Session: db.query(User).filter(...).first() → user"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user
    return db


def _make_cache(cached_value=None):
    """Mock CacheClient: cache.client.get() → cached_value"""
    cache = MagicMock()
    cache.client.get.return_value = cached_value
    return cache


@pytest.fixture
def client_authed(monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: "user-ext-1"
    app.dependency_overrides[get_db_session] = lambda: _make_db(user=_fake_user())
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


# ─────────────────────────────────────────────────────────────
# /practices/suggestions
# ─────────────────────────────────────────────────────────────

class TestSuggestionsEndpoint:

    def test_cache_miss_calls_service_and_returns_200(self, client_authed):
        suggestions = {"popular_keywords": ["python"], "interest_tags": ["ml"]}
        with patch(
            "src.routers.users.PracticeService.get_search_suggestions",
            return_value=suggestions,
        ):
            resp = client_authed.get("/api/v1/users/practices/suggestions")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == suggestions
        assert body["cacheHit"] is False

    def test_cache_hit_returns_cached_data(self):
        cached = {"popular_keywords": ["go"], "interest_tags": ["backend"]}
        app.dependency_overrides[get_current_user] = lambda: "user-ext-1"
        app.dependency_overrides[get_db_session] = lambda: _make_db(user=_fake_user())
        app.dependency_overrides[get_cache_client] = lambda: _make_cache(
            cached_value=json.dumps(cached)
        )
        client = TestClient(app)
        resp = client.get("/api/v1/users/practices/suggestions")
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == cached
        assert body["cacheHit"] is True

    def test_anonymous_user_returns_empty(self, client_anon):
        resp = client_anon.get("/api/v1/users/practices/suggestions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == {"popular_keywords": [], "interest_tags": []}
        assert body["cacheHit"] is False


# ─────────────────────────────────────────────────────────────
# /practices/completions
# ─────────────────────────────────────────────────────────────

class TestCompletionsEndpoint:

    def test_cache_miss_calls_service_and_returns_200(self, client_authed):
        result = {"completions": ["python", "pytorch"], "next_word_suggestions": [], "query": "py"}
        with patch(
            "src.routers.users.PracticeService.get_completions",
            return_value=result,
        ):
            resp = client_authed.get("/api/v1/users/practices/completions?q=py")

        assert resp.status_code == 200
        assert resp.json()["data"] == result
        assert resp.json()["cacheHit"] is False

    def test_cache_hit_returns_cached_data(self):
        cached = {"completions": ["fast"], "next_word_suggestions": [], "query": "fast"}
        app.dependency_overrides[get_current_user] = lambda: "user-ext-1"
        app.dependency_overrides[get_db_session] = lambda: _make_db(user=_fake_user())
        app.dependency_overrides[get_cache_client] = lambda: _make_cache(
            cached_value=json.dumps(cached)
        )
        client = TestClient(app)
        resp = client.get("/api/v1/users/practices/completions?q=fast")
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == cached
        assert body["cacheHit"] is True

    def test_missing_q_returns_422(self, client_authed):
        resp = client_authed.get("/api/v1/users/practices/completions")
        assert resp.status_code == 422

    def test_query_is_normalized_before_cache_lookup(self, client_authed):
        """Router 應對 q 做 strip + lower 再查 cache。"""
        result = {"completions": [], "next_word_suggestions": [], "query": "hello world"}
        with patch("src.routers.users.PracticeService.get_completions", return_value=result):
            resp = client_authed.get("/api/v1/users/practices/completions?q=+Hello+World+")
        assert resp.status_code == 200
