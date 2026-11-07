"""Exercise the response wrapper at its public HTTP boundary."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.response_template import api_response_decorator


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 503])
def test_http_error_preserves_status_headers_and_envelope(status):
    app = FastAPI()

    @app.get("/error")
    @api_response_decorator
    async def error():
        raise HTTPException(
            status_code=status,
            detail="Request rejected",
            headers={"WWW-Authenticate": "Bearer", "Retry-After": "30"},
        )

    response = TestClient(app).get("/error")
    assert response.status_code == status
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["retry-after"] == "30"
    body = response.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"] == {
        "code": "HTTP_ERROR",
        "message": "Request rejected",
        "details": {"status_code": status},
    }


def test_success_still_returns_data_and_metadata():
    app = FastAPI()

    @app.get("/success")
    @api_response_decorator
    async def success():
        return {"data": {"value": "完成"}, "pagination": None, "cache_hit": True}

    response = TestClient(app).get("/success")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"value": "完成"}
    assert body["cacheHit"] is True
    assert body["error"] is None
    assert body["requestId"]
