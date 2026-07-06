from dataclasses import dataclass, field
from enum import Enum


@dataclass
class ApprovalRequest:
    id: str
    action: str  # e.g. "send_emails", "send_notifications"
    description: str
    payload: dict
    preview: list[dict] = field(default_factory=list)  # sample items for preview


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    ALLOWED = "allowed"
    DENIED = "denied"


class ApprovalMode(str, Enum):
    """審批模式（見 agent-approval spec「審批雙模式」）。

    - NORMAL: 所有寫入型 action 逐一推 approval_request
    - AUTO: allowlist 直接放行、denylist 一律拒絕、其餘仍審批（排程用）
    """

    NORMAL = "normal"
    AUTO = "auto"


class ActionDecision(str, Enum):
    ALLOW = "allow"  # 直接執行，不推審批
    DENY = "deny"  # 一律拒絕
    ASK = "ask"  # 推 approval_request 等待人工


@dataclass(frozen=True)
class ApprovalPolicy:
    """allowlist / denylist 由設定層管理（config > db > env，見 D12/D13）。"""

    mode: ApprovalMode = ApprovalMode.NORMAL
    allowlist: frozenset[str] = frozenset()
    denylist: frozenset[str] = frozenset()

    def resolve(self, action: str) -> ActionDecision:
        """依模式與清單決定 action 處置。denylist 恆勝，不可被 auto 覆蓋。"""
        if action in self.denylist:
            return ActionDecision.DENY
        if self.mode is ApprovalMode.AUTO and action in self.allowlist:
            return ActionDecision.ALLOW
        return ActionDecision.ASK
