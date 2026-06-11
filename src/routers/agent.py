import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.dependencies import AdminDep, SessionDep, SettingsDep
from src.response_template import api_response_decorator
from src.services.agent.engine import QueryEngine
from src.services.agent.state import AppState

router = APIRouter()

# In-memory thread storage (MVP — no separate DB model needed)
# thread_id -> {id, title, history, state_dict, created_at}
_threads: dict[str, dict] = {}


# ── Request / Response schemas ────────────────────────────────────────────────


class CreateThreadRequest(BaseModel):
    title: Optional[str] = None


class SendTurnRequest(BaseModel):
    message: str
    provider: Optional[str] = None
    model_override: Optional[str] = None
    dry_run: Optional[bool] = None


class ApproveRequest(BaseModel):
    response: str  # "allow" or "deny"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _new_thread(title: str | None = None) -> dict:
    thread_id = str(uuid.uuid4())
    return {
        "id": thread_id,
        "title": title or f"Thread {thread_id[:8]}",
        "history": [],
        "state": {
            "provider": "openrouter",
            "model_override": None,
            "dry_run": True,
            "thread_id": thread_id,
            "tools_used": [],
            "approval_pending": False,
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "archived": False,
    }


def _get_thread_or_404(thread_id: str) -> dict:
    thread = _threads.get(thread_id)
    if thread is None or thread.get("archived"):
        raise HTTPException(status_code=404, detail=f"Thread '{thread_id}' not found")
    return thread


def _state_from_thread(thread: dict) -> AppState:
    s = thread["state"]
    return AppState(
        provider=s.get("provider", "openrouter"),
        model_override=s.get("model_override"),
        dry_run=s.get("dry_run", True),
        thread_id=s.get("thread_id"),
        tools_used=list(s.get("tools_used", [])),
        approval_pending=s.get("approval_pending", False),
    )


def _sync_state_to_thread(thread: dict, state: AppState) -> None:
    thread["state"] = {
        "provider": state.provider,
        "model_override": state.model_override,
        "dry_run": state.dry_run,
        "thread_id": state.thread_id,
        "tools_used": state.tools_used,
        "approval_pending": state.approval_pending,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/agent/threads")
@api_response_decorator
async def create_thread(
    body: CreateThreadRequest,
    admin: AdminDep,  # noqa: ARG001
) -> dict:
    """Create a new agent conversation thread."""
    thread = _new_thread(body.title)
    _threads[thread["id"]] = thread
    return {
        "data": {
            "id": thread["id"],
            "title": thread["title"],
            "created_at": thread["created_at"],
        },
        "pagination": None,
        "cache_hit": False,
    }


@router.get("/agent/threads")
@api_response_decorator
async def list_threads(
    admin: AdminDep,  # noqa: ARG001
) -> dict:
    """List all active agent threads."""
    threads = [
        {
            "id": t["id"],
            "title": t["title"],
            "created_at": t["created_at"],
            "message_count": len(t["history"]),
            "approval_pending": t["state"].get("approval_pending", False),
        }
        for t in _threads.values()
        if not t.get("archived")
    ]
    threads.sort(key=lambda x: x["created_at"], reverse=True)
    return {
        "data": threads,
        "pagination": None,
        "cache_hit": False,
    }


@router.get("/agent/threads/{thread_id}")
@api_response_decorator
async def get_thread(
    thread_id: str,
    admin: AdminDep,  # noqa: ARG001
) -> dict:
    """Get a thread with its full conversation history."""
    thread = _get_thread_or_404(thread_id)
    return {
        "data": {
            "id": thread["id"],
            "title": thread["title"],
            "created_at": thread["created_at"],
            "history": thread["history"],
            "state": thread["state"],
        },
        "pagination": None,
        "cache_hit": False,
    }


@router.post("/agent/threads/{thread_id}/turns")
@api_response_decorator
async def send_turn(
    thread_id: str,
    body: SendTurnRequest,
    admin: AdminDep,  # noqa: ARG001
    settings: SettingsDep,
    db: SessionDep,  # noqa: ARG001 — available for skill execution
) -> dict:
    """Send a user message to the agent and get a response."""
    thread = _get_thread_or_404(thread_id)
    state = _state_from_thread(thread)

    # Apply per-turn overrides
    if body.provider is not None:
        state.provider = body.provider
    if body.model_override is not None:
        state.model_override = body.model_override
    if body.dry_run is not None:
        state.dry_run = body.dry_run

    # Append user message to history
    thread["history"].append({"role": "user", "content": body.message})

    engine = QueryEngine(settings=settings)
    items: list[dict] = []

    async for item in engine.run_turn(
        user_message=body.message,
        state=state,
        thread_history=thread["history"][:-1],  # exclude the just-added user message
    ):
        items.append(item)

    # Append agent response to history
    agent_messages = [i["content"] for i in items if i.get("type") == "agent_message"]
    if agent_messages:
        thread["history"].append(
            {"role": "assistant", "content": "\n\n".join(agent_messages)}
        )

    # Sync state back
    _sync_state_to_thread(thread, state)

    return {
        "data": {
            "thread_id": thread_id,
            "items": items,
        },
        "pagination": None,
        "cache_hit": False,
    }


@router.post("/agent/threads/{thread_id}/approve")
@api_response_decorator
async def approve_action(
    thread_id: str,
    body: ApproveRequest,
    admin: AdminDep,  # noqa: ARG001
    settings: SettingsDep,
    db: SessionDep,  # noqa: ARG001
) -> dict:
    """Respond to a pending approval request (allow or deny)."""
    thread = _get_thread_or_404(thread_id)
    state = _state_from_thread(thread)

    if not state.approval_pending:
        raise HTTPException(
            status_code=400, detail="No approval request is pending for this thread."
        )

    if body.response.lower() not in ("allow", "deny"):
        raise HTTPException(
            status_code=422, detail="response must be 'allow' or 'deny'."
        )

    engine = QueryEngine(settings=settings)
    items: list[dict] = []

    # Re-run with approval response using the last user message
    last_user_msg = ""
    for turn in reversed(thread["history"]):
        if turn.get("role") == "user":
            last_user_msg = turn.get("content", "")
            break

    async for item in engine.run_turn(
        user_message=last_user_msg,
        state=state,
        thread_history=thread["history"],
        approval_response=body.response,
    ):
        items.append(item)

    # Append agent follow-up to history
    agent_messages = [i["content"] for i in items if i.get("type") == "agent_message"]
    if agent_messages:
        thread["history"].append(
            {"role": "assistant", "content": "\n\n".join(agent_messages)}
        )

    _sync_state_to_thread(thread, state)

    return {
        "data": {
            "thread_id": thread_id,
            "approval_response": body.response,
            "items": items,
        },
        "pagination": None,
        "cache_hit": False,
    }


@router.delete("/agent/threads/{thread_id}")
@api_response_decorator
async def archive_thread(
    thread_id: str,
    admin: AdminDep,  # noqa: ARG001
) -> dict:
    """Archive (soft-delete) a thread."""
    thread = _get_thread_or_404(thread_id)
    thread["archived"] = True
    return {
        "data": {"id": thread_id, "archived": True},
        "pagination": None,
        "cache_hit": False,
    }
