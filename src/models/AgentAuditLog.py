from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.sql import func

from src.models.base import Base


class AgentAuditLog(Base):
    """Agent 全程稽核記錄（見 agent-security spec「全程 Trace / Audit」/ D15）。

    記錄 LLM 呼叫、tool_call、approval 決策、skill 觸發。
    保留至少 180 天；不得含 email / phone 等 PII 明文。
    """

    __tablename__ = "agent_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 事件類型: "llm_call" | "tool_call" | "approval" | "skill_trigger"
    event_type = Column(String(50), nullable=False)

    thread_id = Column(String(64), nullable=True)
    user_id = Column(String(64), nullable=True)

    # 工具名 / skill 名 / action 名
    subject = Column(String(200), nullable=False)

    # 參數與結果摘要（PII 已遮罩）
    detail = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)

    # approval 事件的決策: "allow" | "deny" | "auto_allow" | "auto_deny"
    decision = Column(String(20), nullable=True)

    summary = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True).with_variant(TIMESTAMP(timezone=True), "postgresql"),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_agent_audit_thread", "thread_id"),
        Index("idx_agent_audit_user_time", "user_id", "created_at"),
    )
