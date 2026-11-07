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

from src.logger import AppLogger
from src.models.UserTokenQuota import UserTokenQuota

logger = AppLogger(__name__).get_logger()

DEFAULT_ADMIN_MONTHLY_TOKEN_LIMIT = 100_000


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
                  = DATE_TRUNC('month', statement_timestamp() AT TIME ZONE 'UTC')
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
                  = DATE_TRUNC('day', statement_timestamp() AT TIME ZONE 'UTC')
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


def seed_admin_quotas(db: Session) -> None:
    """
    為所有 admin / superadmin 使用者補建預設 quota（冪等）。
    已有 quota_month IS NULL 記錄者跳過，不覆蓋既有設定。
    """
    from src.models.Role import Role  # noqa: PLC0415
    from src.models.User import User  # noqa: PLC0415

    admin_roles = db.query(Role).filter(Role.name.in_(["admin", "superadmin"])).all()
    role_ids = [r.id for r in admin_roles]
    if not role_ids:
        return

    admin_users = db.query(User).filter(User.role_id.in_(role_ids)).all()
    created = 0
    for user in admin_users:
        exists = (
            db.query(UserTokenQuota)
            .filter(
                UserTokenQuota.user_id == user.id,
                UserTokenQuota.quota_month.is_(None),
            )
            .first()
        )
        if exists:
            continue
        db.add(
            UserTokenQuota(
                user_id=user.id,
                monthly_token_limit=DEFAULT_ADMIN_MONTHLY_TOKEN_LIMIT,
            )
        )
        created += 1

    if created:
        db.commit()
        logger.info(
            f"[seed_admin_quotas] 建立 {created} 筆 admin quota (月限 {DEFAULT_ADMIN_MONTHLY_TOKEN_LIMIT:,} tokens)"
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
