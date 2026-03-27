from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship
from sqlalchemy.types import TIMESTAMP

from src.models.base import Base


class PracticeInsight(Base):
    """
    AI 生成的個人成長洞察，每個已完成的 Practice 只有一份。
    排程每日 01:00 掃描 status='completed' 且尚無洞察的 Practice，
    呼叫 LLM 生成後儲存於此表。
    """

    __tablename__ = "practice_insights"

    id = Column(Integer, primary_key=True)

    # 一個 practice 只有一份洞察（unique 確保冪等）
    practice_id = Column(
        Integer,
        ForeignKey("practices.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    content = Column(Text, nullable=False)  # AI 生成的成長洞察
    llm_backend = Column(String(50), nullable=False)  # 使用哪個 LLM
    llm_cost = Column(Float, nullable=True)  # 生成成本（USD）

    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    practice = relationship("Practice", foreign_keys=[practice_id])
    user = relationship("User", foreign_keys=[user_id])
