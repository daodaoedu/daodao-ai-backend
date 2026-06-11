from typing import AsyncIterator

from src.config import Settings
from src.logger import AppLogger
from src.services.agent.agent import DaoDaoAgent
from src.services.agent.state import AppState

logger = AppLogger(__name__).get_logger()


class QueryEngine:
    """Orchestrates a full Turn: context injection -> LLM -> tool execution -> approval -> result."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def run_turn(
        self,
        user_message: str,
        state: AppState,
        thread_history: list[dict],
        approval_response: str | None = None,  # "allow" or "deny" if resuming after approval
    ) -> AsyncIterator[dict]:
        # Handle approval resume
        if state.approval_pending and approval_response is not None:
            state.approval_pending = False
            if approval_response.lower() == "deny":
                yield {
                    "type": "agent_message",
                    "content": "操作已取消。",
                }
                yield {"type": "result", "summary": "Action denied by admin."}
                return
            # If allowed, continue processing the original message
            # (the engine will re-run or the caller handles execution)
            yield {
                "type": "agent_message",
                "content": "操作已核准，正在執行...",
            }

        agent = DaoDaoAgent(settings=self.settings, state=state)

        async for item in agent.process_turn(
            user_message=user_message,
            thread_history=thread_history,
        ):
            yield item
