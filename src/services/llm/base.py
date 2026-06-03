import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

_RETRYABLE_EXCEPTIONS = (
    TimeoutError,
    ConnectionError,
    OSError,
)

# Exceptions from httpx / openai / anthropic / google-genai that indicate
# transient failures worth retrying.
_RETRYABLE_NAMES = {
    "ConnectError",
    "ReadTimeout",
    "WriteTimeout",
    "PoolTimeout",
    "RemoteProtocolError",
    "APITimeoutError",
    "APIConnectionError",
    "InternalServerError",
    "ServiceUnavailable",
}


def _is_retryable(exc: Exception) -> bool:
    return isinstance(exc, _RETRYABLE_EXCEPTIONS) or type(exc).__name__ in _RETRYABLE_NAMES


async def with_retry(coro_fn, max_attempts: int = 3, base_delay: float = 1.0):
    """Retry an async callable with exponential backoff on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await coro_fn()
        except Exception as exc:
            if not _is_retryable(exc) or attempt == max_attempts - 1:
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "LLM call failed (attempt %d/%d): %s — retrying in %.1fs",
                attempt + 1, max_attempts, exc, delay,
            )
            last_exc = exc
            await asyncio.sleep(delay)
    raise last_exc  # unreachable but satisfies type checkers


class BaseLLMBackend(ABC):
    """所有 LLM backend 的抽象基底類別"""

    def __init__(self, config: dict):
        self.config = config  # {"url": ..., "model": ..., "api_key": ...}

    @abstractmethod
    async def generate(
        self, prompt: str, **kwargs
    ) -> Tuple[str, float, Dict[str, Any], str]:
        """
        呼叫 LLM 生成回應。
        回傳 (output, cost, usage, backend_name)
        """
        raise NotImplementedError

    @abstractmethod
    async def check_health(self) -> bool:
        """
        檢查 LLM backend 是否可用（API Key, URL, 模型權限）。
        """
        raise NotImplementedError

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _estimate_token_cost(self, token_count: int, rate_per_1k: float) -> float:
        return round(token_count / 1000 * rate_per_1k, 6)
