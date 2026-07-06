"""
Unit tests for ContextBuilder and AppState (tasks 11.1).
"""

from datetime import date

from src.services.agent.approval import ApprovalMode, ApprovalPolicy
from src.services.agent.context import ContextBuilder
from src.services.agent.state import AppState


class TestContextBuilder:

    def test_injects_current_date(self):
        context = ContextBuilder().build(AppState())
        assert date.today().isoformat() in context

    def test_injects_provider_and_dry_run(self):
        state = AppState(provider="gemini", dry_run=True)
        context = ContextBuilder().build(state)
        assert "gemini" in context
        assert "DRY RUN MODE" in context

    def test_live_mode_reflected(self):
        context = ContextBuilder().build(AppState(dry_run=False))
        assert "LIVE MODE" in context

    def test_injects_db_schema_summary(self):
        context = ContextBuilder().build(AppState())
        for table in ("practices", "practice_checkins", "users", "email_logs"):
            assert table in context

    def test_guidelines_cover_readonly_and_citation(self):
        context = ContextBuilder().build(AppState())
        assert "READ-ONLY" in context
        assert "prod AND dev" in context
        assert "Cite your sources" in context


class TestAppState:

    def test_defaults_are_safe(self):
        state = AppState()
        assert state.dry_run is True
        assert state.approval_pending is False
        assert state.approval_policy.mode is ApprovalMode.NORMAL
        assert state.tools_used == []
        assert state.sources == []

    def test_state_persists_across_turns(self):
        # 前一 Turn 切換 provider 與關閉 dry_run 後，後續 Turn 沿用同一 state 物件
        state = AppState()
        state.provider = "ollama"
        state.dry_run = False
        state.tools_used.append("query_db")

        assert state.provider == "ollama"
        assert state.dry_run is False
        assert "query_db" in state.tools_used

    def test_policy_is_carried_in_state(self):
        policy = ApprovalPolicy(mode=ApprovalMode.AUTO, allowlist=frozenset({"send_emails"}))
        state = AppState(approval_policy=policy)
        assert state.approval_policy.resolve("send_emails").value == "allow"
