"""Groq model selection stays usable when only credentials are configured."""

from pathlib import Path
from unittest.mock import patch

from src.config import Settings


def test_groq_default_uses_available_chat_model():
    with patch.dict("os.environ", {}, clear=True):
        settings = Settings(_env_file=None)
    assert settings.llm_backend["groq"].model == "openai/gpt-oss-20b"


def test_groq_api_key_only_keeps_available_model_default():
    with patch.dict("os.environ", {}, clear=True):
        settings = Settings(
            _env_file=None, llm_backend={"groq": {"api_key": "test-key"}}
        )
    assert settings.llm_backend["groq"].model == "openai/gpt-oss-20b"
    assert settings.llm_backend["groq"].api_key == "test-key"


def test_explicit_groq_model_override_remains_authoritative():
    with patch.dict(
        "os.environ",
        {"LLM_BACKEND__GROQ__MODEL": "operator-selected-model"},
        clear=True,
    ):
        settings = Settings(_env_file=None)
    assert settings.llm_backend["groq"].model == "operator-selected-model"


def test_dev_sample_selects_available_groq_model():
    with patch.dict("os.environ", {}, clear=True):
        settings = Settings(
            _env_file=Path(__file__).resolve().parents[2] / ".env.dev.sample"
        )
    assert settings.llm_backend["groq"].model == "openai/gpt-oss-20b"
