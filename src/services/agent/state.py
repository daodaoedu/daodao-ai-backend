from dataclasses import dataclass, field


@dataclass
class AppState:
    provider: str = "openrouter"          # current LLM provider
    model_override: str | None = None     # override specific model
    dry_run: bool = True                  # default safe: no real actions
    thread_id: str | None = None
    tools_used: list[str] = field(default_factory=list)
    approval_pending: bool = False
