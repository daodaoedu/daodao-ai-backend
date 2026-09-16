"""Redis settings use explicit, isolated environment inputs."""

from unittest.mock import patch

import pytest

from src.config import RedisSettings


class TestRedisSettingsTTL:
    def test_ttl_hours_with_valid_int(self):
        with patch.dict("os.environ", {"REDIS_TTL_HOURS": "3"}, clear=True):
            assert RedisSettings(_env_file=None).ttl_hours == 3

    def test_ttl_hours_fallback_when_old_key_used(self):
        with patch.dict("os.environ", {"REDIS_TTL_HOUR": "3"}, clear=True):
            assert RedisSettings(_env_file=None).ttl_hours == 6

    def test_ttl_hours_default_is_int(self):
        with patch.dict("os.environ", {}, clear=True):
            assert RedisSettings(_env_file=None).ttl_hours == 6

    def test_empty_ttl_is_invalid(self):
        with patch.dict("os.environ", {"REDIS_TTL_HOURS": ""}, clear=True):
            with pytest.raises(ValueError):
                RedisSettings(_env_file=None)
