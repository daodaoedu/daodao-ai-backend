"""Redis startup diagnostics must not disclose connection credentials."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import redis

from src.services.cache import factory

PASSWORD = "SYNTHETIC-PASSWORD-99@private"
ENCODED_PASSWORD = "SYNTHETIC-PASSWORD-99%40private"
USERNAME = "PRIVATE-REDIS-USER-99"
PRIVATE_DETAIL = "私人連線資料-99🐾"
REDIS_URL = f"redis://{USERNAME}:{ENCODED_PASSWORD}@cache.example.invalid:6379/0"


@pytest.fixture
def startup(monkeypatch, caplog):
    monkeypatch.setattr(factory.logger, "propagate", True)
    caplog.set_level(logging.INFO, logger=factory.logger.name)
    client = Mock()
    client.ping.return_value = True
    monkeypatch.setattr(factory.redis, "from_url", lambda **_kwargs: client)
    settings = SimpleNamespace(
        redis=SimpleNamespace(url=REDIS_URL, ttl_hours=3, password=PASSWORD)
    )
    return settings, client


def _messages(caplog):
    formatter = logging.Formatter("%(message)s")
    return "\n".join(
        formatter.format(record)
        for record in caplog.records
        if record.name == factory.logger.name
    )


def _assert_private_values_absent(messages):
    for private in (
        REDIS_URL,
        PASSWORD,
        ENCODED_PASSWORD,
        USERNAME,
        PRIVATE_DETAIL,
    ):
        assert private not in messages


@pytest.mark.parametrize("make_cache", [False, True])
def test_successful_connection_logs_without_url_credentials(
    startup, caplog, make_cache
):
    settings, client = startup
    result = (
        factory.make_cache_client(settings)
        if make_cache
        else factory.make_redis_client(settings)
    )

    assert (result.client if make_cache else result) is client
    client.ping.assert_called_once()
    messages = _messages(caplog)
    assert messages and "Redis" in messages
    _assert_private_values_absent(messages)


@pytest.mark.parametrize("make_cache", [False, True])
@pytest.mark.parametrize("error_type", [redis.ConnectionError, RuntimeError])
def test_connection_failure_logs_class_without_exception_details(
    startup, caplog, make_cache, error_type
):
    settings, client = startup
    failure = error_type(f"{REDIS_URL}; {PRIVATE_DETAIL}; {PASSWORD}")
    client.ping.side_effect = failure
    create = factory.make_cache_client if make_cache else factory.make_redis_client

    with pytest.raises(error_type) as caught:
        create(settings)
    assert caught.value is failure
    messages = _messages(caplog)
    _assert_private_values_absent(messages)
    assert error_type.__name__ in messages
    assert any(record.levelno >= logging.ERROR for record in caplog.records)


def test_client_creation_failure_keeps_exception_private(startup, monkeypatch, caplog):
    settings, _client = startup
    failure = ValueError(f"{REDIS_URL}; {PRIVATE_DETAIL}")

    def fail(**_kwargs):
        raise failure

    monkeypatch.setattr(factory.redis, "from_url", fail)
    with pytest.raises(ValueError) as caught:
        factory.make_redis_client(settings)
    assert caught.value is failure
    messages = _messages(caplog)
    _assert_private_values_absent(messages)
    assert "ValueError" in messages


def test_cache_construction_failure_keeps_exception_private(
    startup, monkeypatch, caplog
):
    settings, _client = startup
    failure = ValueError(f"{PRIVATE_DETAIL}; {PASSWORD}")

    def fail(*_args):
        raise failure

    monkeypatch.setattr(factory, "CacheClient", fail)
    with pytest.raises(ValueError) as caught:
        factory.make_cache_client(settings)
    assert caught.value is failure
    messages = _messages(caplog)
    _assert_private_values_absent(messages)
    assert "ValueError" in messages
