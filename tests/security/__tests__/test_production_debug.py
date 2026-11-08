"""Production must fail closed before FastAPI can enable debug responses."""

from pydantic import ValidationError
import pytest

from src.config import Settings

AUTH = {
    "jwt_security": "synthetic-jwt-144-for-config-tests-only",
    "api_secret_key": "synthetic-api-144-for-config-tests-only",
}


@pytest.mark.parametrize("value", [True, "true", "1", "on"])
@pytest.mark.parametrize("source", ["constructor", "environment"])
def test_production_rejects_debug_enabled(
    isolated_settings_env, monkeypatch, value, source
):
    if source == "environment":
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("DEBUG", str(value))
        values = AUTH
    else:
        values = {**AUTH, "environment": "production", "debug": value}
    with pytest.raises(ValidationError, match="DEBUG.*production"):
        Settings(**values)


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
def test_debug_defaults_to_disabled(isolated_settings_env, environment):
    assert Settings(environment=environment, **AUTH).debug is False


@pytest.mark.parametrize("environment", ["development", "staging"])
def test_nonproduction_explicit_debug_is_preserved(isolated_settings_env, environment):
    assert Settings(environment=environment, debug=True, **AUTH).debug is True


@pytest.mark.parametrize("value", [False, "false", "0", "off"])
def test_production_accepts_explicit_debug_disabled(isolated_settings_env, value):
    assert Settings(environment="production", debug=value, **AUTH).debug is False


def test_production_env_file_cannot_enable_debug(isolated_settings_env, monkeypatch):
    monkeypatch.delenv("ENVIRONMENT")
    isolated_settings_env.write_text("ENVIRONMENT=production\nDEBUG=true\n")
    with pytest.raises(ValidationError, match="DEBUG.*production"):
        Settings(**AUTH)
