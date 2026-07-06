import re
from typing import Optional

from sqlalchemy.orm import Session

from src.logger import AppLogger
from src.models.AgentAuditLog import AgentAuditLog

logger = AppLogger(__name__).get_logger()

# PII 遮罩：audit 記錄不得含 email / phone 明文（agent-security spec）。
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?886[-\s]?|0)9\d{2}[-\s]?\d{3}[-\s]?\d{3}(?!\d)")


def mask_pii(value: str) -> str:
    """遮罩字串中的 email 與台灣手機號碼。"""
    value = _EMAIL_RE.sub("[email]", value)
    return _PHONE_RE.sub("[phone]", value)


def _mask_detail(detail: Optional[dict]) -> Optional[dict]:
    if detail is None:
        return None

    def _walk(node):
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(v) for v in node]
        if isinstance(node, str):
            return mask_pii(node)
        return node

    return _walk(detail)


def log_audit_event(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    session: Session,
    event_type: str,
    subject: str,
    thread_id: Optional[str] = None,
    user_id: Optional[str] = None,
    detail: Optional[dict] = None,
    decision: Optional[str] = None,
    summary: Optional[str] = None,
) -> AgentAuditLog:
    """寫入一筆 audit 記錄；PII 於寫入前遮罩。呼叫端負責 commit。"""
    record = AgentAuditLog(
        event_type=event_type,
        subject=subject,
        thread_id=thread_id,
        user_id=user_id,
        detail=_mask_detail(detail),
        decision=decision,
        summary=mask_pii(summary) if summary else None,
    )
    session.add(record)
    return record
