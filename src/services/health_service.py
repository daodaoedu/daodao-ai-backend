from sqlalchemy import text
from sqlalchemy.orm import Session

from src.schemas.health import ServiceStatus


def check_database(db: Session) -> ServiceStatus:
    """
    Execute lightweight DB probes and return a ServiceStatus.
    Raises on any DB error — caller is responsible for catching.
    """
    db.execute(text("SELECT 1"))
    db_name = db.execute(text("SELECT current_database()")).scalar()
    pg_version = db.execute(text("SELECT version()")).scalar()
    db_user = db.execute(text("SELECT current_user")).scalar()

    version_num = pg_version.split(" ")[1] if pg_version else "unknown"
    message = f"PostgreSQL {version_num} - DB: {db_name} - User: {db_user}"
    return ServiceStatus(status="healthy", message=message)
