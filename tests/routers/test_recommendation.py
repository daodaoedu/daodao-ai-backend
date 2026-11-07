"""
Router-level tests for GET /v1/recommendation/rank_feed
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.dependencies import get_cache_client, get_db_session
from src.routers.recommendation import router
from src.schemas.pageInfo import CursorPaginationInfo

# ── minimal app wiring ────────────────────────────────────────
def _make_cache(cached_value=None):
    cache = MagicMock()
    cache.client.get.return_value = cached_value
    return cache


app = FastAPI()
app.include_router(router, prefix="/api")
app.state.limiter = Limiter(key_func=get_remote_address)
app.dependency_overrides[get_db_session] = lambda: None
app.dependency_overrides[get_cache_client] = lambda: _make_cache()


@pytest.fixture
def client():
    yield TestClient(app)


def _make_pagination(count: int = 0, has_next: bool = False):
    return CursorPaginationInfo(
        cursors={"start": None, "end": None},
        hasPrev=False,
        hasNext=has_next,
        count=count,
    )


# ─────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────

class TestRankFeedValidation:

    def test_invalid_type_returns_error(self, client):
        """
        HTTP errors preserve both the status code and the error envelope.
        """
        with patch(
            "src.routers.recommendation.get_recommendation_feed",
            side_effect=HTTPException(
                status_code=400,
                detail="type must be one of ['idea', 'practice', 'project']",
            ),
        ):
            resp = client.get("/api/v1/recommendation/rank_feed?type=invalid")
        assert resp.status_code == 400
        body = resp.json()
        assert body["success"] is False
        assert "idea" in body["error"]["message"]

    @pytest.mark.parametrize("valid_type", ["idea", "practice", "project"])
    def test_valid_types_return_200(self, client, valid_type):
        with patch(
            "src.routers.recommendation.get_recommendation_feed",
            return_value=([], _make_pagination()),
        ):
            resp = client.get(f"/api/v1/recommendation/rank_feed?type={valid_type}")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────
# Response structure
# ─────────────────────────────────────────────────────────────

class TestRankFeedResponse:

    def test_response_contains_data_pagination_cache_hit(self, client):
        with patch(
            "src.routers.recommendation.get_recommendation_feed",
            return_value=([], _make_pagination()),
        ):
            resp = client.get("/api/v1/recommendation/rank_feed")
        body = resp.json()
        assert resp.status_code == 200
        assert "data" in body
        assert "pagination" in body
        assert body["cacheHit"] is False

    def test_pagination_has_next_when_full_page(self, client):
        post = MagicMock()
        post.model_dump.return_value = {"id": "1", "type": "idea"}
        posts = [post] * 20
        pagination = _make_pagination(count=20, has_next=True)
        with patch(
            "src.routers.recommendation.get_recommendation_feed",
            return_value=(posts, pagination),
        ):
            resp = client.get("/api/v1/recommendation/rank_feed?page_size=20")
        body = resp.json()
        assert body["pagination"]["hasNext"] is True
        assert body["pagination"]["count"] == 20

    def test_no_type_calls_service_with_none(self, client):
        with patch(
            "src.routers.recommendation.get_recommendation_feed",
            return_value=([], _make_pagination()),
        ) as mock_svc:
            client.get("/api/v1/recommendation/rank_feed")
        args, _ = mock_svc.call_args
        # type_filter is the 4th positional argument (index 3)
        assert args[3] is None
