import time
from pathlib import Path

from src.logger import AppLogger

logger = AppLogger(__name__).get_logger()

# Agent 暫存檔案保留 30 天（agent-tools spec「檔案暫存 30 天」/ D16）。
SCRATCH_TTL_DAYS = 30
DEFAULT_SCRATCH_DIR = Path("/tmp/daodao-agent-scratch")  # nosec B108 - agent 暫存區


def write_scratch_file(
    filename: str,
    content: str,
    scratch_dir: Path = DEFAULT_SCRATCH_DIR,
) -> Path:
    """寫入暫存檔（報告、匯出、腳本草稿）。檔名不得含路徑跳脫。"""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError(f"Invalid filename: {filename}")
    scratch_dir.mkdir(parents=True, exist_ok=True)
    path = scratch_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def cleanup_expired_files(
    scratch_dir: Path = DEFAULT_SCRATCH_DIR,
    ttl_days: int = SCRATCH_TTL_DAYS,
    now: float | None = None,
) -> list[str]:
    """移除建立超過 ttl_days 的暫存檔，回傳被清除的檔名清單（供 audit）。"""
    if not scratch_dir.exists():
        return []

    current = now if now is not None else time.time()
    cutoff = current - ttl_days * 86400
    removed: list[str] = []

    for entry in scratch_dir.iterdir():
        if not entry.is_file():
            continue
        if entry.stat().st_mtime < cutoff:
            try:
                entry.unlink()
                removed.append(entry.name)
            except OSError as exc:
                logger.warning(f"Failed to remove expired scratch file {entry}: {exc}")

    if removed:
        logger.info(f"Removed {len(removed)} expired agent scratch file(s): {removed}")
    return removed
