from typing import Any, Dict, Tuple

from anthropic import AsyncAnthropic

from src.logger import AppLogger
from src.services.llm.base import BaseLLMBackend

logger = AppLogger(__name__).get_logger()


class AnthropicBackend(BaseLLMBackend):
    """Anthropic Claude backend（anthropic SDK）"""

    def __init__(self, config: dict):
        super().__init__(config)
        # SDK 會自動處理 /v1/messages，所以這裡只給 base_url
        self._client = AsyncAnthropic(
            api_key=config.get("api_key"),
            base_url=config.get("url", "https://api.anthropic.com")
        )

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

    async def check_health(self) -> bool:
        try:
            await self._client.messages.create(
                model=self.config["model"],
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception as e:
            logger.warning(f"Anthropic 健康檢查失敗: {e}")
            return False

    def _calc_cost(self, usage: dict) -> float:
        model = self.config.get("model", "")
        if "haiku" in model:
            input_price = 0.25
            output_price = 1.25
        else:
            input_price = 3.00
            output_price = 15.00
            
        input_cost = usage.get("input_tokens", 0) / 1_000_000 * input_price
        output_cost = (
            usage.get("output_tokens", 0) / 1_000_000 * output_price
        )
        return round(input_cost + output_cost, 6)
