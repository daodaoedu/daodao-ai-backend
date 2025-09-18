import logging

import redis
from config import Settings
from services.cache.client import CacheClient

logger = logging.getLogger(__name__)


def make_redis_client(settings: Settings) -> redis.Redis:
    """Create Redis client with connection pooling."""
    redis_settings = settings.redis

    try:
        client = redis.from_url(url=redis_settings.url)

        # Test connection
        client.ping()
        logger.info(f"Connected to Redis at {redis_settings.url}")
        return client

    except redis.ConnectionError as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating Redis client: {e}")
        raise


def make_cache_client(settings: Settings) -> CacheClient:
    """Create exact match cache client."""
    try:
        redis_client = make_redis_client(settings)
        cache_client = CacheClient(redis_client, settings.redis)
        logger.info("Exact match cache client created successfully")
        return cache_client
    except Exception as e:
        logger.error(f"Failed to create cache client: {e}")
        raise