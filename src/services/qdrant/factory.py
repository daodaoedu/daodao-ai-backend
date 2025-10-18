from functools import lru_cache

from src.config import get_settings
from src.services.qdrant.client import QdrantClient


@lru_cache(maxsize=1)
def make_qdrant_client() -> QdrantClient:
    """
    Create and return a singleton Ollama client instance.

    Returns:
        OllamaClient: Configured Ollama client
    """
    settings = get_settings()
    return QdrantClient(settings)
