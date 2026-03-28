"""
SystemPrompt 業務邏輯：
- is_active 排他性：全局只能一個 prompt 為 active
- version 自動遞增
"""

from typing import Optional

from sqlalchemy.orm import Session

from src.models.SystemPrompt import SystemPrompt


def deactivate_others(db: Session, exclude_id: Optional[int] = None) -> None:
    """將所有其他 active prompt 設為 inactive（全局只允許一個 active）。"""
    query = db.query(SystemPrompt).filter(SystemPrompt.is_active.is_(True))
    if exclude_id is not None:
        query = query.filter(SystemPrompt.id != exclude_id)
    query.update({"is_active": False}, synchronize_session=False)
