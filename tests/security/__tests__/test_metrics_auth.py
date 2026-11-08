"""Metrics require a dedicated credential without changing ordinary API access."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.middleware import middleware as mw

METRICS_TOKEN = "synthetic-metrics-105"
API_TOKEN = "synthetic-service-105"
ENVIRONMENTS = ("development", "staging", "production")


@pytest.fixture
def client_factory(monkeypatch):
    clients = []

    def make(environment="staging", metrics_secret=METRICS_TOKEN):
        settings = SimpleNamespace(
            environment=environment,
            api_secret_key=API_TOKEN,
            metrics_secret=metrics_secret,
        )
        monkeypatch.setattr(mw, "get_settings", lambda: settings)
        app = FastAPI()

        @app.get("/api/v1/health")
        async def health():
            return {"ok": True}

        @app.get("/api/v1/protected-probe")
        async def protected():
            return {"ok": True}

        mw.setup_middlewares(app)
        client = TestClient(
            app, base_url="http://localhost", raise_server_exceptions=False
        )
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


@pytest.mark.parametrize("environment", ENVIRONMENTS)
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-metrics-token"},
        {"Authorization": f"Basic {METRICS_TOKEN}"},
        {"Authorization": f"Bearer {API_TOKEN}"},
        {"Authorization": f"Bearer {METRICS_TOKEN.upper()}"},
        {"x-api-key": API_TOKEN, "X-Service-Token": API_TOKEN},
    ],
)
def test_metrics_reject_anonymous_wrong_or_general_service_credentials(
    client_factory, environment, headers
):
    response = client_factory(environment).get("/metrics", headers=headers)

    assert response.status_code == 403
    assert "# HELP" not in response.text
    assert METRICS_TOKEN not in response.text
    assert API_TOKEN not in response.text


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_dedicated_bearer_returns_actual_prometheus_metrics(
    client_factory, environment
):
    client = client_factory(environment)
    assert client.get("/api/v1/health").status_code == 200
    response = client.get(
        "/metrics", headers={"Authorization": f"bEaReR {METRICS_TOKEN}"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# HELP" in response.text
    assert "daodao_" in response.text


@pytest.mark.parametrize("environment", ENVIRONMENTS)
@pytest.mark.parametrize("secret", ["", "   "])
def test_unconfigured_metrics_secret_denies_even_matching_header(
    client_factory, environment, secret
):
    response = client_factory(environment, metrics_secret=secret).get(
        "/metrics", headers={"Authorization": f"Bearer {secret}"}
    )

    assert response.status_code == 403
    assert "# HELP" not in response.text


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_trailing_slash_rejects_before_redirect_and_allows_authorized_scrape(
    client_factory, environment
):
    client = client_factory(environment)
    denied = client.get("/metrics/", follow_redirects=False)
    assert denied.status_code == 403
    assert "location" not in denied.headers

    allowed = client.get(
        "/metrics/",
        headers={"Authorization": f"Bearer {METRICS_TOKEN}"},
        follow_redirects=True,
    )
    assert allowed.status_code == 200
    assert "# HELP" in allowed.text


@pytest.mark.parametrize("header", ["x-api-key", "X-Service-Token"])
def test_general_service_access_stays_independent_of_metrics_token(
    client_factory, header
):
    client = client_factory()
    assert client.get("/api/v1/health").json() == {"ok": True}
    assert client.get("/api/v1/protected-probe").status_code == 403
    assert (
        client.get("/api/v1/protected-probe", headers={header: API_TOKEN}).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/protected-probe",
            headers={"Authorization": f"Bearer {METRICS_TOKEN}"},
        ).status_code
        == 403
    )


def test_development_general_api_bypass_is_unchanged(client_factory):
    client = client_factory("development")
    assert client.get("/api/v1/protected-probe").status_code == 200


def test_non_ascii_authorization_is_denied_without_internal_error(client_factory):
    response = client_factory().get(
        "/metrics", headers=[(b"Authorization", b"Bearer wrong-\xff-token")]
    )

    assert response.status_code == 403
    assert "# HELP" not in response.text
