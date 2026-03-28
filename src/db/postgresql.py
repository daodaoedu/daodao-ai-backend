import logging
from contextlib import contextmanager
from typing import Generator, List, Optional
from urllib.parse import quote_plus


from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import PostgreSQLSettings
from src.db.interface_db import BaseDatabase

logger = logging.getLogger(__name__)

# AI 後端運作所必要的核心資料表，啟動時驗證是否已存在
# Schema 管理由 Alembic migration 負責，此服務不執行 DDL
_REQUIRED_TABLES: List[str] = [
    "users",
    "practices",
    "practice_checkins",
]


class PostgreSQLDatabase(BaseDatabase):
    """PostgreSQL database implementation."""

    def __init__(self, config: PostgreSQLSettings):
        self.config = config
        self.engine: Optional[Engine] = None
        self.session_factory: Optional[sessionmaker] = None

    def startup(self) -> None:
        """Initialize the database connection."""
        try:
            db_password = quote_plus(self.config.db_password)

            db_url = (
                f"postgresql+psycopg2://{self.config.db_user}:{db_password}"
                f"@{self.config.db_host}:{self.config.db_port}/{self.config.db_name}"
            )

            logger.info(
                f"Attempting to connect to PostgreSQL at: {db_url.split('@')[1] if '@' in db_url else 'localhost'}"
            )

            self.engine = create_engine(
                db_url,
                echo=self.config.echo_sql,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                pool_pre_ping=True,  # Verify connections before use
            )

            self.session_factory = sessionmaker(
                bind=self.engine, expire_on_commit=False
            )

            # 驗證連線
            assert self.engine is not None
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.info("Database connection test successful")

            # 驗證必要資料表已存在（唯讀，不執行 DDL）
            # Schema 應由 Alembic migration 管理，AI 後端不負責建表
            self._verify_required_tables()

            logger.info("PostgreSQL database initialized successfully")
            logger.info(f"Database: {self.engine.url.database}")
            logger.info("Database connection established")

        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL database: {e}")
            raise

    def _verify_required_tables(self) -> None:
        """
        驗證必要資料表是否存在，僅做唯讀檢查。
        若缺少資料表，記錄警告但不中斷啟動（允許 migration 後補跑）。
        Schema 管理應透過 Alembic migration，不在此執行 DDL。
        """
        assert self.engine is not None
        inspector = inspect(self.engine)
        existing = set(inspector.get_table_names())

        missing = [t for t in _REQUIRED_TABLES if t not in existing]
        present = [t for t in _REQUIRED_TABLES if t in existing]

        if present:
            logger.info(f"已驗證資料表存在: {', '.join(present)}")

        if missing:
            logger.warning(
                f"以下資料表不存在，請確認 migration 是否已執行: {', '.join(missing)}"
            )

    def teardown(self) -> None:
        """Close the database connection."""
        if self.engine:
            self.engine.dispose()
            logger.info("PostgreSQL database connections closed")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session."""
        if not self.session_factory:
            raise RuntimeError("Database not initialized. Call startup() first.")

        session = self.session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
