"""Keep real Settings tests independent of developer dotenv and environment values."""

import os

import pytest

from src.config import (
    BaseConfigSettings,
    ClickHouseSettings,
    PostgreSQLSettings,
    get_settings,
)


@pytest.fixture
def isolated_settings_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    settings_classes = (
        BaseConfigSettings,
        *BaseConfigSettings.__subclasses__(),
        PostgreSQLSettings,
        ClickHouseSettings,
    )
    config_names = {
        (settings_class.model_config.get("env_prefix", "") + name).upper()
        for settings_class in settings_classes
        for name in settings_class.model_fields
    }
    for name in tuple(os.environ):
        upper_name = name.upper()
        if any(
            upper_name == config_name or upper_name.startswith(config_name + "__")
            for config_name in config_names
        ):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENVIRONMENT", "development")
    for settings_class in settings_classes:
        monkeypatch.setitem(settings_class.model_config, "env_file", str(env_file))
    get_settings.cache_clear()
    try:
        yield env_file
    finally:
        get_settings.cache_clear()
