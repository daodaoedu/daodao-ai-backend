"""The real cache factory must authenticate before serving cache operations."""

import logging
import subprocess
import time
import uuid

import pytest
import redis

from src.config import RedisSettings, Settings
from src.services.cache import factory

PASSWORD = "synthetic-app-redis-auth-99"


def _docker(*args):
    return subprocess.run(
        ["docker", *args], text=True, capture_output=True, timeout=30, check=False
    )


@pytest.fixture(scope="module")
def protected_redis_url():
    name = f"daodao-ai99-app-{uuid.uuid4().hex}"
    started = _docker(
        "run",
        "--detach",
        "--rm",
        "--name",
        name,
        "--publish",
        "127.0.0.1::6379",
        "redis:alpine",
        "redis-server",
        "--requirepass",
        PASSWORD,
    )
    assert started.returncode == 0, started.stderr
    try:
        deadline = time.monotonic() + 10
        while True:
            ping = _docker(
                "exec",
                "--env",
                f"REDISCLI_AUTH={PASSWORD}",
                name,
                "redis-cli",
                "ping",
            )
            if ping.returncode == 0 and ping.stdout.strip() == "PONG":
                break
            assert time.monotonic() < deadline, ping.stderr
            time.sleep(0.1)
        published = _docker("port", name, "6379")
        assert published.returncode == 0, published.stderr
        address = published.stdout.strip()
        assert address.startswith("127.0.0.1:")
        yield f"redis://{address}/0"
    finally:
        removed = _docker("rm", "--force", name)
        assert removed.returncode == 0, removed.stderr


@pytest.fixture
def capture_factory_logs(monkeypatch, caplog):
    monkeypatch.setattr(factory.logger, "propagate", True)
    caplog.set_level(logging.INFO, logger=factory.logger.name)
    return caplog


def _settings(url, password):
    return Settings(
        _env_file=None,
        environment="development",
        redis=RedisSettings(_env_file=None, url=url, password=password),
    )


def test_authenticated_factory_performs_unicode_json_roundtrip(
    protected_redis_url, capture_factory_logs
):
    cache = factory.make_cache_client(_settings(protected_redis_url, PASSWORD))
    try:
        assert cache.check_redis_health() is True
        key = f"qa99:{uuid.uuid4().hex}"
        content = {"note": "今天讀完一章，繼續練習🐾", "count": 2}
        cache.write_dict(key, content, expire=30)
        assert cache.read_dict(key) == content
        cache.delete(key)
        assert cache.read_dict(key) is None
        assert PASSWORD not in capture_factory_logs.text
    finally:
        cache.client.close()


@pytest.mark.parametrize("password", ["", "synthetic-wrong-password-99"])
def test_factory_refuses_missing_or_wrong_password_before_cache_is_available(
    protected_redis_url, capture_factory_logs, password
):
    with pytest.raises(redis.AuthenticationError):
        factory.make_cache_client(_settings(protected_redis_url, password))
    assert "AuthenticationError" in capture_factory_logs.text
    assert PASSWORD not in capture_factory_logs.text
    if password:
        assert password not in capture_factory_logs.text
