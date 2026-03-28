"""
User token quota enforcement.

Usage:
    try:
        check_user_quota(db, user_id)
    except QuotaExceededError as e:
        raise HTTPException(429, f"Token quota exceeded: {e}")
"""

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.models.UserTokenQuota import UserTokenQuota


class QuotaExceededError(Exception):
    def __init__(self, kind: str, used: int, limit: int):
        self.kind = kind  # "monthly" | "daily"
        self.used = used
        self.limit = limit
        super().__init__(f"{kind} quota exceeded: {used}/{limit} tokens")


def get_monthly_usage(db: Session, user_id: int) -> int:
    """當月已使用 token 數（來自 ai_query_logs）。"""
    row = db.execute(
        text(
            """
            SELECT COALESCE(SUM(total_tokens), 0) AS used
            FROM ai_query_logs
            WHERE user_id = :user_id
              AND DATE_TRUNC('month', created_at AT TIME ZONE 'UTC')
                  = DATE_TRUNC('month', NOW() AT TIME ZONE 'UTC')
            """
        ),
        {"user_id": user_id},
    ).fetchone()
    return int(row.used) if row else 0


def get_daily_usage(db: Session, user_id: int) -> int:
    """今日已使用 token 數（來自 ai_query_logs）。"""
    row = db.execute(
        text(
            """
            SELECT COALESCE(SUM(total_tokens), 0) AS used
            FROM ai_query_logs
            WHERE user_id = :user_id
              AND DATE_TRUNC('day', created_at AT TIME ZONE 'UTC')
                  = DATE_TRUNC('day', NOW() AT TIME ZONE 'UTC')
            """
        ),
        {"user_id": user_id},
    ).fetchone()
    return int(row.used) if row else 0


def get_user_quota(db: Session, user_id: int) -> Optional[UserTokenQuota]:
    """取得使用者的永久預設 quota（quota_month IS NULL）。"""
    return (
        db.query(UserTokenQuota)
        .filter(
            UserTokenQuota.user_id == user_id,
            UserTokenQuota.quota_month.is_(None),
        )
        .first()
    )


def check_user_quota(db: Session, user_id: int) -> None:
    """
    檢查使用者是否超過 token quota。
    - 無設定 quota → 直接 return（不限制）
    - 月用量 >= monthly_token_limit → raise QuotaExceededError("monthly", ...)
    - daily_token_limit 不為 NULL 且 日用量 >= limit → raise QuotaExceededError("daily", ...)
    """
    quota = get_user_quota(db, user_id)
    if quota is None:
        return  # 未設定 quota = 不限制

    monthly_used = get_monthly_usage(db, user_id)
    if monthly_used >= quota.monthly_token_limit:
        raise QuotaExceededError("monthly", monthly_used, quota.monthly_token_limit)

    if quota.daily_token_limit is not None:
        daily_used = get_daily_usage(db, user_id)
        if daily_used >= quota.daily_token_limit:
            raise QuotaExceededError("daily", daily_used, quota.daily_token_limit)
