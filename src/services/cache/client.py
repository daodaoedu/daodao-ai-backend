import pickle
from datetime import timedelta

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

    @staticmethod
    def _get_r():
        r = redis.from_url(CacheClient.settings.url)
        return r

    @classmethod
    def write_dict(self, key, value, expire=None):
        expire_in_seconds = expire or 600

        r = self._get_r()
        r.set(key, pickle.dumps(value), ex=expire_in_seconds)

    @classmethod
    def read_dict(self, key):
        r = self._get_r()
        data = r.get(key)
        if data is None:
            return None
        return pickle.loads(data)

    @classmethod
    def delete(self, *names):
        r = self._get_r()
        r.delete(*names)

    @classmethod
    def expire(self, name, expire=None):
        expire_in_seconds = expire or 600

        r = self._get_r()
        r.expire(name, expire_in_seconds)
