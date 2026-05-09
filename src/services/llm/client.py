from typing import Any, Dict, Tuple

from src.config import Settings
from src.logger import AppLogger
from src.services.llm.anthropic_backend import AnthropicBackend
from src.services.llm.base import BaseLLMBackend
from src.services.llm.gemini_backend import GeminiBackend
from src.services.llm.groq_backend import GroqBackend
from src.services.llm.ollama_backend import OllamaBackend
from src.services.llm.openai_backend import OpenAIBackend
from src.services.llm.openai_chat_backend import OpenAIChatBackend
from src.services.prompts.prompts import RAGPromptBuilder, ResponseParser

logger = AppLogger(__name__).get_logger()

_BACKEND_MAP: Dict[str, type] = {
    "openai": OpenAIBackend,
    "gemini": GeminiBackend,
    "anthropic": AnthropicBackend,
    "ollama": OllamaBackend,
    "groq": GroqBackend,
    "cloudflare": OpenAIChatBackend,
    "nvidia": OpenAIChatBackend,
    "cerebras": OpenAIChatBackend,
    "openrouter": OpenAIChatBackend,
    "ollama_cloud": OpenAIChatBackend,
}


class LLMClient:
    def __init__(self, settings: Settings, backend: str):
        if backend not in settings.llm_backend:
            raise ValueError(f"LLM backend '{backend}' 未在設定中定義")

        backend_cfg = settings.llm_backend[backend]
        backend_cls = _BACKEND_MAP.get(backend)
        if backend_cls is None:
            raise ValueError(f"不支援的 LLM backend: {backend}")

        self.backend = backend
        self._backend: BaseLLMBackend = backend_cls(
            {
                "url": backend_cfg.url,
                "model": backend_cfg.model,
                "api_key": backend_cfg.api_key,
                "backend_name": backend,
            }
        )
        # 保留給外部服務使用的 prompt 工具
        self.prompt_builder = RAGPromptBuilder()
        self.response_parser = ResponseParser()

    async def generate(
        self,
        prompt: str,
        **kwargs,
    ) -> Tuple[str, float, Dict[str, Any], str]:
        """
        呼叫 LLM 生成回應。
        回傳 (output, cost, usage, backend_name)
        """
        return await self._backend.generate(prompt, **kwargs)
