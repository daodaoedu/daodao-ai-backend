"""
Trace / Audit tests (12.5): 記錄寫入、PII 遮罩、依 user/時間查詢。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.AgentAuditLog import AgentAuditLog
from src.models.base import Base
from src.services.agent.audit import log_audit_event, mask_pii
from src.services.agent.scheduling import (
    SchedulePrincipal,
    SchedulePrincipalError,
    build_schedule_state,
    validate_schedule_execution,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    AgentAuditLog.__table__.create(engine)
    factory = sessionmaker(bind=engine)
    sess = factory()
    yield sess
    sess.close()


class TestPiiMasking:

    def test_masks_email(self):
        assert "user@example.com" not in mask_pii("寄給 user@example.com 了")

    def test_masks_taiwan_mobile(self):
        assert "0912345678" not in mask_pii("電話 0912345678")

    def test_plain_text_unchanged(self):
        assert mask_pii("查詢了 42 筆 practices") == "查詢了 42 筆 practices"


class TestAuditLog:

    def test_tool_call_recorded_with_context(self, session):
        log_audit_event(
            session,
            event_type="tool_call",
            subject="query_db",
            thread_id="t-1",
            user_id="u-1",
            detail={"sql": "SELECT count(*) FROM practices"},
        )
        session.commit()

        row = session.query(AgentAuditLog).one()
        assert row.event_type == "tool_call"
        assert row.thread_id == "t-1"
        assert row.user_id == "u-1"
        assert row.created_at is not None

    def test_pii_masked_in_detail_and_summary(self, session):
        log_audit_event(
            session,
            event_type="tool_call",
            subject="send_email",
            detail={"recipients": ["a@b.tw", {"phone": "0912-345-678"}]},
            summary="sent to a@b.tw",
        )
        session.commit()

        row = session.query(AgentAuditLog).one()
        assert "a@b.tw" not in str(row.detail)
        assert "0912" not in str(row.detail)
        assert "a@b.tw" not in row.summary

    def test_queryable_by_user(self, session):
        for user in ("u-1", "u-1", "u-2"):
            log_audit_event(session, event_type="llm_call", subject="generate", user_id=user)
        session.commit()

        count = session.query(AgentAuditLog).filter_by(user_id="u-1").count()
        assert count == 2

    def test_approval_decision_recorded(self, session):
        log_audit_event(
            session,
            event_type="approval",
            subject="send_emails",
            decision="auto_allow",
        )
        session.commit()
        assert session.query(AgentAuditLog).one().decision == "auto_allow"


class TestScheduleIdentity:

    def test_schedule_runs_as_creator(self):
        principal = SchedulePrincipal("admin-9", creator_is_admin=True, dry_run=False)
        state = build_schedule_state(principal, allowlist=frozenset({"send_emails"}))

        assert state.user_id == "admin-9"
        assert state.dry_run is False
        assert state.approval_policy.mode.value == "auto"
        assert state.approval_policy.resolve("send_emails").value == "allow"

    def test_creator_without_admin_disables_write_schedule(self):
        principal = SchedulePrincipal("ex-admin", creator_is_admin=False)
        with pytest.raises(SchedulePrincipalError):
            validate_schedule_execution(principal, uses_write_tools=True)

    def test_readonly_schedule_survives_role_loss(self):
        principal = SchedulePrincipal("ex-admin", creator_is_admin=False)
        validate_schedule_execution(principal, uses_write_tools=False)
