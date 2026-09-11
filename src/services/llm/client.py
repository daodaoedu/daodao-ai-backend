from typing import Any, Dict, Optional, Tuple

from src.config import _LLM_BACKEND_DEFAULTS, Settings
from src.logger import AppLogger
from src.services.llm.anthropic_backend import AnthropicBackend
from src.services.llm.base import BaseLLMBackend
from src.services.llm.gemini_backend import GeminiBackend
from src.services.llm.groq_backend import GroqBackend
from src.services.llm.guardrail import GuardrailLayer
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
    def __init__(
        self,
        settings: Settings,
        backend: str,
        enable_guardrail: bool = True,
        api_key_override: Optional[str] = None,
    ):
        if backend not in settings.llm_backend:
            raise ValueError(f"LLM backend '{backend}' 未在設定中定義")

        backend_cfg = settings.llm_backend[backend]
        backend_cls = _BACKEND_MAP.get(backend)
        if backend_cls is None:
            raise ValueError(f"不支援的 LLM backend: {backend}")

        self.backend = backend
        self.model = backend_cfg.model
        self._backend: BaseLLMBackend = backend_cls(
            {
                "url": backend_cfg.url,
                "model": backend_cfg.model,
                "api_key": api_key_override or backend_cfg.api_key,
                "backend_name": backend,
            }
        )
        self._enable_guardrail = enable_guardrail
        # 保留給外部服務使用的 prompt 工具
        self.prompt_builder = RAGPromptBuilder()
        self.response_parser = ResponseParser()

    @classmethod
    def with_credentials(
        cls, settings: Settings, backend: str, api_key: str
    ) -> "LLMClient":
        """
        用呼叫端提供的 API key 建 client（燈塔組織自帶 key）：
        url / model 沿設定檔（沒設定就用預設表），只換 key；key 不落地、不快取。
        """
        if backend not in _BACKEND_MAP:
            raise ValueError(f"不支援的 LLM backend: {backend}")
        if backend in settings.llm_backend:
            return cls(settings, backend, api_key_override=api_key)
        defaults = _LLM_BACKEND_DEFAULTS.get(backend)
        if defaults is None:
            raise ValueError(f"LLM backend '{backend}' 沒有預設設定")
        client = cls.__new__(cls)
        client.backend = backend
        client.model = defaults["model"]
        client._backend = _BACKEND_MAP[backend](
            {
                "url": defaults["url"],
                "model": defaults["model"],
                "api_key": api_key,
                "backend_name": backend,
            }
        )
        client._enable_guardrail = True
        client.prompt_builder = RAGPromptBuilder()
        client.response_parser = ResponseParser()
        return client

    async def generate(
        self,
        prompt: str,
        **kwargs,
    ) -> Tuple[str, float, Dict[str, Any], str]:
        """
        呼叫 LLM 生成回應。
        回傳 (output, cost, usage, backend_name)
        """
        if self._enable_guardrail:
            prompt = prompt + GuardrailLayer.GUARDRAIL_SUFFIX
        return await self._backend.generate(prompt, **kwargs)
