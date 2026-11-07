"""HTTP regressions: partial provider output must never become a successful summary."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.config import get_settings
from src.dependencies import get_current_user, require_service_caller
from src.routers import cohort_summary

COMPLETE = "大家持續寫下學習紀錄。\n\n參與者 1 找到了練習方向。\n\n帶領人可以繼續鼓勵彼此交流。"
PARTIAL = "參與者帶著「很"
PAYLOAD = {
    "cohort": {"name": "QA 完整摘要", "phase": "in_progress"},
    "entries": [{"participant": "參與者 1", "text": "今天寫了三行學習紀錄"}],
}


@pytest.fixture
def http_client():
    """Keep the real HTTP route and dependency boundary; no provider/DB requests."""
    app = FastAPI()
    app.include_router(cohort_summary.router, prefix="/api")
    app.state.limiter = cohort_summary.limiter
    settings = MagicMock()
    settings.insight.llm_backend = "gemini"
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_user] = lambda: "42"
    app.dependency_overrides[require_service_caller] = lambda: "service:daodao-server"
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def provider_client(backend="gemini", output=COMPLETE, finish_reason="stop"):
    """Model the provider boundary with real completion metadata and synthetic content."""
    client = MagicMock()
    client.backend = backend
    client.model = (
        "gemini-3-flash-preview" if backend == "gemini" else "configured-model"
    )
    usage = {"input_tokens": 562, "output_tokens": 43}
    if finish_reason is not None:
        usage["finish_reason"] = finish_reason
    client.generate = AsyncMock(return_value=(output, 0.0, usage, backend))
    return client


def generate(http_client, fake, own=True):
    """Exercise the endpoint in own-key or platform mode without replacing its response."""
    payload = (
        {**PAYLOAD, "provider": fake.backend, "apiKey": "synthetic-qa-key"}
        if own
        else PAYLOAD
    )
    with patch.object(cohort_summary, "LLMClient") as factory:
        factory.with_credentials.return_value = fake
        factory.return_value = fake
        return http_client.post("/api/v1/cohort-summary/generate", json=payload)


def test_nonempty_gemini_max_tokens_is_not_a_successful_summary(http_client):
    """Live regression: provider returned text but ended because token budget was exhausted."""
    fake = provider_client(output=PARTIAL, finish_reason="max_tokens")
    response = generate(http_client, fake)
    assert response.status_code == 502
    assert "未完整產生" in response.json()["detail"]
    assert "summary" not in response.json()
    assert PARTIAL not in response.text
    assert fake.generate.await_count == 1


@pytest.mark.parametrize(
    "finish_reason",
    [
        "MAX_TOKENS",
        "FinishReason.MAX_TOKENS",
        "length",
        "max_output_tokens",
        "incomplete",
    ],
)
def test_explicit_incomplete_output_is_rejected_for_other_providers(
    http_client, finish_reason
):
    fake = provider_client(
        backend="openai", output=PARTIAL, finish_reason=finish_reason
    )
    response = generate(http_client, fake)
    assert response.status_code == 502
    assert PARTIAL not in response.text
    assert "summary" not in response.json()
    assert fake.generate.await_count == 1


@pytest.mark.parametrize("finish_reason", [None, "", "safety", "recitation", "unknown"])
def test_gemini_without_normal_stop_is_not_claimed_complete(http_client, finish_reason):
    fake = provider_client(output=PARTIAL, finish_reason=finish_reason)
    response = generate(http_client, fake)
    assert response.status_code == 502
    assert "未完整產生" in response.json()["detail"]
    assert PARTIAL not in response.text
    assert fake.generate.await_count == 1


@pytest.mark.parametrize("own", [True, False])
def test_complete_gemini_summary_is_returned_with_configured_model(http_client, own):
    fake = provider_client(finish_reason="stop")
    response = generate(http_client, fake, own=own)
    assert response.status_code == 200
    assert response.json()["summary"] == COMPLETE
    assert response.json()["provider"] == "gemini"
    assert response.json()["model"] == "gemini-3-flash-preview"
    assert response.json()["usage"]["finish_reason"] == "stop"
    assert fake.generate.await_count == 1
    assert fake.generate.call_args.kwargs["max_tokens"] == 8192


@pytest.mark.parametrize(
    ("backend", "finish_reason"),
    [("openai", "completed"), ("groq", "stop"), ("anthropic", "end_turn")],
)
def test_other_providers_keep_normal_completion_and_existing_budget(
    http_client, backend, finish_reason
):
    fake = provider_client(backend=backend, finish_reason=finish_reason)
    response = generate(http_client, fake)
    assert response.status_code == 200
    assert response.json()["summary"] == COMPLETE
    assert response.json()["provider"] == backend
    assert fake.generate.await_count == 1
    assert fake.generate.call_args.kwargs["max_tokens"] == 1200


@pytest.mark.parametrize("output", ["  ", "未提供回應"])
def test_empty_normal_stop_does_not_become_a_summary(http_client, output):
    fake = provider_client(output=output, finish_reason="stop")
    response = generate(http_client, fake)
    assert response.status_code == 502
    assert "AI 沒有回傳摘要內容" in response.json()["detail"]
    assert "summary" not in response.json()


def test_provider_failure_is_not_retried_or_exposed_as_partial_success(http_client):
    fake = provider_client()
    fake.generate.side_effect = RuntimeError(
        "private provider details synthetic-qa-key"
    )
    response = generate(http_client, fake)
    assert response.status_code == 502
    assert "summary" not in response.json()
    assert "synthetic-qa-key" not in response.text
    assert "private provider details" not in response.text
    assert fake.generate.await_count == 1
