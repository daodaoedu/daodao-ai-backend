from functools import lru_cache

from config import get_settings
from services.clickhouse.client import ClickHouseClient


@lru_cache(maxsize=1)
def make_clickhouse_client():
    """
    Create and return a singleton Ollama client instance.

    Returns:
        OllamaClient: Configured Ollama client
    """
    settings = get_settings()
    return ClickHouseClient(settings.clickhouse)
