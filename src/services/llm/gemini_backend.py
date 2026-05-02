from typing import Any, Dict, Tuple

from google import genai

from src.logger import AppLogger
from src.services.llm.base import BaseLLMBackend

logger = AppLogger(__name__).get_logger()


class GeminiBackend(BaseLLMBackend):
    """Google Gemini backend（google-genai SDK）"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = genai.Client(api_key=config.get("api_key"))

    async def generate(
        self, prompt: str, **kwargs
    ) -> Tuple[str, float, Dict[str, Any], str]:
        try:
            # 修正：google-genai SDK 的異步調用方式
            response = await self._client.aio.models.generate_content(
                model=self.config["model"],
                contents=prompt,
            )
            output = response.text or "未提供回應"
            meta = response.usage_metadata
            try:
                input_tokens = int(meta.prompt_token_count or 0)
                output_tokens = int(meta.candidates_token_count or 0)
            except (TypeError, AttributeError, ValueError):
                input_tokens = 0
                output_tokens = 0
            estimated = self._estimate_tokens(prompt) + (output_tokens or 1)
            usage_dict = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_tokens": estimated,
            }
            cost = self._estimate_token_cost(input_tokens + output_tokens, 0.01)
            return output, cost, usage_dict, "gemini"
        except Exception as e:
            logger.error(f"Gemini 呼叫失敗: {e}")
            return f"錯誤：{e}", 0.0, {}, "gemini"

    async def check_health(self) -> bool:
        try:
            await self._client.aio.models.generate_content(
                model=self.config["model"],
                contents="ping",
                config={"max_output_tokens": 1},
            )
            return True
        except Exception as e:
            logger.warning(f"Gemini 健康檢查失敗: {e}")
            return False
