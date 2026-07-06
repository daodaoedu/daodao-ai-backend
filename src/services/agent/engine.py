from typing import AsyncIterator

from src.config import Settings
from src.logger import AppLogger
from src.services.agent.agent import DaoDaoAgent
from src.services.agent.capacity import CapacityError, ensure_capacity
from src.services.agent.state import AppState

logger = AppLogger(__name__).get_logger()

# 任務用了多個工具組合時，評估是否值得沉澱為可重用 Skill（D16 / agent-skills spec）
_REUSE_SUGGESTION_MIN_TOOLS = 3


class QueryEngine:
    """Orchestrates a full Turn: context -> LLM -> tool execution -> approval -> result."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def run_turn(
        self,
        user_message: str,
        state: AppState,
        thread_history: list[dict],
        approval_response: (
            str | None
        ) = None,  # "allow" or "deny" if resuming after approval
    ) -> AsyncIterator[dict]:
        # 資源容量護欄：餘裕不足時拒絕啟動而非帶病執行（D14）
        try:
            ensure_capacity()
        except CapacityError as exc:
            logger.error(f"Capacity check failed, refusing turn: {exc}")
            yield {
                "type": "result",
                "summary": f"資源餘裕不足，本次任務未啟動：{exc}",
                "error": "capacity_exceeded",
            }
            return

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

        # 任務後可重用程式碼沉澱評估：多步工具組合的臨時任務，建議存為 draft Skill
        distinct_tools = set(state.tools_used)
        if len(distinct_tools) >= _REUSE_SUGGESTION_MIN_TOOLS:
            yield {
                "type": "agent_message",
                "content": (
                    f"本次任務組合了 {len(distinct_tools)} 種工具"
                    f"（{', '.join(sorted(distinct_tools))}）。"
                    "若此流程會重複使用，建議存成 draft Skill 供 review 後排程復用。"
                ),
                "suggestion": "save_as_skill",
            }
