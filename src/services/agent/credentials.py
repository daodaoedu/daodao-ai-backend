import os
from typing import Callable, Mapping, Optional

from src.logger import AppLogger

logger = AppLogger(__name__).get_logger()

# 第三方憑證一律由開發者供裝（見 agent-security spec「第三方憑證由開發者供裝」）。
# 解析優先序：config 檔 > DB 設定 > 環境變數（D13）。
# 對話內容不是合法來源——本模組刻意不提供任何從 user input 注入憑證的路徑。


def resolve_credential(
    name: str,
    config_credentials: Optional[Mapping[str, str]] = None,
    db_lookup: Optional[Callable[[str], Optional[str]]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """依 config > db > env 優先序解析第三方憑證，找不到回傳 None。

    Args:
        name: 憑證名稱，如 "NOTION_TOKEN"、"DAODAO_ADMIN_TOKEN"
        config_credentials: config 檔載入的憑證表
        db_lookup: 從 DB 設定表查詢的 callable（如 AIServiceConfig）
        env: 環境變數（預設 os.environ）
    """
    if config_credentials:
        value = config_credentials.get(name)
        if value:
            return value

    if db_lookup:
        value = db_lookup(name)
        if value:
            return value

    env_map = env if env is not None else os.environ
    return env_map.get(name) or None


def is_connector_allowed(
    connector: str,
    user_roles: frozenset[str],
    connector_roles: Mapping[str, frozenset[str]],
) -> bool:
    """connector 可用範圍依角色 / 組織綁定管理（D13）。

    connector_roles 未列出的 connector 一律拒絕（deny by default）。
    """
    allowed_roles = connector_roles.get(connector)
    if not allowed_roles:
        return False
    return bool(allowed_roles & user_roles)
