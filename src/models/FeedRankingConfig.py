from sqlalchemy import Boolean, Column, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.sql import func

from src.models.base import Base


class FeedRankingConfig(Base):
    __tablename__ = "feed_ranking_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 版本名稱，供管理介面辨識
    name = Column(String(200), nullable=False)

    # 各訊號權重（對應 feed_ranking.py 的 Score 公式）
    w_social = Column(Numeric(5, 2), nullable=False, default=0.35)
    w_engagement = Column(Numeric(5, 2), nullable=False, default=0.30)
    w_content = Column(Numeric(5, 2), nullable=False, default=0.15)
    w_decay = Column(Numeric(5, 2), nullable=False, default=0.20)

    # 新內容加分：freshness_window_hours 內線性遞減至 0
    w_freshness = Column(Numeric(5, 2), nullable=False, default=0.30)
    freshness_window_hours = Column(Integer, nullable=False, default=72)

    # 精選加分：practices.is_featured 的內容加分；0 表示不影響排序
    w_featured = Column(Numeric(5, 2), nullable=False, default=0.50)

    # 全表最多一筆 is_active=True（由 DB partial unique index 強制）
    is_active = Column(Boolean, nullable=False, default=False)

    notes = Column(Text, nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(TIMESTAMP(timezone=True), onupdate=func.now(), nullable=True)

    __table_args__ = (
        Index(
            "idx_feed_ranking_configs_is_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active IS TRUE"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<FeedRankingConfig id={self.id} name={self.name} active={self.is_active}>"
        )
