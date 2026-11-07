import json
from datetime import timedelta
from typing import Any, Optional

import redis

from src.config import RedisSettings
from src.logger import AppLogger

logger = AppLogger(__name__).get_logger()


class CacheClient:
    """Redis-based exact match cache for RAG queries."""

    def __init__(self, redis_client: redis.Redis, settings: RedisSettings):
        self.client = redis_client
        self.settings = settings
        self.ttl = timedelta(hours=settings.ttl_hours)

    def check_redis_health(self):
        try:
            self.client.ping()  # 嘗試 ping Redis
            logger.info("Redis service is healthy.")
            return True
        except redis.RedisError:
            return False

    def write_dict(
        self, key: str, value: dict[str, Any], expire: Optional[int] = None
    ) -> None:
        self.client.set(key, json.dumps(value), ex=expire or 600)

    def read_dict(self, key: str) -> Optional[dict[str, Any]]:
        data = self.client.get(key)
        if data is None:
            return None
        try:
            value = json.loads(data)
        except (ValueError, UnicodeDecodeError, RecursionError):
            logger.warning("Invalid dictionary cache payload; treating as cache miss")
            return None
        if not isinstance(value, dict):
            logger.warning("Non-dictionary cache payload; treating as cache miss")
            return None
        return value

    def delete(self, *names: str) -> None:
        self.client.delete(*names)

    def expire(self, name: str, expire: Optional[int] = None) -> None:
        self.client.expire(name, expire or 600)
