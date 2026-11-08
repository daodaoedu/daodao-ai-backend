"""JWT authentication must use the same configured Settings source as the app."""

import json
from pathlib import Path
import secrets
import time

import jwt
import pytest
from dotenv import dotenv_values
from pydantic import ValidationError
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from src import verify_jwt
from src.config import Settings, get_settings
from src.dependencies import get_admin_user, get_current_user


@pytest.fixture
def configured_env_file(isolated_settings_env, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    env_file = isolated_settings_env

    def configure(secret):
        env_file.write_text(
            "JWT_SECURITY="
            + json.dumps(secret)
            + "\nAPI_SECRET_KEY=synthetic-api-config\nPOSTGRES_DB_NAME=jwt-fixture-db\n"
        )
        get_settings.cache_clear()

    secret = secrets.token_urlsafe(32)
    configure(secret)
    return secret, configure


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
    with pytest.raises(ValidationError, match="JWT_SECURITY must be configured"):
        verify_jwt.verify(token)


def test_development_default_cannot_authenticate_known_placeholder(
    configured_env_file, monkeypatch, tmp_path
):
    monkeypatch.setenv("ENVIRONMENT", "development")
    (tmp_path / ".env").unlink()
    get_settings.cache_clear()
    token, _ = signed_token("xxxxxxxxxxxxxxxx")
    with pytest.raises(ValidationError) as caught:
        verify_jwt.verify(token)
    missing = {
        error["loc"] for error in caught.value.errors() if error["type"] == "missing"
    }
    assert missing == {("jwt_security",), ("api_secret_key",)}


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


def test_nested_settings_use_fixture_dotenv(configured_env_file, monkeypatch):
    monkeypatch.delenv("POSTGRES_DB_NAME", raising=False)
    get_settings.cache_clear()
    assert get_settings().postgresql.db_name == "jwt-fixture-db"


@pytest.mark.parametrize("sample_name", [".env.dev.sample", ".env.prod.sample"])
@pytest.mark.parametrize("environment", ["development", "staging", "production"])
@pytest.mark.parametrize("padding", ["", " "])
def test_public_sample_jwt_cannot_authenticate(
    configured_env_file, monkeypatch, sample_name, environment, padding
):
    sample = Path(__file__).resolve().parents[3] / sample_name
    public_values = dotenv_values(sample, interpolate=False)
    secret = padding + public_values["JWT_SECURITY"] + padding
    _, configure = configured_env_file
    monkeypatch.setenv("ENVIRONMENT", environment)
    configure(secret)
    token, _ = signed_token(secret or "xxxxxxxxxxxxxxxx")
    with pytest.raises(ValidationError, match="JWT_SECURITY must be configured"):
        verify_jwt.verify(token)


@pytest.mark.parametrize("sample_name", [".env.dev.sample", ".env.prod.sample"])
@pytest.mark.parametrize("environment", ["development", "staging", "production"])
@pytest.mark.parametrize("field", ["JWT_SECURITY", "API_SECRET_KEY"])
@pytest.mark.parametrize("padding", ["", " "])
def test_deployment_rejects_public_sample_secrets(
    isolated_settings_env, sample_name, environment, field, padding
):
    sample = Path(__file__).resolve().parents[3] / sample_name
    public_values = dotenv_values(sample, interpolate=False)
    values = {
        "jwt_security": secrets.token_urlsafe(32),
        "api_secret_key": secrets.token_urlsafe(32),
    }
    values[field.lower()] = padding + public_values[field] + padding
    with pytest.raises(ValidationError, match=field + " must be configured"):
        Settings(environment=environment, **values)


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
@pytest.mark.parametrize("field", ["jwt_security", "api_secret_key"])
def test_deployment_rejects_padded_default_placeholder(
    isolated_settings_env, environment, field
):
    values = {
        "jwt_security": secrets.token_urlsafe(32),
        "api_secret_key": secrets.token_urlsafe(32),
    }
    values[field] = "\t xxxxxxxxxxxxxxxx \t"
    with pytest.raises(ValidationError, match=field.upper() + " must be configured"):
        Settings(environment=environment, **values)


def test_deployment_preserves_legitimate_secret_bytes(isolated_settings_env):
    jwt_key = " " + secrets.token_urlsafe(32) + "\t"
    api_key = "\t" + secrets.token_urlsafe(32) + " "
    settings = Settings(
        environment="production", jwt_security=jwt_key, api_secret_key=api_key
    )
    assert settings.jwt_security == jwt_key
    assert settings.api_secret_key == api_key
