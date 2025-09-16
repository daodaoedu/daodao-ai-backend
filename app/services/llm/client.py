from typing import Dict, List, Optional
import httpx
from config import Settings
from logger import AppLogger
from qdrant_client import QdrantClient as Client
from qdrant_client import models
from qdrant_client.http.exceptions import UnexpectedResponse
from prompt import RAGPromptBuilder, ResponseParser


logger = AppLogger(__name__).get_logger()


class LLMClient:
    def __init__(self, settings: Settings, backend: str):
        self.settings = settings
        self.backend = backend
        self.conf = settings.llm_backend[backend]  # e.g. settings.llm_backend["openai"]

        self.timeout = httpx.Timeout(300)
        self.prompt_builder = RAGPromptBuilder()
        self.response_parser = ResponseParser()

    def _estimate_cost(self, prompt: str, output: str, usage: dict) -> float:
        if self.backend == "openai":
            # OpenAI 有 usage，照實算
            if usage:
                return self._estimate_openai_cost(usage)
            # 沒有 usage，fallback
            tokens = self._estimate_tokens(prompt + output)
            return self._estimate_token_cost(tokens, 0.09)
        elif self.backend == "gemini":
            tokens = self._estimate_tokens(prompt + output)
            return self._estimate_token_cost(tokens, 0.01)
        elif self.backend == "ollama":
            tokens = self._estimate_tokens(prompt + output)
            return self._estimate_token_cost(tokens, 0.005)
        elif self.backend == "grok":
            tokens = self._estimate_tokens(prompt + output)
            return self._estimate_token_cost(tokens, 0.01)
        return 0.0

    def _estimate_openai_cost(self, usage: dict) -> float:
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        input_tokens_details = usage.get("input_tokens_details", {})
        cached_tokens = input_tokens_details.get("cached_tokens", 0)

        normal_input_tokens = (
            input_tokens - cached_tokens if input_tokens > cached_tokens else 0
        )
        input_cost = normal_input_tokens / 1_000_000 * 5.00
        cached_input_cost = cached_tokens / 1_000_000 * 2.50
        output_cost = output_tokens / 1_000_000 * 20.00
        total_cost = input_cost + cached_input_cost + output_cost

        if input_tokens or output_tokens or cached_tokens:
            return round(total_cost, 6)
        total_tokens = usage.get("total_tokens", 0)
        return round(total_tokens / 1000 * 0.025, 6)

    def _estimate_token_cost(self, token_count: int, rate_per_1k: float) -> float:
        return round(token_count / 1000 * rate_per_1k, 6)

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    async def generate(
        self,
        prompt: str,
        **kwargs,
    ) -> Tuple[str, float, Dict[str, Any], str]:
        """
        單一 query 方法，依照 self.backend 決定調用方式
        回傳 (output, cost, usage, backend_name)
        """
        if self.backend == "openai":
            url = self.conf["url"]
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.conf['api_key']}",
            }
            payload = {"model": self.conf["model"], "input": prompt}

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    return f"錯誤：{resp.text}", 0, {}, "openai"
                data = resp.json()
                output = (
                    data.get("output", [{}])[0].get("content", [{}])[0].get("text", "未提供回應")
                )
                usage = data.get("usage", {})
                cost = self._estimate_cost(prompt, output, usage)
                return output, cost, usage, "openai"

        elif self.backend == "gemini":
            url = f"{self.conf['url']}/?key={self.conf['api_key']}"
            headers = {"Content-Type": "application/json"}
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    return f"錯誤：{resp.text}", 0, {}, "gemini"
                data = resp.json()
                output = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "未提供回應")
                )
                tokens = self._estimate_tokens(prompt + output)
                cost = self._estimate_cost(prompt, output, {"estimated_tokens": tokens})
                return output, cost, {"estimated_tokens": tokens}, "gemini"

        elif self.backend == "ollama":
            url = self.conf["url"]
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": self.conf["model"],
                "prompt": prompt,
                "max_tokens": kwargs.get("max_tokens", 500),
                "temperature": kwargs.get("temperature", 0.7),
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                try:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                except Exception as e:
                    return f"錯誤：{e}", 0, {}, "ollama"
                data = resp.json()
                output = data.get("completion", "未提供回應")
                tokens = self._estimate_tokens(prompt + output)
                cost = self._estimate_cost(prompt, output, {"estimated_tokens": tokens})
                return output, cost, {"estimated_tokens": tokens}, "ollama"

        elif self.backend == "grok":
            url = self.conf["url"]
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.conf['api_key']}",
            }
            payload = {
                "messages": [
                    {"role": "system", "content": "You are a test assistant."},
                    {"role": "user", "content": prompt},
                ],
                "model": self.conf["model"],
                "stream": False,
                "temperature": 0,
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    return f"錯誤：{resp.text}", 0, {}, "grok"
                data = resp.json()
                output = data.get("choices", [{}])[0].get("message", {}).get("content", "未提供回應")
                tokens = self._estimate_tokens(prompt + output)
                cost = self._estimate_cost(prompt, output, {"estimated_tokens": tokens})
                return output, cost, {"estimated_tokens": tokens}, "grok"

        else:
            return f"錯誤：未知的 backend {self.backend}", 0, {}, self.backend