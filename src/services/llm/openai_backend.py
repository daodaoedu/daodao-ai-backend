from typing import Any, Dict, Tuple

from openai import AsyncOpenAI

from src.logger import AppLogger
from src.services.llm.base import BaseLLMBackend

logger = AppLogger(__name__).get_logger()


class OpenAIBackend(BaseLLMBackend):
    """OpenAI Chat Completions API backend"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = AsyncOpenAI(
            api_key=config.get("api_key"),
            base_url=config.get("url", "https://api.openai.com/v1")
        )

    async def generate(
        self, prompt: str, **kwargs
    ) -> Tuple[str, float, Dict[str, Any], str]:
        try:
            response = await self._client.chat.completions.create(
                model=self.config["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 1000),
            )
            output = response.choices[0].message.content or "未提供回應"
            usage_dict = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
            cost = self._calc_cost(usage_dict)
            return output, cost, usage_dict, "openai"
        except Exception as e:
            logger.error(f"OpenAI 呼叫失敗: {e}")
            return f"錯誤：{e}", 0.0, {}, "openai"

    async def check_health(self) -> bool:
        try:
            await self._client.chat.completions.create(
                model=self.config["model"],
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return True
        except Exception as e:
            logger.warning(f"OpenAI 健康檢查失敗: {e}")
            return False

    def _calc_cost(self, usage: dict) -> float:
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        
        # 根據模型決定費率
        model = self.config.get("model", "")
        if "gpt-4o-mini" in model:
            input_rate = 0.15
            output_rate = 0.60
        else:
            input_rate = 2.50
            output_rate = 10.00
            
        input_cost = input_tokens / 1_000_000 * input_rate
        output_cost = output_tokens / 1_000_000 * output_rate
        return round(input_cost + output_cost, 6)
