import redis

from src.config import Settings
from src.logger import AppLogger
from src.services.cache.client import CacheClient

logger = AppLogger(__name__).get_logger()


def make_redis_client(settings: Settings) -> redis.Redis:
    """Create Redis client with connection pooling."""
    redis_settings = settings.redis

    try:
        client = redis.from_url(
            url=redis_settings.url, password=redis_settings.password or None
        )

        # Test connection
        client.ping()
        logger.info("Connected to Redis")
        return client

    except redis.ConnectionError as e:
        logger.error("Failed to connect to Redis: %s", type(e).__name__)
        raise
    except Exception as e:
        logger.error("Unexpected error creating Redis client: %s", type(e).__name__)
        raise


def make_cache_client(settings: Settings) -> CacheClient:
    """Create exact match cache client."""
    try:
        redis_client = make_redis_client(settings)
        cache_client = CacheClient(redis_client, settings.redis)
        logger.info("Exact match cache client created successfully")
        return cache_client
    except Exception as e:
        logger.error("Failed to create cache client: %s", type(e).__name__)
        raise
