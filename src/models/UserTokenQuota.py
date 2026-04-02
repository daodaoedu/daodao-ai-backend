from sqlalchemy import Column, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.sql import func

from src.models.base import Base


class UserTokenQuota(Base):
    __tablename__ = "user_token_quotas"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # FK to users.id
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 每月 token 上限（input + output 加總）
    monthly_token_limit = Column(Integer, nullable=False, default=100000)

    # 每日 token 上限；NULL = 不設每日上限
    daily_token_limit = Column(Integer, nullable=True)

    # 適用月份：YYYYMM 整數，如 202603；NULL = 用戶永久預設值
    quota_month = Column(Integer, nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "quota_month", name="uq_user_token_quotas_user_month"
        ),
        Index("ix_user_token_quotas_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserTokenQuota id={self.id} user_id={self.user_id}"
            f" limit={self.monthly_token_limit} month={self.quota_month}>"
        )
