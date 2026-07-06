from dataclasses import dataclass

from src.logger import AppLogger
from src.services.agent.approval import ApprovalMode, ApprovalPolicy
from src.services.agent.state import AppState

logger = AppLogger(__name__).get_logger()

# 排程執行身分（agent-security spec「排程執行身分」/ D17）：
# 無人值守排程以建立者身分執行；建立者失去 admin 角色時排程自動停用。
# 排程 runner 落地時 MUST 於每次觸發前呼叫 validate_schedule_execution。


class SchedulePrincipalError(PermissionError):
    """排程建立者已不具執行所需角色，排程應停用。"""


@dataclass(frozen=True)
class SchedulePrincipal:
    """排程綁定的執行身分：建立排程的用戶。"""

    creator_user_id: str
    creator_is_admin: bool
    dry_run: bool = True  # 排程定義中明確設 False 視為建立者明確授權


def validate_schedule_execution(
    principal: SchedulePrincipal,
    uses_write_tools: bool,
) -> None:
    """每次排程觸發前檢核：含寫入型工具的排程，建立者必須仍具 admin 角色。

    Raises SchedulePrincipalError — 呼叫端 MUST 停用該排程並記錄停用原因。
    """
    if uses_write_tools and not principal.creator_is_admin:
        raise SchedulePrincipalError(
            f"Schedule creator {principal.creator_user_id} no longer has admin role; "
            "schedule must be disabled."
        )


def build_schedule_state(
    principal: SchedulePrincipal,
    allowlist: frozenset[str],
    denylist: frozenset[str] = frozenset(),
) -> AppState:
    """建立排程執行用的 AppState：auto 模式 + 明確 allowlist，身分為建立者。

    排程 MUST 採 auto 模式（否則 Turn 會永久卡在審批，見 D12）；
    dry_run 依排程定義（明確設 False 即視為授權）。
    """
    return AppState(
        dry_run=principal.dry_run,
        user_id=principal.creator_user_id,
        approval_policy=ApprovalPolicy(
            mode=ApprovalMode.AUTO,
            allowlist=allowlist,
            denylist=denylist,
        ),
    )
