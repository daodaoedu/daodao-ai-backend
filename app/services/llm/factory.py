from functools import lru_cache

from config import get_settings
from services.llm.client import LLMClient


@lru_cache(maxsize=1)
def make_llm_client():
    """
    Create and return a singleton Ollama client instance.

    Returns:
        OllamaClient: Configured Ollama client
    """
    settings = get_settings()
    return LLMClient(settings, "gemini")
    