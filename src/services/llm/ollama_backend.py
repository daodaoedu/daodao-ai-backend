from typing import Any, Dict, Tuple

import httpx

from src.logger import AppLogger
from src.services.llm.base import BaseLLMBackend

logger = AppLogger(__name__).get_logger()


class OllamaBackend(BaseLLMBackend):
    """Ollama 本地 LLM backend（httpx，無官方 async SDK）"""

    def __init__(self, config: dict):
        super().__init__(config)
        self._timeout = httpx.Timeout(300)

    async def generate(
        self, prompt: str, **kwargs
    ) -> Tuple[str, float, Dict[str, Any], str]:
        base = self.config["url"].rstrip("/")
        url = base if base.endswith("/api/generate") else f"{base}/api/generate"
        options: dict = {
            "num_predict": kwargs.get("max_tokens", 500),
            "temperature": kwargs.get("temperature", 0.7),
        }
        if kwargs.get("top_p") is not None:
            options["top_p"] = float(kwargs["top_p"])
        if kwargs.get("top_k") is not None:
            options["top_k"] = int(kwargs["top_k"])
        payload = {
            "model": self.config["model"],
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"Ollama 呼叫失敗: {e}")
                raise
            data = resp.json()
            output = data.get("response", "未提供回應")
            input_tokens = data.get("prompt_eval_count", 0) or 0
            output_tokens = data.get("eval_count", 0) or 0
            usage_dict = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "finish_reason": data.get("done_reason"),
            }
            cost = self._estimate_token_cost(input_tokens + output_tokens, 0.0)
            return output, cost, usage_dict, "ollama"

    async def check_health(self) -> bool:
        base = self.config["url"].rstrip("/")
        # Ollama 健康檢查：先檢查 tags 確保服務在線，再檢查模型是否存在
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                # 1. 檢查服務
                resp = await client.get(f"{base}/api/tags")
                if resp.status_code != 200:
                    return False

                # 2. 檢查特定模型 (Optional but recommended)
                # data = resp.json()
                # models = [m['name'] for m in data.get('models', [])]
                # return self.config["model"] in models
                return True
            except Exception as e:
                logger.warning(f"Ollama 健康檢查失敗: {e}")
                return False
