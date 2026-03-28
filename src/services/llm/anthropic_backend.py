from typing import Any, Dict, Tuple

from anthropic import AsyncAnthropic

from src.logger import AppLogger
from src.services.llm.base import BaseLLMBackend

logger = AppLogger(__name__).get_logger()

# claude-3-5-sonnet-20241022 定價（USD/1M tokens）
_ANTHROPIC_INPUT_PRICE = 3.00
_ANTHROPIC_OUTPUT_PRICE = 15.00


class AnthropicBackend(BaseLLMBackend):
    """Anthropic Claude backend（anthropic SDK）"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = AsyncAnthropic(api_key=config.get("api_key"))

    async def generate(
        self, prompt: str, **kwargs
    ) -> Tuple[str, float, Dict[str, Any], str]:
        max_tokens = kwargs.get("max_tokens", 1024)
        try:
            message = await self._client.messages.create(
                model=self.config["model"],
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            output = message.content[0].text if message.content else "未提供回應"
            usage_dict = {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            }
            cost = self._calc_cost(usage_dict)
            return output, cost, usage_dict, "anthropic"
        except Exception as e:
            logger.error(f"Anthropic 呼叫失敗: {e}")
            return f"錯誤：{e}", 0.0, {}, "anthropic"

    def _calc_cost(self, usage: dict) -> float:
        input_cost = usage.get("input_tokens", 0) / 1_000_000 * _ANTHROPIC_INPUT_PRICE
        output_cost = (
            usage.get("output_tokens", 0) / 1_000_000 * _ANTHROPIC_OUTPUT_PRICE
        )
        return round(input_cost + output_cost, 6)
