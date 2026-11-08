"""Redis credentials stay separate from the host-only connection URL."""

import pytest

from src.config import RedisSettings


@pytest.mark.parametrize("password", ["synthetic-redis-99", "含有:@/%?的測試密碼🐾"])
def test_password_loads_from_environment_without_uri_encoding(monkeypatch, password):
    monkeypatch.setenv("REDIS_PASSWORD", password)
    settings = RedisSettings(_env_file=None, url="redis://cache.invalid:6379/0")
    assert settings.password == password
    assert settings.url == "redis://cache.invalid:6379/0"


def test_no_credential_is_invented_when_not_configured(monkeypatch):
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    settings = RedisSettings(_env_file=None)
    assert settings.password == ""
