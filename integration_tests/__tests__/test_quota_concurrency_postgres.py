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
        factory.schema = schema
        yield factory
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def main_sessions(sessions):
    """Exercise actual startup and independent factories against local PostgreSQL."""
    from src.config import PostgreSQLSettings
    from src.db.postgresql import PostgreSQLDatabase

    url = sessions.engine.url
    config = PostgreSQLSettings(
        db_host=url.host,
        db_port=url.port,
        db_user=url.username,
        db_password=url.password,
        # Test-owned UUID schema, passed as a standard libpq connection option.
        db_name=f"{url.database}?options=-csearch_path%3D{sessions.schema}",
        pool_size=2,
        max_overflow=0,
    )
    database = PostgreSQLDatabase(config)
    database.startup()

    @contextmanager
    def factory():
        with database.get_session() as session:
            yield session

    factory.database = database
    try:
        yield factory
    finally:
        database.teardown()


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

    completed_at = None

    async def generate(_prompt):
        nonlocal completed_at
        await asyncio.sleep(0.1)
        with sessions() as session:
            completed_at = session.scalar(text("SELECT clock_timestamp()"))
        return success()

    await client(sessions, generate).generate("timestamp")
    with sessions() as session:
        log = session.scalars(select(AIQueryLog)).one()
    assert log.created_at >= completed_at


@pytest.mark.asyncio
@pytest.mark.parametrize("sessions", [12], indirect=True)
async def test_same_user_waiters_do_not_starve_another_user(sessions):
    with sessions() as session:
        session.execute(
            text(
                "INSERT INTO user_token_quotas (user_id,monthly_token_limit) VALUES (43,50)"
            )
        )
        session.commit()
    owner_entered = asyncio.Event()
    other_entered = asyncio.Event()
    release = asyncio.Event()

    async def generate(prompt):
        if prompt.startswith("owner"):
            owner_entered.set()
            await release.wait()
        else:
            other_entered.set()
        return success()

    owner = asyncio.create_task(client(sessions, generate, 42).generate("owner-first"))
    await asyncio.wait_for(owner_entered.wait(), 2)
    waiters = [
        asyncio.create_task(client(sessions, generate, 42).generate(f"owner-{i}"))
        for i in range(7)
    ]
    await asyncio.sleep(0.15)
    other = asyncio.create_task(client(sessions, generate, 43).generate("other"))
    try:
        await asyncio.wait_for(other_entered.wait(), 1)
        assert not owner.done(), "other user must progress before owner completes"
    finally:
        for task in waiters:
            task.cancel()
        release.set()
        await asyncio.gather(owner, other, *waiters, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("sessions", [16], indirect=True)
@pytest.mark.parametrize("limited", [False, True])
async def test_unrestricted_provider_concurrency_is_not_limited_by_db_workers(
    sessions, limited
):
    if limited:
        with sessions() as session:
            session.execute(
                text(
                    "INSERT INTO user_token_quotas (user_id,monthly_token_limit) SELECT generate_series(43,53),50"
                )
            )
            session.commit()
    started = set()
    all_entered = asyncio.Event()

    async def generate(prompt):
        started.add(prompt)
        if len(started) == 12:
            all_entered.set()
        await asyncio.wait_for(all_entered.wait(), 1)
        return success()

    await asyncio.wait_for(
        asyncio.gather(
            *(
                client(sessions, generate, 42 + i if limited else 99).generate(str(i))
                for i in range(12)
            )
        ),
        3,
    )
    assert len(started) == 12


@pytest.mark.asyncio
@pytest.mark.parametrize("sessions", [1], indirect=True)
async def test_playground_releases_read_session_before_generation(
    sessions, monkeypatch
):
    from src.models.LLMModel import LLMModel
    from src.routers.admin import playground
    from src.schemas.admin.playground import PlaygroundChatRequest

    LLMModel.__table__.create(sessions.engine)
    with sessions() as session:
        session.add(LLMModel(id=1, provider="test", model_name="test-model"))
        session.commit()
    calls = []

    async def generate(_prompt, **_kwargs):
        calls.append("provider")
        return success()

    backend = SimpleNamespace(
        backend="test",
        _backend=SimpleNamespace(config={"model": "test-model"}),
        generate=generate,
    )
    monkeypatch.setattr(playground, "LLMClient", lambda *_args: backend)
    with sessions() as session:
        result = await asyncio.wait_for(
            playground.playground_chat.__wrapped__(
                body=PlaygroundChatRequest(model_id=1, message="hello"),
                admin=SimpleNamespace(id=42),
                db=session,
                database=SimpleNamespace(
                    get_session=sessions, get_quota_session=sessions
                ),
                settings=None,
            ),
            2,
        )
    assert calls == ["provider"]
    assert result["data"]["model_used"] == "test/test-model"


@pytest.mark.asyncio
@pytest.mark.parametrize("sessions", [1], indirect=True)
@pytest.mark.parametrize("save", [False, True])
async def test_playground_insight_keeps_profile_and_optional_save_after_read_close(
    sessions, monkeypatch, save
):
    from sqlalchemy import ARRAY, Enum
    from sqlalchemy.schema import CreateTable
    from src.models.BasicInfo import BasicInfo
    from src.models.LLMModel import LLMModel
    from src.models.Practice import Practice
    from src.models.PracticeCheckIn import PracticeCheckIn
    from src.models.User import User
    from src.routers.admin import playground
    from src.schemas.admin.playground import PlaygroundInsightRequest

    # Use the actual ORM column definitions; foreign keys to unrelated product
    # tables are omitted only inside this disposable minimal schema.
    with sessions.engine.begin() as connection:
        for table in [
            LLMModel.__table__,
            BasicInfo.__table__,
            User.__table__,
            Practice.__table__,
            PracticeCheckIn.__table__,
        ]:
            for column in table.columns:
                column_type = (
                    column.type.item_type
                    if isinstance(column.type, ARRAY)
                    else column.type
                )
                if isinstance(column_type, Enum):
                    column_type.create(connection, checkfirst=True)
            connection.execute(CreateTable(table, include_foreign_key_constraints=[]))
    with sessions.engine.begin() as connection:
        connection.execute(
            text(
                """
            CREATE TABLE user_preferences (user_id integer, preference_option_id integer, is_selected boolean);
            CREATE TABLE preference_options (id integer, preference_type_id integer, name text, display_order integer);
            CREATE TABLE preference_types (id integer, name text, display_order integer);
        """
            )
        )
    with sessions() as session:
        session.execute(
            LLMModel.__table__.insert().values(
                id=1, provider="test", model_name="test-model"
            )
        )
        session.execute(
            BasicInfo.__table__.insert().values(
                id=1, self_introduction="  QA profile  "
            )
        )
        session.execute(
            User.__table__.insert().values(
                id=42,
                mongo_id="qa42",
                role_id=1,
                nickname="QA",
                basic_info_id=1,
                tag_list=["reading"],
            )
        )
        session.execute(
            Practice.__table__.insert().values(
                id=10, user_id=42, title="QA reading", insight="old insight"
            )
        )
        session.commit()

    async def generate(prompt, **_kwargs):
        assert "QA profile" in prompt
        return (
            "<think>reason</think>New insight",
            0.002,
            {"input_tokens": 30, "output_tokens": 20},
            "test",
        )

    backend = SimpleNamespace(
        backend="test",
        _backend=SimpleNamespace(config={"model": "test-model"}),
        generate=generate,
    )
    monkeypatch.setattr(playground, "LLMClient", lambda *_args: backend)
    with sessions() as session:
        result = await asyncio.wait_for(
            playground.playground_insight.__wrapped__(
                body=PlaygroundInsightRequest(
                    model_id=1,
                    practice_id=10,
                    save=save,
                    system_prompt_override="Test prompt",
                ),
                admin=SimpleNamespace(id=42),
                db=session,
                database=SimpleNamespace(
                    get_session=sessions, get_quota_session=sessions
                ),
                settings=None,
            ),
            2,
        )
    data = result["data"]
    assert data["insight"] == "New insight"
    assert data["thinking"] == "reason"
    assert data["model_used"] == "test/test-model"
    assert data["user_profile_used"]["self_introduction"] == "QA profile"
    assert data["user_profile_used"]["tag_list"] == ["reading"]
    assert data["saved"] is save
    with sessions() as session:
        assert session.get(Practice, 10).insight == (
            "New insight" if save else "old insight"
        )


@pytest.mark.asyncio
async def test_malformed_provider_output_still_releases_admission_guard(sessions):
    opened = []

    @contextmanager
    def tracked_sessions():
        with sessions() as session:
            opened.append(session)
            yield session

    async def generate(prompt):
        if prompt == "malformed":
            return None, 0.002, {"input_tokens": 30, "output_tokens": 20}, "test"
        return success()

    try:
        with pytest.raises(TypeError) as failure:
            await client(tracked_sessions, generate).generate("malformed")
        # Error reporting can retain the traceback and its guard; cleanup must
        # be explicit rather than depend on generator garbage collection.
        assert failure.type is TypeError
        assert (
            await asyncio.wait_for(
                client(tracked_sessions, generate).generate("next"), 1
            )
            == success()
        )
    finally:
        # Keep the RED baseline safe: its leaked guard must not leave a lock or
        # connection behind and block random-schema cleanup after test failure.
        for session in opened:
            session.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("sessions", [2], indirect=True)
async def test_encouragement_identity_lookup_keeps_loop_live_when_pool_is_full(
    sessions,
    main_sessions,
):
    import inspect
    from src.routers.encouragement import generate_encouragement
    from src.schemas.encouragement import GenerateEncouragementRequest

    with sessions() as session:
        session.execute(
            text(
                "CREATE TABLE users (id integer PRIMARY KEY,mongo_id text,external_id text); INSERT INTO users VALUES (99,'qa99','external99'); INSERT INTO user_token_quotas (user_id,monthly_token_limit) VALUES (43,50)"
            )
        )
        session.commit()
    both_started = asyncio.Event()
    release = asyncio.Event()
    heartbeat = asyncio.Event()
    owners_started = []

    async def generate(prompt):
        if prompt.startswith("owner"):
            owners_started.append(prompt)
            if len(owners_started) == 2:
                both_started.set()
            await release.wait()
        return success()

    owners = [
        asyncio.create_task(
            client(main_sessions.database.get_quota_session, generate, u).generate(
                f"owner-{u}"
            )
        )
        for u in [42, 43]
    ]
    await asyncio.wait_for(both_started.wait(), 2)

    async def release_on_loop():
        await asyncio.sleep(0.05)
        with main_sessions.database.get_session() as db:
            assert db.scalar(text("SELECT 1")) == 1
        assert main_sessions.database.engine is not main_sessions.database.quota_engine
        heartbeat.set()
        release.set()

    beat = asyncio.create_task(release_on_loop())
    backend = SimpleNamespace(
        backend="test",
        _backend=SimpleNamespace(config={"model": "test"}),
        generate=generate,
    )
    try:
        response = await asyncio.wait_for(
            inspect.unwrap(generate_encouragement)(
                request=None,
                current_user="99",
                req=GenerateEncouragementRequest(practiceTitle="reading"),
                llm_client=backend,
                database=main_sessions.database,
            ),
            2,
        )
        assert response.draft == "generated"
        await asyncio.wait_for(beat, 1)
        assert heartbeat.is_set()
    finally:
        release.set()
        await asyncio.gather(*owners, beat, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("sessions", [2], indirect=True)
async def test_scheduler_provider_bypasses_saturated_admission_executor(
    sessions, main_sessions
):
    with sessions() as session:
        session.execute(
            text(
                "INSERT INTO user_token_quotas (user_id,monthly_token_limit) VALUES (43,50)"
            )
        )
        session.commit()
    release = asyncio.Event()
    owners_ready = asyncio.Event()
    scheduler_started = asyncio.Event()
    started = []

    async def generate(prompt):
        if prompt.startswith("owner"):
            started.append(prompt)
            if len(started) == 2:
                owners_ready.set()
            await release.wait()
        elif prompt == "scheduler":
            scheduler_started.set()
        return success()

    entered = threading.Event()
    count_lock = threading.Lock()
    checkout_count = 0

    blocking_engine = create_engine(
        sessions.engine.url,
        connect_args={"options": f"-csearch_path={sessions.schema} -ctimezone=UTC"},
        pool_size=8,
        max_overflow=0,
        pool_timeout=1,
    )

    @contextmanager
    def blocked_sessions():
        nonlocal checkout_count
        with Session(blocking_engine) as session:
            with count_lock:
                checkout_count += 1
                initial_lookup = checkout_count <= 8
                if checkout_count >= 8:
                    entered.set()
            if initial_lookup:
                session.execute(text("SELECT pg_sleep(1)"))
            yield session

    owners = [
        asyncio.create_task(
            client(main_sessions.database.get_quota_session, generate, u).generate(
                f"owner-{u}"
            )
        )
        for u in [42, 43]
    ]
    await asyncio.wait_for(owners_ready.wait(), 2)
    blocked = [
        asyncio.create_task(
            client(blocked_sessions, generate, 99).generate(f"blocked-{i}")
        )
        for i in range(8)
    ]
    assert await asyncio.to_thread(entered.wait, 2)
    backend = SimpleNamespace(
        backend="test",
        _backend=SimpleNamespace(config={"model": "test"}),
        generate=generate,
    )
    scheduler = asyncio.create_task(
        LoggingLLMClient(backend, main_sessions, user_id=None).generate("scheduler")
    )
    try:
        await asyncio.wait_for(scheduler_started.wait(), 0.5)
        await asyncio.wait_for(scheduler, 0.5)
        assert not release.is_set()
        assert all(not task.done() for task in blocked)
    finally:
        release.set()
        await asyncio.gather(*owners, *blocked, scheduler, return_exceptions=True)
        blocking_engine.dispose()


@pytest.mark.asyncio
async def test_usage_attribution_uses_database_clock_despite_application_clock_skew(
    sessions, monkeypatch
):
    from datetime import datetime, timezone
    from src.services.llm import logging_client as logging_module

    class SkewedClock:
        @staticmethod
        def now(_timezone):
            return datetime(1970, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(logging_module, "datetime", SkewedClock, raising=False)

    async def generate(_prompt):
        return success()

    await client(sessions, generate).generate("clock")
    with pytest.raises(QuotaExceededError):
        await client(sessions, generate).generate("must be rejected in current month")


@pytest.mark.asyncio
@pytest.mark.parametrize("sessions", [2], indirect=True)
@pytest.mark.parametrize("waiter_count", [0, 8])
async def test_no_quota_user_progresses_and_logs_while_guard_pool_is_saturated(
    sessions, main_sessions, waiter_count
):
    import inspect
    from src.routers.encouragement import generate_encouragement
    from src.schemas.encouragement import GenerateEncouragementRequest

    database = main_sessions.database
    with database.get_session() as db:
        db.execute(
            text(
                "CREATE TABLE users (id integer PRIMARY KEY,mongo_id text,external_id text); INSERT INTO users VALUES (42,'qa42','external42'),(99,'qa99','external99'); INSERT INTO user_token_quotas (user_id,monthly_token_limit) VALUES (43,50)"
            )
        )
        db.commit()
    ready = asyncio.Event()
    release = asyncio.Event()
    owners_started = []
    unlimited_started = asyncio.Event()

    async def owner_provider(prompt):
        owners_started.append(prompt)
        if len(owners_started) == 2:
            ready.set()
        await release.wait()
        return success()

    async def unlimited_provider(_prompt):
        unlimited_started.set()
        return success()

    async def waiter_provider(_prompt):
        pytest.fail(
            "configured waiter must not call provider while owner holds admission"
        )

    def backend(generate):
        return SimpleNamespace(
            backend="test",
            _backend=SimpleNamespace(config={"model": "test"}),
            generate=generate,
        )

    async def route(identity, generate):
        return await inspect.unwrap(generate_encouragement)(
            request=None,
            current_user=identity,
            req=GenerateEncouragementRequest(practiceTitle="reading"),
            llm_client=backend(generate),
            database=database,
        )

    owners = [
        asyncio.create_task(
            client(database.get_quota_session, owner_provider, u).generate(str(u))
        )
        for u in [42, 43]
    ]
    await asyncio.wait_for(ready.wait(), 2)
    waiters = [
        asyncio.create_task(route("42", waiter_provider)) for _ in range(waiter_count)
    ]
    await asyncio.sleep(0.1)
    try:
        result = await asyncio.wait_for(route("99", unlimited_provider), 1)
        assert result.draft == "generated"
        assert unlimited_started.is_set()
        assert all(not task.done() for task in owners)
        assert all(not task.done() for task in waiters)
        with database.get_session() as db:
            log = db.scalars(select(AIQueryLog).where(AIQueryLog.user_id == 99)).one()
            assert (log.status, log.total_tokens, log.context) == (
                "success",
                50,
                "encouragement",
            )
    finally:
        for task in waiters:
            task.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)
        release.set()
        await asyncio.gather(*owners, return_exceptions=True)
