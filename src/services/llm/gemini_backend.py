from typing import Any, Dict, Tuple

from google import genai
from google.genai import types as genai_types

from src.logger import AppLogger
from src.services.llm.base import BaseLLMBackend

logger = AppLogger(__name__).get_logger()


class GeminiBackend(BaseLLMBackend):
    """Google Gemini backend（google-genai SDK）"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._client = genai.Client(
            api_key=config.get("api_key"),
            http_options={"timeout": 120000},
        )

    async def generate(
        self, prompt: str, **kwargs
    ) -> Tuple[str, float, Dict[str, Any], str]:
        gen_config: dict = {}
        if kwargs.get("max_tokens") is not None:
            gen_config["max_output_tokens"] = int(kwargs["max_tokens"])
        if kwargs.get("temperature") is not None:
            gen_config["temperature"] = float(kwargs["temperature"])
        if kwargs.get("top_p") is not None:
            gen_config["top_p"] = float(kwargs["top_p"])
        if kwargs.get("top_k") is not None:
            gen_config["top_k"] = int(kwargs["top_k"])
        try:
            # 修正：google-genai SDK 的異步調用方式
            response = await self._client.aio.models.generate_content(
                model=self.config["model"],
                contents=prompt,
                config=(
                    genai_types.GenerateContentConfig(**gen_config)
                    if gen_config
                    else None
                ),
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
            finish_reason = None
            try:
                if response.candidates:
                    finish_reason = (
                        str(response.candidates[0].finish_reason).split(".")[-1].lower()
                    )
            except Exception:
                pass
            usage_dict = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_tokens": estimated,
                "finish_reason": finish_reason,
            }
            cost = self._estimate_token_cost(input_tokens + output_tokens, 0.01)
            return output, cost, usage_dict, "gemini"
        except Exception as e:
            logger.error(f"Gemini 呼叫失敗: {e}")
            raise

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
