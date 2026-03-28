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
            response = await self._client.aio.models.generate_content(
                model=self.config["model"],
                contents=prompt,
            )
            output = response.text or "未提供回應"
            tokens = self._estimate_tokens(prompt + output)
            cost = self._estimate_token_cost(tokens, 0.01)
            return output, cost, {"estimated_tokens": tokens}, "gemini"
        except Exception as e:
            logger.error(f"Gemini 呼叫失敗: {e}")
            return f"錯誤：{e}", 0.0, {}, "gemini"
