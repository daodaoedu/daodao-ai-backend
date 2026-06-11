from sqlalchemy.orm import Session
from sqlalchemy import text

_SCHEMA_SUMMARY: dict = {
    "practices": {
        "columns": [
            "id", "user_id", "title", "description", "status",
            "goal", "start_date", "end_date", "insight",
            "created_at", "updated_at", "deleted_at",
        ],
        "notes": "status: active | completed | archived. Soft-delete via deleted_at.",
    },
    "practice_checkins": {
        "columns": [
            "id", "practice_id", "user_id", "note", "mood",
            "created_at", "updated_at", "deleted_at",
        ],
        "notes": "mood: integer 1-5. Soft-delete via deleted_at.",
    },
    "users": {
        "columns": [
            "id", "nickname", "email", "mongo_id", "external_id", "role_id",
            "personal_slogan", "professional_field", "custom_position",
            "education_stage", "tag_list", "birth_date", "created_at", "updated_at",
        ],
        "notes": "Primary key is numeric id. mongo_id stores legacy MongoDB ObjectId.",
    },
    "reactions": {
        "columns": ["id", "user_id", "target_type", "target_id", "reaction_type", "created_at"],
        "notes": "target_type: 'practice' | 'checkin' | 'comment'.",
    },
    "comments": {
        "columns": [
            "id", "user_id", "target_type", "target_id", "content",
            "created_at", "updated_at", "deleted_at",
        ],
        "notes": "Soft-delete via deleted_at.",
    },
    "follows": {
        "columns": ["id", "follower_id", "followee_id", "created_at"],
        "notes": "follower_id follows followee_id.",
    },
    "email_logs": {
        "columns": [
            "id", "user_id", "email_type", "subject", "to_email",
            "status", "sent_at", "created_at",
        ],
        "notes": "status: pending | sent | failed.",
    },
    "notifications": {
        "columns": ["id", "user_id", "type", "content", "is_read", "created_at"],
        "notes": "is_read: boolean.",
    },
}


async def query_prod_db(sql: str, db_session: Session) -> list[dict]:
    """Execute read-only SQL against prod DB. Raises if not a SELECT statement."""
    normalized = sql.strip().lstrip(";").strip().upper()
    if not normalized.startswith("SELECT") and not normalized.startswith("WITH"):
        raise ValueError(
            "Only SELECT (and WITH ... SELECT) queries are permitted on the production DB."
        )

    result = db_session.execute(text(sql))
    columns = list(result.keys())
    rows = result.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def describe_schema(table: str | None = None) -> dict:
    """Return schema summary for the given table or all tables."""
    if table is not None:
        if table not in _SCHEMA_SUMMARY:
            raise ValueError(
                f"Unknown table: '{table}'. Available: {list(_SCHEMA_SUMMARY.keys())}"
            )
        return {table: _SCHEMA_SUMMARY[table]}
    return _SCHEMA_SUMMARY
