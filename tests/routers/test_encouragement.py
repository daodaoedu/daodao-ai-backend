"""
Response contract tests for /v1/encouragement/generate.
Validates response shapes against GenerateEncouragementResponse schema.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.dependencies import get_current_user, get_database_postgres, get_llm_client
from src.routers.encouragement import router
from src.schemas.encouragement import GenerateEncouragementResponse

app = FastAPI()
app.include_router(router, prefix="/api")
app.state.limiter = Limiter(key_func=get_remote_address)


def _make_llm(output="你做得很好，繼續加油！"):
    llm = AsyncMock()
    llm.backend = "openai"
    llm._backend = SimpleNamespace(config={"model": "test-model"})
    llm.generate.return_value = (output, 0.001, {"total_tokens": 50}, "openai")
    return llm


def _database():
    session = MagicMock()
    session.scalar.return_value = 42
    session.query.return_value.filter.return_value.first.return_value = None

    @contextmanager
    def get_session():
        yield session

    database = MagicMock()
    database.get_session = get_session
    return database


@pytest.fixture
def client_authed():
    app.dependency_overrides[get_database_postgres] = _database
    app.dependency_overrides[get_current_user] = lambda: "42"
    app.dependency_overrides[get_llm_client] = lambda: _make_llm()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_anon():
    app.dependency_overrides[get_database_postgres] = _database
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_llm_client] = lambda: _make_llm()
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGenerateEncouragement:
    def test_200_response_matches_schema(self, client_authed):
        resp = client_authed.post(
            "/api/v1/encouragement/generate",
            json={"practiceTitle": "每日閱讀", "mood": "happy", "note": "讀了一章"},
        )
        assert resp.status_code == 200
        body = resp.json()
        parsed = GenerateEncouragementResponse.model_validate(body)
        assert isinstance(parsed.draft, str)
        assert len(parsed.draft) > 0

    def test_minimal_request_fields(self, client_authed):
        resp = client_authed.post(
            "/api/v1/encouragement/generate",
            json={"practiceTitle": "練琴"},
        )
        assert resp.status_code == 200
        GenerateEncouragementResponse.model_validate(resp.json())

    def test_401_without_auth(self, client_anon):
        resp = client_anon.post(
            "/api/v1/encouragement/generate",
            json={"practiceTitle": "練琴"},
        )
        assert resp.status_code == 401

    def test_422_missing_required_field(self, client_authed):
        resp = client_authed.post(
            "/api/v1/encouragement/generate",
            json={"mood": "happy"},
        )
        assert resp.status_code == 422

    def test_no_internal_fields_in_response(self, client_authed):
        resp = client_authed.post(
            "/api/v1/encouragement/generate",
            json={"practiceTitle": "練琴"},
        )
        body = resp.json()
        assert "cost" not in body
        assert "usage" not in body
        assert "backend_name" not in body
        assert "prompt" not in body
