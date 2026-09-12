"""ApiKeyMiddleware 在 staging/production 下：x-api-key 或 X-Service-Token 擇一（皆為 API_SECRET_KEY）。

development 會整個略過 middleware，所以本機 uvicorn 驗不到這條路徑；這裡用 staging 設定實際掛 middleware 打一輪。
"""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.middleware import middleware as mw


def _app(
    environment: str = "staging", secret: str = "super-secret-token"
) -> TestClient:
    settings = MagicMock()
    settings.environment = environment
    settings.api_secret_key = secret
    settings.cors_origins = []
    with patch.object(mw, "get_settings", return_value=settings):
        app = FastAPI()

        @app.get("/api/v1/cohort-summary/probe")
        def probe():
            return {"ok": True}

        @app.get("/api/v1/health")
        def health():
            return {"ok": True}

        mw.setup_middlewares(app)
    return TestClient(
        app, base_url="http://localhost"
    )  # TrustedHost 只放行 localhost 等


def test_staging_rejects_without_any_key():
    client = _app()
    assert client.get("/api/v1/cohort-summary/probe").status_code == 403


def test_staging_accepts_x_api_key():
    client = _app()
    res = client.get(
        "/api/v1/cohort-summary/probe", headers={"x-api-key": "super-secret-token"}
    )
    assert res.status_code == 200


def test_staging_accepts_service_token_from_daodao_server():
    """daodao-server 只送 X-Service-Token（+ Bearer JWT），不送 x-api-key —— 以前這裡會 403"""
    client = _app()
    res = client.get(
        "/api/v1/cohort-summary/probe",
        headers={"X-Service-Token": "super-secret-token", "Authorization": "Bearer x"},
    )
    assert res.status_code == 200


def test_staging_rejects_wrong_service_token():
    client = _app()
    res = client.get(
        "/api/v1/cohort-summary/probe", headers={"X-Service-Token": "nope"}
    )
    assert res.status_code == 403


def test_exempt_paths_and_development_skip():
    assert _app().get("/api/v1/health").status_code == 200
    assert (
        _app(environment="development").get("/api/v1/cohort-summary/probe").status_code
        == 200
    )
