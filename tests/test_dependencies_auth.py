"""JWT 使用者身份與 X-Service-Token 服務身份必須分開驗證。"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src import dependencies


def _request(headers=None, cookies=None):
    req = MagicMock()
    req.headers = headers or {}
    req.cookies = cookies or {}
    return req


def _creds(token: str):
    creds = MagicMock()
    creds.credentials = token
    return creds


def test_accepts_numeric_id_from_server_jwt():
    with patch.object(dependencies, "verify", return_value={"id": 2}):
        assert dependencies.get_current_user(_request(), _creds("t")) == "2"


def test_prefers_mongo_id_when_present():
    with patch.object(dependencies, "verify", return_value={"id": 2, "_id": "abc"}):
        assert dependencies.get_current_user(_request(), _creds("t")) == "abc"


def test_service_token_matches_api_secret_key():
    settings = MagicMock(api_secret_key="super-secret-token")
    with patch.object(dependencies, "get_settings", return_value=settings):
        req = _request(headers={"X-Service-Token": "super-secret-token"})
        assert (
            dependencies.require_service_caller(req) == dependencies.SERVICE_PRINCIPAL
        )
        with pytest.raises(HTTPException) as exc_info:
            dependencies.require_service_caller(
                _request(headers={"X-Service-Token": "wrong"})
            )
        assert exc_info.value.status_code == 403


def test_service_token_does_not_replace_missing_user_jwt():
    settings = MagicMock(api_secret_key="super-secret-token")
    request = _request(headers={"X-Service-Token": "super-secret-token"})
    with patch.object(dependencies, "get_settings", return_value=settings):
        assert dependencies.get_current_user(request, None) is None


def test_service_token_does_not_replace_invalid_user_jwt():
    settings = MagicMock(api_secret_key="super-secret-token")
    request = _request(headers={"X-Service-Token": "super-secret-token"})
    with (
        patch.object(dependencies, "get_settings", return_value=settings),
        patch.object(dependencies, "verify", side_effect=ValueError("expired")),
    ):
        assert dependencies.get_current_user(request, _creds("bad")) is None


def test_service_token_does_not_replace_identityless_user_jwt():
    settings = MagicMock(api_secret_key="super-secret-token")
    request = _request(headers={"X-Service-Token": "super-secret-token"})
    with (
        patch.object(dependencies, "get_settings", return_value=settings),
        patch.object(dependencies, "verify", return_value={"scope": "user"}),
    ):
        assert dependencies.get_current_user(request, _creds("identityless")) is None


def test_placeholder_secret_never_authenticates():
    settings = MagicMock(api_secret_key="xxxxxxxxxxxxxxxx")
    with patch.object(dependencies, "get_settings", return_value=settings):
        req = _request(headers={"X-Service-Token": "xxxxxxxxxxxxxxxx"})
        assert dependencies.get_current_user(req, None) is None


def test_invalid_token_without_service_header_is_none():
    with patch.object(dependencies, "verify", return_value=None):
        assert dependencies.get_current_user(_request(), _creds("bad")) is None
