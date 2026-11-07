"""Real PostgreSQL regression for concurrent generation quota admission.

Explicit integration entrypoint: TEST_DATABASE_URL must point to a disposable
loopback PostgreSQL database. Only a random schema is created and removed.
"""

import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from src.models.AIQueryLog import AIQueryLog
from src.services.llm.logging_client import LoggingLLMClient
from src.services.quota_service import QuotaExceededError


@pytest.fixture
def sessions():
    raw_url = os.environ.get("TEST_DATABASE_URL")
    if not raw_url:
        pytest.fail("TEST_DATABASE_URL is required for quota concurrency regressions")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql" or url.host not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        pytest.fail("Quota regressions require loopback PostgreSQL")
    schema = "quota_test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url,
        connect_args={"options": f"-csearch_path={schema} -ctimezone=UTC"},
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                CREATE TABLE user_token_quotas (
                    id serial PRIMARY KEY, user_id integer NOT NULL,
                    monthly_token_limit integer NOT NULL,
                    daily_token_limit integer, quota_month integer,
                    created_at timestamptz DEFAULT now() NOT NULL,
                    updated_at timestamptz
                );
                INSERT INTO user_token_quotas (user_id, monthly_token_limit)
                VALUES (42, 50);
            """
                )
            )
        AIQueryLog.__table__.create(engine)

        @contextmanager
        def factory():
            with Session(engine) as session:
                yield session

        yield factory
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_same_user_waits_for_committed_usage_before_next_admission(sessions):
    """Once first generation consumes the limit, second must not call provider."""
    first_entered = threading.Event()
    second_entered = threading.Event()
    second_request_started = threading.Event()
    release_first = threading.Event()
    calls = []

    async def generate(prompt):
        calls.append(prompt)
        if prompt == "first":
            first_entered.set()
            assert await asyncio.to_thread(release_first.wait, 5), "release timeout"
        else:
            second_entered.set()
        return "generated", 0.002, {"input_tokens": 30, "output_tokens": 20}, "test"

    backend = SimpleNamespace(
        backend="test",
        _backend=SimpleNamespace(config={"model": "test"}),
        generate=generate,
    )

    def request(prompt):
        client = LoggingLLMClient(
            backend, sessions, context="quota-regression", user_id="42"
        )
        try:
            if prompt == "second":
                second_request_started.set()
            asyncio.run(client.generate(prompt))
            return "success"
        except QuotaExceededError:
            return "quota-rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(request, "first")
        try:
            assert first_entered.wait(5), "first provider never started"
            second = pool.submit(request, "second")
            assert second_request_started.wait(5), "second request never started"
            # Broken admission reaches provider here; fixed admission waits for
            # the first committed log. Release in either case to avoid deadlock.
            second_entered.wait(0.5)
        finally:
            release_first.set()
        outcomes = [first.result(timeout=5), second.result(timeout=5)]

    with sessions() as session:
        logs = list(session.scalars(select(AIQueryLog)))
    assert outcomes == ["success", "quota-rejected"]
    assert calls == ["first"]
    assert [(log.user_id, log.total_tokens, log.status) for log in logs] == [
        (42, 50, "success")
    ]
