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
    def __init__(self, settings: Settings):
        self.settings = settings

        self.model_name = settings.llm_backend["gemini"].model

        self.client = None
        
        self.timeout = httpx.Timeout(300)
        self.prompt_builder = RAGPromptBuilder()
        self.response_parser = ResponseParser()
    
    async def generate(
        self,
        prompt: str = "",
        **kwargs,
    ) -> str:():
        pass