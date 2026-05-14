import uuid

from sqlalchemy import Boolean, Column, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.sql import func

from src.models.base import Base


class AIQueryLog(Base):
    __tablename__ = "ai_query_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 追蹤同一請求的 correlation ID
    request_id = Column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4, index=True
    )

    # 呼叫的 backend：groq / gemini / openai / anthropic / ollama
    backend = Column(String(50), nullable=False)

    # 呼叫時的 model 名稱（記錄歷史，可能與現在設定不同）
    model_name = Column(String(200), nullable=True)

    # 呼叫來源：insight / rag / recommendation 等
    context = Column(String(100), nullable=True)

    # 觸發呼叫的用戶（users.id），排程 job 為 NULL（刻意不設 FK，保留用戶刪除後的日誌）
    user_id = Column(Integer, nullable=True)

    # Token 計數（input+output = total，做 SUM 時直接用 total）
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)  # 反正規化，加速 SUM 聚合

    # 費用（USD）用 Numeric 防止浮點漂移
    cost_usd = Column(Numeric(12, 6), nullable=True)

    # LLM 呼叫耗時（ms）
    latency_ms = Column(Integer, nullable=True)

    # 狀態：success / error / timeout / rate_limited
    status = Column(String(20), nullable=False, default="success")

    error_message = Column(Text, nullable=True)

    # backend 回傳的完整 usage dict（JSONB 支援彈性查詢）
    usage_detail = Column(JSONB, nullable=True)

    # prompt 字元數（不存 prompt 原文，保護隱私 + 避免大欄位）
    prompt_chars = Column(Integer, nullable=True)

    output_chars = Column(Integer, nullable=True)
    finish_reason = Column(String(50), nullable=True)
    http_status_code = Column(Integer, nullable=True)
    retry_count = Column(Integer, nullable=True)
    is_stream = Column(Boolean, nullable=True)
    service_config_id = Column(Integer, nullable=True)

    # 主要聚合維度：created_at
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_aql_created_at", "created_at"),
        Index("ix_aql_backend_created_at", "backend", "created_at"),
        Index("ix_aql_user_created_at", "user_id", "created_at"),
        Index("ix_aql_context_created_at", "context", "created_at"),
        Index("ix_aql_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<AIQueryLog id={self.id} backend={self.backend}"
            f" context={self.context} status={self.status}>"
        )
