"""HTTP regressions for encouragement budget checks and attributed usage.

SQLite persists identities, quotas and logs; only PostgreSQL date aggregation is
replaced with an all-time sum over this fresh per-test database.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.dependencies import get_current_user, get_database_postgres, get_llm_client
from src.models.AIQueryLog import AIQueryLog
from src.models.UserTokenQuota import UserTokenQuota
from src.routers.encouragement import router
from src.services import quota_service


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def harness(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, mongo_id TEXT, external_id TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users VALUES (42, 'legacy-mongo-id', '129c0ff4-2c23-4caa-aa19-d00b707faacf'), (43, '123456789012345678901234', '509d319d-5ca2-4d51-a0ab-75f55d004c5c')"
            )
        )
    UserTokenQuota.__table__.create(engine)
    AIQueryLog.__table__.create(engine)

    @contextmanager
    def session_factory():
        with Session(engine) as session:
            yield session

    def usage(session, user_id):
        return session.scalar(
            select(func.coalesce(func.sum(AIQueryLog.total_tokens), 0)).where(
                AIQueryLog.user_id == user_id
            )
        )

    monkeypatch.setattr(quota_service, "get_monthly_usage", usage)
    monkeypatch.setattr(quota_service, "get_daily_usage", usage)
    llm = SimpleNamespace(
        backend="openai",
        _backend=SimpleNamespace(config={"model": "test-model"}),
        generate=AsyncMock(
            return_value=(
                "  繼續加油！  ",
                0.002,
                {"input_tokens": 30, "output_tokens": 20},
                "openai",
            )
        ),
    )
    state = SimpleNamespace(identity="42", llm=llm, sessions=session_factory)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: state.identity
    app.dependency_overrides[get_llm_client] = lambda: llm
    app.dependency_overrides[get_database_postgres] = lambda: SimpleNamespace(
        get_session=session_factory, get_quota_session=session_factory
    )
    # Avoid sharing the module-level IP limit across independent test scenarios.
    from src.middleware.limiter import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    state.client = TestClient(app, raise_server_exceptions=False)
    yield state
    state.client.close()
    engine.dispose()


def _generate(harness):
    return harness.client.post(
        "/api/v1/encouragement/generate",
        json={"practiceTitle": "每日閱讀 A", "note": " 今天讀完一章 "},
    )


def _quota(harness, monthly=1000, daily=None):
    with harness.sessions() as session:
        session.add(
            UserTokenQuota(
                user_id=42, monthly_token_limit=monthly, daily_token_limit=daily
            )
        )
        session.commit()


@pytest.mark.parametrize("kind", ["monthly", "daily"])
def test_exhausted_quota_rejects_before_provider(harness, kind):
    _quota(
        harness,
        monthly=0 if kind == "monthly" else 1000,
        daily=0 if kind == "daily" else None,
    )
    response = _generate(harness)
    assert response.status_code == 429
    harness.llm.generate.assert_not_awaited()
    with harness.sessions() as session:
        assert session.scalar(select(func.count()).select_from(AIQueryLog)) == 0


@pytest.mark.parametrize(
    ("identity", "user_id"),
    [
        ("42", 42),
        ("legacy-mongo-id", 42),
        ("123456789012345678901234", 43),
        ("129c0ff4-2c23-4caa-aa19-d00b707faacf", 42),
    ],
)
def test_success_records_tokens_cost_and_canonical_user(harness, identity, user_id):
    harness.identity = identity
    _quota(harness)
    response = _generate(harness)
    assert response.status_code == 200
    assert response.json() == {"draft": "繼續加油！"}
    harness.llm.generate.assert_awaited_once()
    with harness.sessions() as session:
        log = session.scalars(select(AIQueryLog)).one()
        assert (log.user_id, log.context, log.total_tokens, log.status) == (
            user_id,
            "encouragement",
            50,
            "success",
        )
        assert float(log.cost_usd) == 0.002


def test_recorded_usage_rejects_next_request_at_limit(harness):
    _quota(harness, monthly=50)
    assert _generate(harness).status_code == 200
    assert _generate(harness).status_code == 429
    harness.llm.generate.assert_awaited_once()


@pytest.mark.parametrize(
    "identity",
    [None, "unknown-mongo-id", "999", "2147483648", "999999999999999999999999"],
)
def test_unidentified_user_never_calls_provider(harness, identity):
    harness.identity = identity
    response = _generate(harness)
    assert response.status_code == 401
    harness.llm.generate.assert_not_awaited()


def test_provider_failure_is_logged_and_does_not_return_success(harness):
    harness.llm.generate.side_effect = RuntimeError("test provider failure")
    response = _generate(harness)
    assert response.status_code == 500
    harness.llm.generate.assert_awaited_once()
    with harness.sessions() as session:
        log = session.scalars(select(AIQueryLog)).one()
        assert (log.user_id, log.context, log.status) == (42, "encouragement", "error")
