"""Persisted provider failure records must not expose exception text to admins."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.models.AIQueryLog import AIQueryLog
from src.models.UserTokenQuota import UserTokenQuota
from src.schemas.admin.query_log import AIQueryLogDetail, AIQueryLogRead
from src.services.llm.client import LLMClient
from src.services.llm.logging_client import LoggingLLMClient
from tests.routers.__tests__ import test_encouragement_quota as quota_regressions

quota_database = quota_regressions.harness


def _client(database, provider):
    client = LLMClient.__new__(LLMClient)
    client.backend = "openai"
    client._enable_guardrail = True
    client._backend = SimpleNamespace(
        config={"model": "privacy-test-model"}, generate=provider
    )
    return LoggingLLMClient(
        client, database.sessions, context="encouragement", user_id="42"
    )


@pytest.mark.parametrize("has_quota", [False, True])
@pytest.mark.parametrize(
    "private_detail",
    [
        "Incorrect API key sk-SYNTHETIC-237; user=PRIVATE-USER-237",
        "供應商拒絕 key=測試密鑰237；私人日記：今天心情低落🐾",
    ],
)
def test_provider_error_text_is_absent_from_persisted_and_admin_records(
    quota_database, has_quota, private_detail
):
    if has_quota:
        with quota_database.sessions() as session:
            session.add(UserTokenQuota(user_id=42, monthly_token_limit=1000))
            session.commit()

    failure = RuntimeError(private_detail)
    successful_result = (
        "繼續加油！",
        0.002,
        {"input_tokens": 30, "output_tokens": 20},
        "openai",
    )
    provider = AsyncMock(side_effect=[failure, successful_result])
    client = _client(quota_database, provider)

    async def fail_then_succeed():
        with pytest.raises(RuntimeError) as caught:
            await client.generate("安全的閱讀練習")
        assert caught.value is failure
        assert await client.generate("下一次閱讀練習") == successful_result

    asyncio.run(fail_then_succeed())
    assert provider.await_count == 2
    with quota_database.sessions() as session:
        failure_log = session.scalars(
            select(AIQueryLog).where(AIQueryLog.status == "error")
        ).one()
        success_log = session.scalars(
            select(AIQueryLog).where(AIQueryLog.status == "success")
        ).one()
        assert (failure_log.user_id, failure_log.context) == (42, "encouragement")
        assert failure_log.total_tokens == 0
        assert success_log.total_tokens == 50
        assert success_log.error_message is None
        for schema in (AIQueryLogRead, AIQueryLogDetail):
            serialized = schema.model_validate(failure_log).model_dump_json()
            assert private_detail not in serialized
            assert schema.model_validate(failure_log).error_message == "RuntimeError"
        assert failure_log.error_message == "RuntimeError"


def test_cancellation_keeps_safe_marker_and_propagates(quota_database):
    cancellation = asyncio.CancelledError()
    provider = AsyncMock(side_effect=cancellation)
    client = _client(quota_database, provider)

    async def cancel():
        with pytest.raises(asyncio.CancelledError) as caught:
            await client.generate("安全的閱讀練習")
        assert caught.value is cancellation

    asyncio.run(cancel())
    with quota_database.sessions() as session:
        record = session.scalars(select(AIQueryLog)).one()
        assert record.status == "error"
        assert record.error_message == "Generation cancelled"
        assert record.total_tokens == 0
