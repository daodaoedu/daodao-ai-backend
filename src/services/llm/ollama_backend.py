from typing import Any, Dict, Tuple

import httpx

from src.logger import AppLogger
from src.services.llm.base import BaseLLMBackend

logger = AppLogger(__name__).get_logger()


class OllamaBackend(BaseLLMBackend):
    """Ollama 本地 LLM backend（httpx，無官方 async SDK）"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._timeout = httpx.Timeout(300)

    async def generate(
        self, prompt: str, **kwargs
    ) -> Tuple[str, float, Dict[str, Any], str]:
        url = self.config["url"]
        payload = {
            "model": self.config["model"],
            "prompt": prompt,
            "max_tokens": kwargs.get("max_tokens", 500),
            "temperature": kwargs.get("temperature", 0.7),
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"Ollama 呼叫失敗: {e}")
                return f"錯誤：{e}", 0.0, {}, "ollama"
            data = resp.json()
            output = data.get("completion", "未提供回應")
            tokens = self._estimate_tokens(prompt + output)
            cost = self._estimate_token_cost(tokens, 0.005)
            return output, cost, {"estimated_tokens": tokens}, "ollama"
