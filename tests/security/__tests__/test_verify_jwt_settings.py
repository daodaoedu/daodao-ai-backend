"""JWT authentication must use the same configured Settings source as the app."""

import json
import secrets
import time

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from src import verify_jwt
from src.config import Settings, get_settings
from src.dependencies import get_admin_user, get_current_user


@pytest.fixture
def configured_env_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JWT_SECURITY", raising=False)
    monkeypatch.delenv("API_SECRET_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "staging")
    env_file = tmp_path / ".env"
    monkeypatch.setitem(Settings.model_config, "env_file", str(env_file))

    def configure(secret):
        env_file.write_text(
            "JWT_SECURITY="
            + json.dumps(secret)
            + "\nAPI_SECRET_KEY=synthetic-api-config\n"
        )
        get_settings.cache_clear()

    secret = secrets.token_urlsafe(32)
    configure(secret)
    try:
        yield secret, configure
    finally:
        get_settings.cache_clear()


def signed_token(secret, expired=False):
    now = int(time.time())
    claims = {"id": 138, "iat": now - 60, "exp": now - 1 if expired else now + 300}
    return jwt.encode(claims, secret, algorithm="HS256"), claims


def test_env_file_secret_authenticates_without_process_environment(configured_env_file):
    secret, _ = configured_env_file
    token, claims = signed_token(secret)
    assert verify_jwt.verify(token) == claims


def test_settings_refresh_rotates_verification_without_module_reload(
    configured_env_file,
):
    secret, configure = configured_env_file
    old_token, old_claims = signed_token(secret)
    assert verify_jwt.verify(old_token) == old_claims
    new_secret = secrets.token_urlsafe(32)
    configure(new_secret)
    new_token, new_claims = signed_token(new_secret)
    assert verify_jwt.verify(new_token) == new_claims
    assert verify_jwt.verify(old_token) is None


@pytest.mark.parametrize("kind", ["wrong-signature", "expired", "malformed"])
def test_invalid_authentication_still_rejects(configured_env_file, kind):
    secret, _ = configured_env_file
    signing_key = secrets.token_urlsafe(32) if kind == "wrong-signature" else secret
    token, _ = signed_token(signing_key, expired=kind == "expired")
    if kind == "malformed":
        token = "invalid.jwt"
    assert verify_jwt.verify(token) is None


def test_current_user_uses_real_env_file_verification(configured_env_file):
    secret, _ = configured_env_file
    token, _ = signed_token(secret)
    request = Request({"type": "http", "headers": []})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert get_current_user(request, credentials) == "138"


@pytest.mark.parametrize(
    "secret", ["", " \t ", "xxxxxxxxxxxxxxxx", " xxxxxxxxxxxxxxxx "]
)
def test_development_unconfigured_keys_cannot_authenticate(
    configured_env_file, monkeypatch, secret
):
    _, configure = configured_env_file
    monkeypatch.setenv("ENVIRONMENT", "development")
    configure(secret)
    token, _ = signed_token(secret or "xxxxxxxxxxxxxxxx")
    assert verify_jwt.verify(token) is None


def test_development_default_cannot_authenticate_known_placeholder(
    configured_env_file, monkeypatch, tmp_path
):
    monkeypatch.setenv("ENVIRONMENT", "development")
    (tmp_path / ".env").unlink()
    get_settings.cache_clear()
    token, _ = signed_token("xxxxxxxxxxxxxxxx")
    assert verify_jwt.verify(token) is None


def test_legitimate_whitespace_in_secret_is_not_rewritten(configured_env_file):
    _, configure = configured_env_file
    secret = " " + secrets.token_urlsafe(32) + " "
    configure(secret)
    token, claims = signed_token(secret)
    assert verify_jwt.verify(token) == claims


@pytest.mark.parametrize("algorithm", ["none", "HS512"])
def test_other_algorithms_are_not_accepted(configured_env_file, algorithm):
    secret, _ = configured_env_file
    _, claims = signed_token(secret)
    token = jwt.encode(
        claims, "" if algorithm == "none" else secret, algorithm=algorithm
    )
    assert verify_jwt.verify(token) is None


@pytest.mark.parametrize("kind", ["wrong-signature", "expired", "malformed"])
def test_real_callers_reject_invalid_jwt(configured_env_file, kind):
    secret, _ = configured_env_file
    token, _ = signed_token(
        secrets.token_urlsafe(32) if kind == "wrong-signature" else secret,
        expired=kind == "expired",
    )
    if kind == "malformed":
        token = "invalid.jwt"
    request = Request({"type": "http", "headers": []})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert get_current_user(request, credentials) is None
    with pytest.raises(HTTPException) as error:
        get_admin_user(request, credentials, db=None)
    assert error.value.status_code == 403
