from typing import Any, Dict, Tuple

from openai import AsyncOpenAI

from src.logger import AppLogger
from src.services.llm.base import BaseLLMBackend

logger = AppLogger(__name__).get_logger()


class OpenAIChatBackend(BaseLLMBackend):
    """通用 OpenAI Chat Completions 相容 backend（cloudflare / nvidia / cerebras / openrouter / ollama_cloud）"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._backend_name = config.get(
            "backend_name", config.get("provider", "openai_chat")
        )
        api_key = config.get("api_key")
        if not api_key:
            raise ValueError(f"{self._backend_name} 缺少 api_key 設定")
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=config.get("url"),
            timeout=120.0,
        )

    async def generate(
        self, prompt: str, **kwargs
    ) -> Tuple[str, float, Dict[str, Any], str]:
        top_p_val = kwargs.get("top_p")
        try:
            response = await self._client.chat.completions.create(
                model=self.config["model"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=kwargs.get("max_tokens", 600),
                temperature=kwargs.get("temperature", 0.7),
                **({"top_p": float(top_p_val)} if top_p_val is not None else {}),
            )
            if not response.choices:
                return "未提供回應", 0.0, {}, self._backend_name
            output = response.choices[0].message.content or "未提供回應"
            usage_dict = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "finish_reason": (
                    response.choices[0].finish_reason if response.choices else None
                ),
            }
            cost = 0.0
            return output, cost, usage_dict, self._backend_name
        except Exception as e:
            logger.error(f"{self._backend_name} 呼叫失敗: {e}")
            raise

    async def check_health(self) -> bool:
        try:
            await self._client.chat.completions.create(
                model=self.config["model"],
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return True
        except Exception as e:
            logger.warning(f"{self._backend_name} 健康檢查失敗: {e}")
            return False
