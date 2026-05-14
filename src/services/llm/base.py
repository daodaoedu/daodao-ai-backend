from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple


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
