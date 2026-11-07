"""Deployment config must reject secrets that would disable authentication."""

import pytest
from pydantic import ValidationError

from src.config import Settings


@pytest.mark.parametrize("environment", ["staging", "production"])
@pytest.mark.parametrize("field", ["jwt_security", "api_secret_key"])
@pytest.mark.parametrize("invalid", ["", " ", "\t\r\n", "xxxxxxxxxxxxxxxx"])
def test_deployment_rejects_unconfigured_secret(environment, field, invalid):
    values = {"jwt_security": "jwt-valid-test", "api_secret_key": "api-valid-test"}
    values[field] = invalid
    with pytest.raises(ValidationError, match=field.upper() + " must be configured"):
        Settings(_env_file=None, environment=environment, **values)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployment_preserves_configured_secret_values(environment):
    settings = Settings(
        _env_file=None,
        environment=environment,
        jwt_security=" jwt-secret-with-spaces ",
        api_secret_key="api-secret-test",
    )
    assert settings.jwt_security == " jwt-secret-with-spaces "
    assert settings.api_secret_key == "api-secret-test"


@pytest.mark.parametrize("value", ["", " ", "xxxxxxxxxxxxxxxx"])
def test_development_secret_behavior_is_preserved(value):
    settings = Settings(
        _env_file=None,
        environment="development",
        jwt_security=value,
        api_secret_key=value,
    )
    assert settings.jwt_security == value
    assert settings.api_secret_key == value


def test_development_defaults_are_preserved(monkeypatch):
    monkeypatch.delenv("JWT_SECURITY", raising=False)
    monkeypatch.delenv("API_SECRET_KEY", raising=False)
    settings = Settings(_env_file=None, environment="development")
    assert settings.jwt_security == "xxxxxxxxxxxxxxxx"
    assert settings.api_secret_key == "xxxxxxxxxxxxxxxx"
