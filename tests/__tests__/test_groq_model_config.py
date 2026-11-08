"""Groq model selection stays usable when only credentials are configured."""

from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic_settings import BaseSettings

from src import config
from src.config import Settings


@pytest.fixture(autouse=True)
def isolate_implicit_dotenv(monkeypatch):
    """Nested settings otherwise read checkout dotenv despite the outer override."""
    for model in vars(config).values():
        if (
            isinstance(model, type)
            and issubclass(model, BaseSettings)
            and model.__module__ == config.__name__
        ):
            monkeypatch.setitem(model.model_config, "env_file", None)


def test_groq_default_uses_available_chat_model():
    with patch.dict("os.environ", {}, clear=True):
        settings = Settings(
            _env_file=None,
            jwt_security="synthetic-jwt-115-for-model-tests",
            api_secret_key="synthetic-api-115-for-model-tests",
        )
    assert settings.llm_backend["groq"].model == "openai/gpt-oss-20b"


def test_groq_api_key_only_keeps_available_model_default():
    with patch.dict("os.environ", {}, clear=True):
        settings = Settings(
            _env_file=None,
            jwt_security="synthetic-jwt-115-for-model-tests",
            api_secret_key="synthetic-api-115-for-model-tests",
            llm_backend={"groq": {"api_key": "test-key"}},
        )
    assert settings.llm_backend["groq"].model == "openai/gpt-oss-20b"
    assert settings.llm_backend["groq"].api_key == "test-key"


def test_explicit_groq_model_override_remains_authoritative():
    with patch.dict(
        "os.environ",
        {"LLM_BACKEND__GROQ__MODEL": "operator-selected-model"},
        clear=True,
    ):
        settings = Settings(
            _env_file=None,
            jwt_security="synthetic-jwt-115-for-model-tests",
            api_secret_key="synthetic-api-115-for-model-tests",
        )
    assert settings.llm_backend["groq"].model == "operator-selected-model"


def test_dev_sample_selects_available_groq_model():
    with patch.dict("os.environ", {}, clear=True):
        settings = Settings(
            _env_file=Path(__file__).resolve().parents[2] / ".env.dev.sample",
            jwt_security="synthetic-jwt-115-for-model-tests",
            api_secret_key="synthetic-api-115-for-model-tests",
        )
    assert settings.llm_backend["groq"].model == "openai/gpt-oss-20b"
