"""
SystemPrompt 業務邏輯：
- is_active 排他性：全局只能一個 prompt 為 active
- version 自動遞增
- seed_default_prompts：lifespan 啟動時將 txt 檔寫入 DB（冪等）
"""

from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from src.logger import AppLogger
from src.models.SystemPrompt import SystemPrompt

logger = AppLogger(__name__).get_logger()

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# txt 檔名 → system_prompts.name 的對應表
_SEED_PROMPTS: dict[str, str] = {
    "insight": "insight_system.txt",
    "rag": "rag_system.txt",
    "life_design_coach": "life_design_coach_system.txt",
    "life_design": "life_design_system.txt",
}


def seed_default_prompts(db: Session) -> None:
    """
    Lifespan 啟動時呼叫：將 src/services/prompts/*.txt 寫入 system_prompts 表。
    冪等：name 已存在則跳過，不覆蓋。
    is_active 預設 False，讓 Admin 手動啟用。
    """
    for name, filename in _SEED_PROMPTS.items():
        prompt_file = _PROMPTS_DIR / filename
        if not prompt_file.exists():
            logger.warning(f"[PromptSeed] 找不到 {prompt_file}，跳過")
            continue

        exists = db.query(SystemPrompt).filter(SystemPrompt.name == name).first()
        if exists:
            logger.debug(f"[PromptSeed] name='{name}' 已存在，跳過")
            continue

        content = prompt_file.read_text(encoding="utf-8").strip()
        db.add(SystemPrompt(name=name, content=content, is_active=False, version=1))
        logger.info(f"[PromptSeed] 已插入 system_prompt name='{name}'")

    db.commit()


def get_active_system_prompt(db: Session, name: str, fallback: str = "") -> str:
    """
    查詢指定 name 的 system prompt（name 為唯一索引）。
    找到且 is_active=True → 回傳 content。
    未找到或未啟用 → 回傳 fallback。
    """
    prompt = db.query(SystemPrompt).filter(SystemPrompt.name == name).first()
    if prompt and prompt.is_active:
        return prompt.content
    return fallback


def deactivate_others(db: Session, exclude_id: Optional[int] = None) -> None:
    """將所有其他 active prompt 設為 inactive（全局只允許一個 active）。"""
    query = db.query(SystemPrompt).filter(SystemPrompt.is_active.is_(True))
    if exclude_id is not None:
        query = query.filter(SystemPrompt.id != exclude_id)
    query.update({"is_active": False}, synchronize_session=False)
