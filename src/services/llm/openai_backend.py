from typing import Any, Dict, Tuple

from openai import AsyncOpenAI

from src.logger import AppLogger
from src.services.llm.base import BaseLLMBackend

logger = AppLogger(__name__).get_logger()


class OpenAIBackend(BaseLLMBackend):
    """OpenAI Responses API backend"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = AsyncOpenAI(
            api_key=config.get("api_key"),
            base_url=config.get("url", "https://api.openai.com/v1"),
        )

    async def generate(
        self, prompt: str, **kwargs
    ) -> Tuple[str, float, Dict[str, Any], str]:
        try:
            response = await self._client.responses.create(
                model=self.config["model"],
                input=prompt,
                max_output_tokens=kwargs.get("max_tokens", 1000),
            )
            output = response.output_text or "未提供回應"
            details = getattr(response.usage, "input_tokens_details", None)
            cached_tokens = getattr(details, "cached_tokens", 0) or 0
            usage_dict = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "input_tokens_details": {"cached_tokens": cached_tokens},
            }
            cost = self._calc_cost(usage_dict)
            return output, cost, usage_dict, "openai"
        except Exception as e:
            logger.error(f"OpenAI 呼叫失敗: {e}")
            return f"錯誤：{e}", 0.0, {}, "openai"

    async def check_health(self) -> bool:
        try:
            await self._client.responses.create(
                model=self.config["model"],
                input="ping",
                max_output_tokens=1,
            )
            return True
        except Exception as e:
            logger.warning(f"OpenAI 健康檢查失敗: {e}")
            return False

    def _calc_cost(self, usage: dict) -> float:
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        details = usage.get("input_tokens_details", {})
        cached_tokens = (
            details.get("cached_tokens", 0) if isinstance(details, dict) else 0
        )

        model = self.config.get("model", "")
        if "gpt-4o-mini" in model:
            input_rate = 0.15
            cached_rate = 0.075
            output_rate = 0.60
        else:
            input_rate = 2.50
            cached_rate = 1.25
            output_rate = 10.00

        non_cached = max(0, input_tokens - cached_tokens)
        input_cost = (non_cached / 1_000_000 * input_rate) + (
            cached_tokens / 1_000_000 * cached_rate
        )
        output_cost = output_tokens / 1_000_000 * output_rate
        return round(input_cost + output_cost, 6)
