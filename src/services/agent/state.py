from dataclasses import dataclass, field

from src.services.agent.approval import ApprovalPolicy


@dataclass
class AppState:  # pylint: disable=too-many-instance-attributes
    provider: str = "openrouter"  # current LLM provider
    model_override: str | None = None  # override specific model
    dry_run: bool = True  # default safe: no real actions
    thread_id: str | None = None
    user_id: str | None = None  # 操作者（排程執行時為排程建立者，見 D17）
    tools_used: list[str] = field(default_factory=list)
    approval_pending: bool = False
    approval_policy: ApprovalPolicy = field(default_factory=ApprovalPolicy)
    # citation 來源累積：DB 查詢摘要 / API 端點 / 外部 URL（agent-conversation spec）
    sources: list[str] = field(default_factory=list)
