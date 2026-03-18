"""
Unit tests for src.services.health_service.check_database
"""
from unittest.mock import MagicMock, call

import pytest

from src.services.health_service import check_database


def _make_db(db_name="daodao", version="PostgreSQL 15.3 on x86_64", db_user="daodao_user"):
    """Return a mock Session whose execute().scalar() returns appropriate values."""
    db = MagicMock()
    scalars = iter([db_name, version, db_user])

    def scalar_side_effect():
        return next(scalars)

    db.execute.return_value.scalar.side_effect = scalar_side_effect
    return db


# ─────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────

class TestCheckDatabase:

    def test_returns_healthy_status(self):
        db = _make_db()
        result = check_database(db)
        assert result.status == "healthy"

    def test_message_includes_version_db_and_user(self):
        db = _make_db(db_name="mydb", version="PostgreSQL 14.5 on linux", db_user="admin")
        result = check_database(db)
        assert "14.5" in result.message
        assert "mydb" in result.message
        assert "admin" in result.message

    def test_execute_called_four_times(self):
        """SELECT 1, current_database(), version(), current_user."""
        db = _make_db()
        check_database(db)
        assert db.execute.call_count == 4

    def test_unknown_version_when_pg_version_empty(self):
        db = MagicMock()
        scalars = iter(["mydb", None, "admin"])
        db.execute.return_value.scalar.side_effect = lambda: next(scalars)
        result = check_database(db)
        assert "unknown" in result.message

    def test_raises_on_db_error(self):
        """Service does NOT swallow exceptions — caller handles them."""
        db = MagicMock()
        db.execute.side_effect = Exception("connection refused")
        with pytest.raises(Exception, match="connection refused"):
            check_database(db)
