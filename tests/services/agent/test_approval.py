"""
Approval Flow tests: pause / allow / deny + auto/normal 雙模式 (tasks 11.2, 12.2).
"""

import pytest

from src.config import get_settings
from src.services.agent.approval import (
    ActionDecision,
    ApprovalMode,
    ApprovalPolicy,
)
from src.services.agent.engine import QueryEngine
from src.services.agent.state import AppState


class TestApprovalPolicy:

    def test_normal_mode_always_asks(self):
        policy = ApprovalPolicy(mode=ApprovalMode.NORMAL, allowlist=frozenset({"send_emails"}))
        # normal 模式即使在 allowlist 也要審批
        assert policy.resolve("send_emails") is ActionDecision.ASK

    def test_auto_mode_allows_allowlisted(self):
        policy = ApprovalPolicy(mode=ApprovalMode.AUTO, allowlist=frozenset({"send_emails"}))
        assert policy.resolve("send_emails") is ActionDecision.ALLOW

    def test_auto_mode_still_asks_for_unlisted(self):
        policy = ApprovalPolicy(mode=ApprovalMode.AUTO, allowlist=frozenset({"send_emails"}))
        assert policy.resolve("send_notifications") is ActionDecision.ASK

    def test_denylist_wins_over_allowlist_in_auto(self):
        # denylist 不可被 auto 模式覆蓋（agent-approval spec）
        policy = ApprovalPolicy(
            mode=ApprovalMode.AUTO,
            allowlist=frozenset({"send_emails"}),
            denylist=frozenset({"send_emails"}),
        )
        assert policy.resolve("send_emails") is ActionDecision.DENY

    def test_denylist_applies_in_normal_mode(self):
        policy = ApprovalPolicy(mode=ApprovalMode.NORMAL, denylist=frozenset({"drop_tables"}))
        assert policy.resolve("drop_tables") is ActionDecision.DENY


class TestApprovalResume:

    @pytest.mark.asyncio
    async def test_deny_cancels_turn(self):
        engine = QueryEngine(get_settings())
        state = AppState(approval_pending=True)

        items = [
            item
            async for item in engine.run_turn(
                user_message="",
                state=state,
                thread_history=[],
                approval_response="deny",
            )
        ]

        assert state.approval_pending is False
        result = next(i for i in items if i["type"] == "result")
        assert "denied" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_allow_resumes_turn(self, monkeypatch):
        engine = QueryEngine(get_settings())
        state = AppState(approval_pending=True)

        async def fake_process_turn(self, user_message, thread_history):
            yield {"type": "result", "summary": "done after approval"}

        monkeypatch.setattr(
            "src.services.agent.agent.DaoDaoAgent.process_turn", fake_process_turn
        )

        items = [
            item
            async for item in engine.run_turn(
                user_message="continue",
                state=state,
                thread_history=[],
                approval_response="allow",
            )
        ]

        assert state.approval_pending is False
        messages = [i for i in items if i["type"] == "agent_message"]
        assert any("核准" in m["content"] for m in messages)
        assert any(i["type"] == "result" and "done" in i["summary"] for i in items)
