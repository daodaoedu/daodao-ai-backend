"""Authentication configuration must be explicit before the API can start."""

import os
from pathlib import Path
import subprocess
import sys

from pydantic import ValidationError
import pytest

from src.config import Settings

ENVIRONMENTS = ("development", "staging", "production")
AUTH_VALUES = {
    "jwt_security": "synthetic-jwt-115-with-explicit-configuration",
    "api_secret_key": "synthetic-api-115-with-explicit-configuration",
}
ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("environment", ENVIRONMENTS)
@pytest.mark.parametrize(
    "missing",
    [("jwt_security",), ("api_secret_key",), ("jwt_security", "api_secret_key")],
)
def test_each_authentication_secret_is_required(
    isolated_settings_env, environment, missing
):
    values = {key: value for key, value in AUTH_VALUES.items() if key not in missing}
    with pytest.raises(ValidationError):
        Settings(environment=environment, **values)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("jwt_security", ""),
        ("jwt_security", " \t\r\n"),
        ("jwt_security", "xxxxxxxxxxxxxxxx"),
        (
            "jwt_security",
            "xxxxxxxxxxxxxxxxxxxxx.bbbbbbbbbbbbbb.ddd-cccccccccc-dddddddd",
        ),
        ("api_secret_key", ""),
        ("api_secret_key", " \t\r\n"),
        ("api_secret_key", "xxxxxxxxxxxxxxxx"),
        ("api_secret_key", "supersecurekey"),
    ],
)
def test_development_rejects_empty_and_known_public_credentials(
    isolated_settings_env, field, invalid
):
    values = {**AUTH_VALUES, field: invalid}
    with pytest.raises(ValidationError, match=field.upper() + " must be configured"):
        Settings(environment="development", **values)


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_explicit_credentials_keep_their_exact_bytes(
    isolated_settings_env, environment
):
    values = {
        "jwt_security": " explicit-jwt-115-with-spaces ",
        "api_secret_key": " explicit-api-115-with-spaces ",
    }
    settings = Settings(environment=environment, **values)
    assert settings.jwt_security == values["jwt_security"]
    assert settings.api_secret_key == values["api_secret_key"]


@pytest.mark.parametrize("environment", ENVIRONMENTS)
@pytest.mark.parametrize("invalid_field", ["jwt_security", "api_secret_key"])
def test_invalid_configuration_diagnostics_do_not_print_other_secret_values(
    isolated_settings_env, environment, invalid_field
):
    values = {"jwt_security": "JWT115", "api_secret_key": "API115"}
    values[invalid_field] = ""
    values["llm_backend"] = {"openai": {"api_key": "LLM115"}}
    with pytest.raises(ValidationError) as caught:
        Settings(environment=environment, **values)
    diagnostic = str(caught.value)
    assert invalid_field.upper() in diagnostic
    assert "API115" not in diagnostic
    assert "JWT115" not in diagnostic
    assert "LLM115" not in diagnostic


STARTUP_PROBE = r"""
import socket
import sys
from pathlib import Path
from pydantic import ValidationError
from src.config import BaseConfigSettings, PostgreSQLSettings, ClickHouseSettings, get_settings
for settings_class in (BaseConfigSettings, *BaseConfigSettings.__subclasses__(), PostgreSQLSettings, ClickHouseSettings):
    settings_class.model_config["env_file"] = str(Path.cwd() / "absent.env")
get_settings.cache_clear()
def forbidden(*args, **kwargs):
    raise RuntimeError("EXTERNAL_STARTUP_ATTEMPT")
socket.socket.connect = forbidden
socket.create_connection = forbidden
import src.db.factory
import src.services.cache.factory
import src.services.llm.factory
src.db.factory.make_database = forbidden
src.services.cache.factory.make_cache_client = forbidden
src.services.llm.factory.make_llm_client = forbidden
try:
    import src.main
except ValidationError as exc:
    print("CONFIG_REJECTED")
    print(str(exc))
    sys.exit(23)
assert src.main.app is not None
print("APP_CREATED")
"""


@pytest.mark.parametrize("environment", ENVIRONMENTS)
def test_api_import_rejects_missing_credentials_before_external_startup(
    tmp_path, environment
):
    result = subprocess.run(
        [sys.executable, "-c", STARTUP_PROBE],
        cwd=tmp_path,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "ENVIRONMENT": environment,
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 23, output
    assert "CONFIG_REJECTED" in output
    assert "APP_CREATED" not in output
    assert "EXTERNAL_STARTUP_ATTEMPT" not in output
