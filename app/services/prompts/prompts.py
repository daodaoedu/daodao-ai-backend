import json
import re
from pathlib import Path
from typing import Any, Dict, List

from pydantic import ValidationError


class RAGPromptBuilder:
    """Builder class for creating RAG prompts."""

    def __init__(self):
        """Initialize the prompt builder."""
        self.prompts_dir = Path(__file__).parent # / "prompts"
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load the system prompt from the text file.

        Returns:
            System prompt string
        """
        prompt_file = self.prompts_dir / "rag_system.txt"
        if not prompt_file.exists():
            # Fallback to default prompt if file doesn't exist
            return (
                "你是一位學習教練，請根據使用者的輸入內容，給出「個人化」、「實用」、「具體可行」的學習回饋與建議。"
            )
        return prompt_file.read_text().strip()

    def create_rag_prompt(self, **kwargs) -> str:
        """Create a RAG prompt with query and retrieved chunks.

        Args:
            query: User's question
            chunks: List of retrieved chunks with metadata from OpenSearch

        Returns:
            Formatted prompt string
        """
        try:
            prompt = self.system_prompt_template.format(**kwargs)
        except KeyError as e:
            missing_key = e.args[0]
            raise ValueError(f"Missing variable '{missing_key}' for rag_system.txt prompt formatting")
        return prompt




class ResponseParser:
    """Parser for LLM responses."""

    @staticmethod
    def extract_json_fallback(response: str) -> Dict[str, Any]:
        """Extract JSON from response text as fallback.

        Args:
            response: Raw response text

        Returns:
            Dictionary with extracted content or fallback
        """
        # Try to find JSON in the response
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                # Validate with Pydantic, using defaults for missing fields
                
                return parsed.model_dump()
            except (json.JSONDecodeError, ValidationError):
                pass

        # Final fallback: return response as plain text
        return {
            "answer": response,
            "sources": [],
            "confidence": "low",
        }