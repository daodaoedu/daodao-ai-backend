"""Dictionary cache preserves Redis behavior without executing cached objects."""

import json
import pickle
import shutil
import subprocess
import time
import tempfile
from unittest.mock import Mock

import pytest
import redis

from src.config import RedisSettings
from src.services.cache.client import CacheClient


@pytest.fixture
def redis_client():
    server = shutil.which("redis-server")
    if not server:
        pytest.skip("redis-server is required for cache integration regressions")
    temp_dir = tempfile.TemporaryDirectory(prefix="cache-test-", dir="/tmp")
    socket = temp_dir.name + "/redis.sock"
    process = subprocess.Popen(
        [
            server,
            "--port",
            "0",
            "--unixsocket",
            socket,
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = redis.Redis(unix_socket_path=socket)
    try:
        for _ in range(100):
            try:
                client.ping()
                break
            except redis.ConnectionError:
                time.sleep(0.01)
        else:
            pytest.fail("disposable Redis did not start")
        yield client
    finally:
        client.close()
        process.terminate()
        process.wait(timeout=5)
        temp_dir.cleanup()


@pytest.fixture
def cache(redis_client):
    return CacheClient(redis_client, RedisSettings(_env_file=None))


@pytest.mark.parametrize("expire, expected_ttl", [(None, 600), (120, 120), (0, 600)])
def test_dictionary_roundtrip_and_ttl(cache, redis_client, expire, expected_ttl):
    value = {"status": "done", "content": "中文", "nested": {"tokens": 12}, "ok": True}
    cache.write_dict("feedback:test", value, expire=expire)
    assert cache.read_dict("feedback:test") == value
    assert json.loads(redis_client.get("feedback:test")) == value
    assert expected_ttl - 1 <= redis_client.ttl("feedback:test") <= expected_ttl


@pytest.mark.parametrize(
    "payload", [b"not-json", b"\xff", b"[]", b"null", b'"text"', b"12"]
)
def test_invalid_payload_is_cache_miss(cache, redis_client, payload):
    redis_client.set("legacy", payload)
    assert cache.read_dict("legacy") is None


def test_missing_key_is_cache_miss(cache):
    assert cache.read_dict("missing") is None


# A safe-to-test pickle that would call a spy if unpickled, without shell/file effects.
_PICKLE_EXECUTED = Mock()


def record_pickle_execution():
    _PICKLE_EXECUTED()
    return {"status": "unsafe"}


class ExecutablePickle:
    def __reduce__(self):
        return record_pickle_execution, ()


def test_legacy_pickle_never_executes(cache, redis_client):
    _PICKLE_EXECUTED.reset_mock()
    redis_client.set("legacy", pickle.dumps(ExecutablePickle()))
    assert cache.read_dict("legacy") is None
    _PICKLE_EXECUTED.assert_not_called()


def test_delete_and_expire_reuse_injected_client(cache, redis_client):
    redis_client.set("one", "1")
    redis_client.set("two", "2")
    cache.expire("one", 30)
    assert 29 <= redis_client.ttl("one") <= 30
    cache.delete("one", "two")
    assert redis_client.get("one") is None
    assert redis_client.get("two") is None


def test_default_expiration_remains_600_seconds(cache, redis_client):
    redis_client.set("one", "1")
    cache.expire("one")
    assert 599 <= redis_client.ttl("one") <= 600
