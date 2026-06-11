from dataclasses import dataclass, field
from enum import Enum


@dataclass
class ApprovalRequest:
    id: str
    action: str           # e.g. "send_emails", "send_notifications"
    description: str
    payload: dict
    preview: list[dict] = field(default_factory=list)   # sample items for preview


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    ALLOWED = "allowed"
    DENIED = "denied"
