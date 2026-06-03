from typing import Any, Dict, Tuple

from openai import AsyncOpenAI

from src.logger import AppLogger
from src.services.llm.base import BaseLLMBackend, with_retry

logger = AppLogger(__name__).get_logger()


class GroqBackend(BaseLLMBackend):
    """Groq LLM backend（OpenAI SDK，Chat Completions API）"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = AsyncOpenAI(
            api_key=config.get("api_key"),
            base_url=config.get("url", "https://api.groq.com/openai/v1"),
            timeout=30.0,
        )

    async def generate(
        self, prompt: str, **kwargs
    ) -> Tuple[str, float, Dict[str, Any], str]:
        top_p_val = kwargs.get("top_p")
        try:
            response = await with_retry(
                lambda: self._client.chat.completions.create(
                    model=self.config["model"],
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=kwargs.get("max_tokens", 2000),
                    temperature=kwargs.get("temperature", 0.7),
                    **({"top_p": float(top_p_val)} if top_p_val is not None else {}),
                )
            )
            output = response.choices[0].message.content or "未提供回應"
            usage_dict = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
                "finish_reason": response.choices[0].finish_reason,
            }
            cost = 0.0  # Groq 免費方案無費用
            return output, cost, usage_dict, "groq"
        except Exception as e:
            logger.error(f"Groq 呼叫失敗: {e}")
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
            logger.warning(f"Groq 健康檢查失敗: {e}")
            return False
