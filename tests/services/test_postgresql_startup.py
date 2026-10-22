"""
Unit tests for src.db.postgresql.PostgreSQLDatabase

涵蓋：
  - startup：連線建立、_verify_required_tables 呼叫
  - _verify_required_tables：全表存在、部分缺失（warning）、全部缺失
  - teardown：engine.dispose 被呼叫
"""

from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy.exc import OperationalError

from src.db.postgresql import PostgreSQLDatabase, _REQUIRED_TABLES


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────


def _make_config(**overrides) -> MagicMock:
    cfg = MagicMock()
    cfg.db_user = "test"
    cfg.db_password = "pass"
    cfg.db_host = "localhost"
    cfg.db_port = 5432
    cfg.db_name = "testdb"
    cfg.echo_sql = False
    cfg.pool_size = 5
    cfg.max_overflow = 10
    cfg.connect_max_attempts = 3
    cfg.connect_retry_interval_seconds = 0
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


# ─────────────────────────────────────────────────────────────
# startup
# ─────────────────────────────────────────────────────────────


class TestPostgreSQLStartup:

    def test_startup_calls_verify_tables(self):
        """startup 成功後，應呼叫 _verify_required_tables（不執行 DDL）"""
        db = PostgreSQLDatabase(_make_config())

        with (
            patch("src.db.postgresql.create_engine") as mock_engine,
            patch("src.db.postgresql.sessionmaker"),
            patch.object(db, "_verify_required_tables") as mock_verify,
        ):
            engine_instance = MagicMock()
            engine_instance.connect.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            engine_instance.connect.return_value.__exit__ = MagicMock(return_value=False)
            engine_instance.url.database = "testdb"
            mock_engine.return_value = engine_instance

            db.startup()

        mock_verify.assert_called_once()

    def test_startup_does_not_call_create_all(self):
        """startup 不應呼叫 Base.metadata.create_all（DDL 禁止在 AI 後端執行）"""
        db = PostgreSQLDatabase(_make_config())

        with (
            patch("src.db.postgresql.create_engine") as mock_engine,
            patch("src.db.postgresql.sessionmaker"),
            patch.object(db, "_verify_required_tables"),
            patch("src.db.postgresql.Base", create=True) as mock_base,
        ):
            engine_instance = MagicMock()
            engine_instance.connect.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            engine_instance.connect.return_value.__exit__ = MagicMock(return_value=False)
            engine_instance.url.database = "testdb"
            mock_engine.return_value = engine_instance

            db.startup()

        # create_all 不應被呼叫
        if hasattr(mock_base, "metadata"):
            mock_base.metadata.create_all.assert_not_called()

    def test_startup_raises_on_connection_failure(self):
        """連線失敗時，startup 應向外拋出例外"""
        db = PostgreSQLDatabase(_make_config())

        with patch(
            "src.db.postgresql.create_engine",
            side_effect=Exception("Connection refused"),
        ):
            with pytest.raises(Exception, match="Connection refused"):
                db.startup()


# ─────────────────────────────────────────────────────────────
# startup：DB 晚起來時重試（daodao#362）
# ─────────────────────────────────────────────────────────────


def _db_down_error() -> OperationalError:
    return OperationalError(
        "SELECT 1",
        {},
        Exception('could not translate host name "pg-dev" to address'),
    )


def _engine_with_connect_results(results: list) -> MagicMock:
    """依序回傳 connect() 的結果：Exception 代表連線失敗，其他代表成功"""
    engine_instance = MagicMock()
    engine_instance.url.database = "testdb"

    def _connect():
        outcome = results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=MagicMock())
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    engine_instance.connect.side_effect = _connect
    return engine_instance


class TestPostgreSQLStartupRetry:

    def test_startup_waits_for_db_that_comes_up_late(self):
        """重開機情境：前兩次 pg-dev 還解析不到，第三次連上 → 啟動成功、不拋錯"""
        db = PostgreSQLDatabase(_make_config(connect_max_attempts=5))
        engine_instance = _engine_with_connect_results(
            [_db_down_error(), _db_down_error(), "ok"]
        )

        with (
            patch("src.db.postgresql.create_engine", return_value=engine_instance),
            patch("src.db.postgresql.sessionmaker"),
            patch.object(db, "_verify_required_tables") as mock_verify,
            patch("src.db.postgresql.time.sleep") as mock_sleep,
        ):
            db.startup()

        assert engine_instance.connect.call_count == 3
        assert mock_sleep.call_count == 2
        mock_verify.assert_called_once()

    def test_startup_gives_up_after_max_attempts(self):
        """DB 一直起不來 → 用完次數後拋出 OperationalError，不會無限等待"""
        db = PostgreSQLDatabase(_make_config(connect_max_attempts=3))
        engine_instance = _engine_with_connect_results([_db_down_error()] * 3)

        with (
            patch("src.db.postgresql.create_engine", return_value=engine_instance),
            patch("src.db.postgresql.sessionmaker"),
            patch.object(db, "_verify_required_tables") as mock_verify,
            patch("src.db.postgresql.time.sleep") as mock_sleep,
        ):
            with pytest.raises(OperationalError):
                db.startup()

        assert engine_instance.connect.call_count == 3
        assert mock_sleep.call_count == 2
        mock_verify.assert_not_called()

    def test_startup_does_not_retry_non_connection_errors(self):
        """非連線類錯誤（例如程式錯誤）不重試，直接拋出"""
        db = PostgreSQLDatabase(_make_config(connect_max_attempts=5))
        engine_instance = _engine_with_connect_results([ValueError("bad config")])

        with (
            patch("src.db.postgresql.create_engine", return_value=engine_instance),
            patch("src.db.postgresql.sessionmaker"),
            patch("src.db.postgresql.time.sleep") as mock_sleep,
        ):
            with pytest.raises(ValueError, match="bad config"):
                db.startup()

        assert engine_instance.connect.call_count == 1
        mock_sleep.assert_not_called()


# ─────────────────────────────────────────────────────────────
# _verify_required_tables
# ─────────────────────────────────────────────────────────────


class TestVerifyRequiredTables:

    def _db_with_engine(self, existing_tables: list) -> PostgreSQLDatabase:
        db = PostgreSQLDatabase(_make_config())
        db.engine = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = existing_tables
        with patch("src.db.postgresql.inspect", return_value=mock_inspector):
            db._verify_required_tables()
        return db

    def test_all_tables_present_no_warning(self, caplog):
        """所有必要資料表存在時，不應記錄 warning"""
        import logging

        with caplog.at_level(logging.WARNING, logger="src.db.postgresql"):
            self._db_with_engine(_REQUIRED_TABLES + ["extra_table"])

        assert "不存在" not in caplog.text

    def test_missing_tables_logs_warning(self, caplog):
        """缺少資料表時，應記錄 warning（不 raise）"""
        import logging

        # 移除第一個必要表來模擬缺失情境
        missing_table = _REQUIRED_TABLES[0]
        existing = _REQUIRED_TABLES[1:]

        with caplog.at_level(logging.WARNING, logger="src.db.postgresql"):
            self._db_with_engine(existing)

        assert missing_table in caplog.text

    def test_all_tables_missing_logs_warning_not_raise(self):
        """所有資料表都缺失時，不應 raise（允許 migration 後補跑）"""
        db = PostgreSQLDatabase(_make_config())
        db.engine = MagicMock()
        mock_inspector = MagicMock()
        mock_inspector.get_table_names.return_value = []

        with patch("src.db.postgresql.inspect", return_value=mock_inspector):
            # 不應拋出任何例外
            db._verify_required_tables()

    def test_required_tables_constant_not_empty(self):
        """_REQUIRED_TABLES 常數不能為空（確保驗證有效）"""
        assert len(_REQUIRED_TABLES) > 0


# ─────────────────────────────────────────────────────────────
# teardown
# ─────────────────────────────────────────────────────────────


class TestPostgreSQLTeardown:

    def test_teardown_disposes_engine(self):
        db = PostgreSQLDatabase(_make_config())
        db.engine = MagicMock()

        db.teardown()

        db.engine.dispose.assert_called_once()

    def test_teardown_does_nothing_without_engine(self):
        db = PostgreSQLDatabase(_make_config())
        db.engine = None

        # 不應 raise
        db.teardown()
