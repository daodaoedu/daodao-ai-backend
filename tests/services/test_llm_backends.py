"""
Unit tests for LLM backends:
  - src.services.llm.anthropic_backend.AnthropicBackend
  - src.services.llm.openai_backend.OpenAIBackend
  - src.services.llm.gemini_backend.GeminiBackend

所有測試均 mock 第三方 SDK，不發出真實 HTTP 請求。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.llm.anthropic_backend import AnthropicBackend
from src.services.llm.gemini_backend import GeminiBackend
from src.services.llm.openai_backend import OpenAIBackend

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

_ANTHROPIC_CFG = {"api_key": "test-key", "model": "claude-3-5-sonnet-20241022"}
_OPENAI_CFG = {"api_key": "test-key", "model": "gpt-4o"}
_GEMINI_CFG = {"api_key": "test-key", "model": "gemini-2.0-flash"}


# ═════════════════════════════════════════════════════════════
# AnthropicBackend
# ═════════════════════════════════════════════════════════════


class TestAnthropicBackend:

    def _make_backend(self) -> AnthropicBackend:
        with patch("src.services.llm.anthropic_backend.AsyncAnthropic"):
            return AnthropicBackend(_ANTHROPIC_CFG)

    # ── 正常生成 ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_returns_text(self):
        backend = self._make_backend()
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="成長洞察內容")]
        mock_message.usage.input_tokens = 100
        mock_message.usage.output_tokens = 50
        backend._client.messages.create = AsyncMock(return_value=mock_message)

        output, cost, usage, name = await backend.generate("test prompt", max_tokens=600)

        assert output == "成長洞察內容"
        assert name == "anthropic"
        assert cost >= 0
        assert "input_tokens" in usage
        assert "output_tokens" in usage

    @pytest.mark.asyncio
    async def test_generate_empty_content_returns_fallback(self):
        backend = self._make_backend()
        mock_message = MagicMock()
        mock_message.content = []
        mock_message.usage.input_tokens = 10
        mock_message.usage.output_tokens = 0
        backend._client.messages.create = AsyncMock(return_value=mock_message)

        output, _, _, _ = await backend.generate("prompt")

        assert output == "未提供回應"

    # ── 錯誤處理 ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_api_error_propagates(self):
        backend = self._make_backend()
        backend._client.messages.create = AsyncMock(
            side_effect=Exception("API rate limit")
        )

        with pytest.raises(Exception, match="API rate limit"):
            await backend.generate("prompt")

    # ── Cost 計算 ─────────────────────────────────────────────

    def test_calc_cost_proportional_to_tokens(self):
        backend = self._make_backend()
        small = backend._calc_cost({"input_tokens": 1000, "output_tokens": 500})
        large = backend._calc_cost({"input_tokens": 10000, "output_tokens": 5000})
        assert large > small

    def test_calc_cost_zero_tokens_returns_zero(self):
        backend = self._make_backend()
        assert backend._calc_cost({"input_tokens": 0, "output_tokens": 0}) == 0.0


# ═════════════════════════════════════════════════════════════
# OpenAIBackend
# ═════════════════════════════════════════════════════════════


class TestOpenAIBackend:

    def _make_backend(self) -> OpenAIBackend:
        with patch("src.services.llm.openai_backend.AsyncOpenAI"):
            return OpenAIBackend(_OPENAI_CFG)

    # ── 正常生成 ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_returns_text(self):
        backend = self._make_backend()
        mock_response = MagicMock()
        mock_response.output_text = "AI 生成的建議"
        mock_response.usage.input_tokens = 200
        mock_response.usage.output_tokens = 80
        mock_response.usage.input_tokens_details = MagicMock(cached_tokens=0)
        backend._client.responses.create = AsyncMock(return_value=mock_response)

        output, cost, usage, name = await backend.generate("test prompt")

        assert output == "AI 生成的建議"
        assert name == "openai"
        assert cost >= 0
        assert "input_tokens" in usage

    @pytest.mark.asyncio
    async def test_generate_empty_output_returns_fallback(self):
        backend = self._make_backend()
        mock_response = MagicMock()
        mock_response.output_text = ""
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 0
        mock_response.usage.input_tokens_details = MagicMock(cached_tokens=0)
        backend._client.responses.create = AsyncMock(return_value=mock_response)

        output, _, _, _ = await backend.generate("prompt")

        assert output == "未提供回應"

    # ── Cached tokens ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_cached_tokens_reduce_cost(self):
        backend = self._make_backend()

        def _make_response(cached: int):
            r = MagicMock()
            r.output_text = "回應"
            r.usage.input_tokens = 1000
            r.usage.output_tokens = 100
            r.usage.input_tokens_details = MagicMock(cached_tokens=cached)
            return r

        backend._client.responses.create = AsyncMock(
            side_effect=[_make_response(0), _make_response(800)]
        )
        _, cost_no_cache, _, _ = await backend.generate("prompt")
        _, cost_with_cache, _, _ = await backend.generate("prompt")

        # cached tokens 費率較低，成本應更低
        assert cost_with_cache < cost_no_cache

    # ── 錯誤處理 ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_api_error_propagates(self):
        backend = self._make_backend()
        backend._client.responses.create = AsyncMock(
            side_effect=Exception("Connection timeout")
        )

        with pytest.raises(Exception, match="Connection timeout"):
            await backend.generate("prompt")

    # ── Cost 計算 ─────────────────────────────────────────────

    def test_calc_cost_no_cached_tokens(self):
        backend = self._make_backend()
        cost = backend._calc_cost(
            {
                "input_tokens": 1000,
                "output_tokens": 500,
                "input_tokens_details": {"cached_tokens": 0},
            }
        )
        assert cost > 0

    def test_calc_cost_missing_details_defaults_zero(self):
        backend = self._make_backend()
        # input_tokens_details 不存在時不應 raise
        cost = backend._calc_cost({"input_tokens": 100, "output_tokens": 50})
        assert cost >= 0


# ═════════════════════════════════════════════════════════════
# GeminiBackend
# ═════════════════════════════════════════════════════════════


class TestGeminiBackend:

    def _make_backend(self) -> GeminiBackend:
        with patch("src.services.llm.gemini_backend.genai"):
            return GeminiBackend(_GEMINI_CFG)

    # ── 正常生成 ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_returns_text(self):
        backend = self._make_backend()
        mock_response = MagicMock()
        mock_response.text = "Gemini 洞察內容"
        backend._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        output, cost, usage, name = await backend.generate("test prompt")

        assert output == "Gemini 洞察內容"
        assert name == "gemini"
        assert cost >= 0
        assert "estimated_tokens" in usage

    @pytest.mark.asyncio
    async def test_generate_empty_text_returns_fallback(self):
        backend = self._make_backend()
        mock_response = MagicMock()
        mock_response.text = ""
        backend._client.aio.models.generate_content = AsyncMock(
            return_value=mock_response
        )

        output, _, _, _ = await backend.generate("prompt")

        assert output == "未提供回應"

    # ── 錯誤處理 ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_generate_api_error_propagates(self):
        backend = self._make_backend()
        backend._client.aio.models.generate_content = AsyncMock(
            side_effect=Exception("Quota exceeded")
        )

        with pytest.raises(Exception, match="Quota exceeded"):
            await backend.generate("prompt")

    # ── Token 估算 ────────────────────────────────────────────

    def test_estimate_tokens_minimum_one(self):
        backend = self._make_backend()
        assert backend._estimate_tokens("") >= 1

    def test_estimate_tokens_scales_with_length(self):
        backend = self._make_backend()
        short = backend._estimate_tokens("hi")
        long_ = backend._estimate_tokens("a" * 400)
        assert long_ > short
