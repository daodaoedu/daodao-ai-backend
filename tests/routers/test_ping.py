"""
Response contract tests for /v1/ping and /v1/health.
Validates response shapes against declared Pydantic schemas.
"""
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.config import Settings, get_settings
from src.dependencies import get_db_session
from src.routers.ping import router
from src.schemas.health import HealthResponse

app = FastAPI()
app.include_router(router, prefix="/api")


def _make_db():
    return MagicMock()


def _fake_settings():
    s = MagicMock(spec=Settings)
    s.app_version = "0.1.0-test"
    s.environment = "test"
    s.service_name = "rag-api"
    return s


@pytest.fixture
def client():
    app.dependency_overrides[get_db_session] = lambda: _make_db()
    app.dependency_overrides[get_settings] = lambda: _fake_settings()
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestPing:
    def test_returns_ok_status(self, client):
        resp = client.get("/api/v1/ping")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["message"] == "pong"

    def test_no_internal_fields_in_ping(self, client):
        resp = client.get("/api/v1/ping")
        body = resp.json()
        assert "version" not in body
        assert "database" not in body
        assert "config" not in body


class TestHealth:
    def test_healthy_response_matches_schema(self, client):
        from src.services.health_service import check_database
        from src.schemas.health import ServiceStatus

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.routers.ping.check_database",
                lambda db: ServiceStatus(status="healthy", message="Connected"),
            )
            resp = client.get("/api/v1/health")

        assert resp.status_code == 200
        body = resp.json()
        parsed = HealthResponse.model_validate(body)
        assert parsed.status == "ok"
        assert parsed.version == "0.1.0-test"
        assert parsed.environment == "test"
        assert parsed.service_name == "rag-api"
        assert parsed.services["database"].status == "healthy"

    def test_degraded_on_db_failure(self, client):
        from src.schemas.health import ServiceStatus

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.routers.ping.check_database",
                lambda db: ServiceStatus(status="unhealthy", message="Connection refused"),
            )
            resp = client.get("/api/v1/health")

        assert resp.status_code == 200
        body = resp.json()
        parsed = HealthResponse.model_validate(body)
        assert parsed.status == "degraded"
        assert parsed.services["database"].status == "unhealthy"

    def test_no_internal_config_in_health(self, client):
        from src.schemas.health import ServiceStatus

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.routers.ping.check_database",
                lambda db: ServiceStatus(status="healthy", message="ok"),
            )
            resp = client.get("/api/v1/health")

        body = resp.json()
        text = resp.text
        assert "password" not in text.lower()
        assert "secret" not in text.lower()
        assert "redis_url" not in text
        assert "database_url" not in text
