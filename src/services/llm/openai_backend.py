from typing import Any, Dict, Tuple

from openai import AsyncOpenAI

from src.logger import AppLogger
from src.services.llm.base import BaseLLMBackend

logger = AppLogger(__name__).get_logger()


class OpenAIBackend(BaseLLMBackend):
    """OpenAI Responses API backend（openai SDK v2）"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = AsyncOpenAI(api_key=config.get("api_key"))

    async def generate(
        self, prompt: str, **kwargs
    ) -> Tuple[str, float, Dict[str, Any], str]:
        try:
            response = await self._client.responses.create(
                model=self.config["model"],
                input=prompt,
            )
            output = response.output_text or "未提供回應"
            usage_dict = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "input_tokens_details": {
                    "cached_tokens": (
                        response.usage.input_tokens_details.cached_tokens
                        if response.usage.input_tokens_details
                        else 0
                    )
                },
            }
            cost = self._calc_cost(usage_dict)
            return output, cost, usage_dict, "openai"
        except Exception as e:
            logger.error(f"OpenAI 呼叫失敗: {e}")
            return f"錯誤：{e}", 0.0, {}, "openai"

    def _calc_cost(self, usage: dict) -> float:
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cached_tokens = usage.get("input_tokens_details", {}).get("cached_tokens", 0)
        normal_input = max(0, input_tokens - cached_tokens)
        input_cost = normal_input / 1_000_000 * 5.00
        cached_cost = cached_tokens / 1_000_000 * 2.50
        output_cost = output_tokens / 1_000_000 * 20.00
        return round(input_cost + cached_cost + output_cost, 6)
