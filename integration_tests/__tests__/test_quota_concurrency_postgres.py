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
def sessions(request):
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
        pool_size=getattr(request, "param", 5),
        max_overflow=0,
        pool_timeout=3,
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

        factory.engine = engine
        yield factory
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.parametrize("kind", ["monthly", "daily"])
def test_same_user_waits_for_committed_usage_before_next_admission(sessions, kind):
    """Once first generation consumes the limit, second must not call provider."""
    if kind == "daily":
        with sessions() as session:
            session.execute(
                text(
                    "UPDATE user_token_quotas SET monthly_token_limit=1000, daily_token_limit=50"
                )
            )
            session.commit()
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


def client(sessions, generate, user_id=42):
    backend = SimpleNamespace(
        backend="test",
        _backend=SimpleNamespace(config={"model": "test"}),
        generate=generate,
    )
    return LoggingLLMClient(
        backend, sessions, context="quota-regression", user_id=str(user_id)
    )


def success():
    return "generated", 0.002, {"input_tokens": 30, "output_tokens": 20}, "test"


@pytest.mark.asyncio
async def test_different_users_provider_stays_on_original_loop(sessions):
    with sessions() as session:
        session.execute(
            text(
                "INSERT INTO user_token_quotas (user_id, monthly_token_limit) VALUES (43,50)"
            )
        )
        session.commit()
    loop = asyncio.get_running_loop()
    both_started = asyncio.Event()
    started = []

    async def generate(prompt):
        assert asyncio.get_running_loop() is loop
        started.append(prompt)
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), 2)
        return success()

    await asyncio.wait_for(
        asyncio.gather(
            client(sessions, generate, 42).generate("one"),
            client(sessions, generate, 43).generate("two"),
        ),
        3,
    )
    assert sorted(started) == ["one", "two"]


@pytest.mark.asyncio
@pytest.mark.parametrize("sessions", [2], indirect=True)
async def test_more_requests_than_pool_connections_progress(sessions):
    with sessions() as session:
        session.execute(
            text(
                "INSERT INTO user_token_quotas (user_id, monthly_token_limit) SELECT generate_series(43,54),50"
            )
        )
        session.commit()
    completed = []
    # A small default executor reproduces the DNS starvation condition without
    # spawning dozens of threads; DB workers must use their own executor.
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=2))

    async def generate(prompt):
        # HTTP DNS and other provider work use the default executor. DB waiting
        # must neither block the event loop nor exhaust that same executor.
        await asyncio.wait_for(asyncio.to_thread(lambda: None), 1)
        await asyncio.sleep(0.02)
        completed.append(prompt)
        return success()

    results = await asyncio.wait_for(
        asyncio.gather(
            *(
                client(sessions, generate, user).generate(str(user))
                for user in range(42, 55)
            )
        ),
        5,
    )
    assert len(results) == len(completed) == 13
    with sessions() as session:
        assert len(list(session.scalars(select(AIQueryLog)))) == 13


@pytest.mark.asyncio
async def test_cancel_active_generation_finishes_provider_cleanup_and_releases_lock(
    sessions,
):
    entered = asyncio.Event()
    cleaned = asyncio.Event()
    waiting = asyncio.Event()

    async def generate(prompt):
        if prompt == "cancel":
            entered.set()
            try:
                await waiting.wait()
            finally:
                await asyncio.sleep(0.02)
                cleaned.set()
        assert cleaned.is_set()
        return success()

    task = asyncio.create_task(client(sessions, generate).generate("cancel"))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 2)
    assert cleaned.is_set()
    await asyncio.wait_for(client(sessions, generate).generate("next"), 2)
    with sessions() as session:
        logs = list(session.scalars(select(AIQueryLog).order_by(AIQueryLog.id)))
    assert [(log.status, log.total_tokens) for log in logs] == [
        ("error", 0),
        ("success", 50),
    ]


@pytest.mark.asyncio
async def test_cancel_waiting_request_never_calls_provider(sessions):
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def generate(prompt):
        calls.append(prompt)
        entered.set()
        await release.wait()
        return success()

    first = asyncio.create_task(client(sessions, generate).generate("first"))
    await asyncio.wait_for(entered.wait(), 2)
    second = asyncio.create_task(client(sessions, generate).generate("cancelled"))
    await asyncio.sleep(0.1)
    second.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(second, 1)
        assert calls == ["first"]
    finally:
        release.set()
        await asyncio.wait_for(first, 2)
    with sessions() as session:
        assert len(list(session.scalars(select(AIQueryLog)))) == 1


@pytest.mark.asyncio
async def test_provider_failure_records_error_and_next_request_progresses(sessions):
    async def generate(prompt):
        if prompt == "fail":
            raise RuntimeError("provider failed")
        return success()

    with pytest.raises(RuntimeError, match="provider failed"):
        await client(sessions, generate).generate("fail")
    await asyncio.wait_for(client(sessions, generate).generate("next"), 2)
    with sessions() as session:
        logs = list(session.scalars(select(AIQueryLog).order_by(AIQueryLog.id)))
    assert [(log.status, log.total_tokens) for log in logs] == [
        ("error", 0),
        ("success", 50),
    ]


@pytest.mark.asyncio
async def test_log_commit_failure_preserves_fail_open_and_releases_lock(
    sessions, monkeypatch
):
    original_commit = Session.commit
    fail_next = True

    def commit(session):
        nonlocal fail_next
        if fail_next:
            fail_next = False
            raise RuntimeError("synthetic commit failure")
        return original_commit(session)

    monkeypatch.setattr(Session, "commit", commit)

    async def generate(_prompt):
        return success()

    assert await client(sessions, generate).generate("unlogged") == success()
    assert (
        await asyncio.wait_for(client(sessions, generate).generate("next"), 2)
        == success()
    )
    with sessions() as session:
        logs = list(session.scalars(select(AIQueryLog)))
    assert [(log.status, log.total_tokens) for log in logs] == [("success", 50)]


@pytest.mark.asyncio
async def test_no_quota_requests_remain_unrestricted(sessions):
    entered = []
    both = asyncio.Event()

    async def generate(prompt):
        entered.append(prompt)
        if len(entered) == 2:
            both.set()
        await asyncio.wait_for(both.wait(), 2)
        return success()

    await asyncio.wait_for(
        asyncio.gather(
            *(client(sessions, generate, 99).generate(str(i)) for i in range(2))
        ),
        3,
    )
    assert len(entered) == 2


@pytest.mark.asyncio
async def test_unexpected_log_construction_failure_is_not_silently_swallowed(sessions):
    async def generate(_prompt):
        return "generated", 0.0, ["malformed usage"], "test"

    with pytest.raises(AttributeError):
        await asyncio.wait_for(client(sessions, generate).generate("bad usage"), 2)

    async def valid(_prompt):
        return success()

    assert (
        await asyncio.wait_for(client(sessions, valid).generate("next"), 2) == success()
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_count", [1, 2])
async def test_cancel_during_admission_error_does_not_leave_unretrieved_future(
    sessions,
    cancel_count,
):
    import gc
    import time

    @contextmanager
    def failed_session():
        time.sleep(0.1)
        raise RuntimeError("synthetic checkout failure")
        yield  # pragma: no cover

    async def generate(_prompt):
        pytest.fail("provider must not run after cancelled admission")

    loop = asyncio.get_running_loop()
    errors = []
    previous = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: errors.append(context))
    try:
        task = asyncio.create_task(client(failed_session, generate).generate("cancel"))
        await asyncio.sleep(0.02)
        task.cancel()
        for _ in range(cancel_count - 1):
            await asyncio.sleep(0.02)
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        del task
        gc.collect()
        await asyncio.sleep(0.02)
        assert errors == []
    finally:
        loop.set_exception_handler(previous)


@pytest.mark.asyncio
async def test_database_error_after_lock_releases_transaction(sessions, monkeypatch):
    original_execute = Session.execute
    fail_next = True

    def execute(session, statement, *args, **kwargs):
        nonlocal fail_next
        if fail_next and "SUM(total_tokens)" in str(statement):
            fail_next = False
            # A genuine PostgreSQL error leaves the transaction aborted and its
            # lock held until cleanup rolls it back, unlike a mocked exception.
            return original_execute(session, text("SELECT 1 / 0"))
        return original_execute(session, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", execute)

    async def generate(_prompt):
        return success()

    from sqlalchemy.exc import DataError

    with pytest.raises(DataError):
        await asyncio.wait_for(client(sessions, generate).generate("db error"), 2)
    assert (
        await asyncio.wait_for(client(sessions, generate).generate("next"), 2)
        == success()
    )


@pytest.mark.asyncio
async def test_usage_timestamp_is_generation_completion_not_lock_transaction_start(
    sessions,
):
    from datetime import datetime, timezone

    completed_at = None

    async def generate(_prompt):
        nonlocal completed_at
        await asyncio.sleep(0.1)
        completed_at = datetime.now(timezone.utc)
        return success()

    await client(sessions, generate).generate("timestamp")
    with sessions() as session:
        log = session.scalars(select(AIQueryLog)).one()
    assert log.created_at >= completed_at
