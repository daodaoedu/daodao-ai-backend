"""Quota traffic must not consume ordinary request connections."""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from src.db.postgresql import PostgreSQLDatabase
from src.config import PostgreSQLSettings


@pytest.fixture
def database(tmp_path):
    url = f"sqlite:///{tmp_path / 'pool.db'}"
    options = dict(pool_size=1, max_overflow=0, pool_timeout=0.05)
    db = PostgreSQLDatabase(MagicMock())
    db.engine = create_engine(url, **options)
    db.quota_engine = create_engine(url, **options)
    db.session_factory = sessionmaker(db.engine)
    db.quota_session_factory = sessionmaker(db.quota_engine)
    try:
        yield db
    finally:
        db.engine.dispose()
        db.quota_engine.dispose()


def test_quota_query_progresses_while_request_connection_is_occupied(database):
    with database.get_session() as request:
        assert request.scalar(text("SELECT 1")) == 1
        with database.get_quota_session() as quota:
            assert quota.scalar(text("SELECT 2")) == 2
    assert database.engine.pool.checkedout() == 0
    assert database.quota_engine.pool.checkedout() == 0


def test_failed_quota_transaction_is_rolled_back_and_connection_reusable(database):
    with database.engine.begin() as connection:
        connection.execute(text("CREATE TABLE usage (tokens integer)"))
    with pytest.raises(RuntimeError, match="failed generation"):
        with database.get_quota_session() as quota:
            quota.execute(text("INSERT INTO usage VALUES (10)"))
            raise RuntimeError("failed generation")
    with database.get_quota_session() as quota:
        assert quota.scalar(text("SELECT COUNT(*) FROM usage")) == 0
    assert database.quota_engine.pool.checkedout() == 0


def test_teardown_closes_idle_connections_in_both_pools(database):
    closed = []
    for label, engine in [
        ("request", database.engine),
        ("quota", database.quota_engine),
    ]:
        event.listen(
            engine, "close", lambda _conn, _record, name=label: closed.append(name)
        )
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    database.teardown()
    assert sorted(closed) == ["quota", "request"]


@pytest.mark.parametrize("size", [0, -1])
def test_quota_pool_rejects_unbounded_or_invalid_size(size):
    with pytest.raises(ValidationError):
        PostgreSQLSettings(_env_file=None, quota_pool_size=size)
