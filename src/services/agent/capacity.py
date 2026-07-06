import os
from dataclasses import dataclass

from src.logger import AppLogger

logger = AppLogger(__name__).get_logger()

# 資源容量護欄（見 agent-harness spec「資源容量護欄」/ D14）：
# session / turn 啟動前檢查，執行中的高耗用操作也應呼叫 ensure_capacity。
# 預設水位可由呼叫端覆寫。

DEFAULT_MIN_FREE_MEMORY_MB = 256
DEFAULT_MIN_FREE_DISK_MB = 512


class CapacityError(RuntimeError):
    """記憶體或磁碟餘裕不足，拒絕啟動或要求降級。"""


@dataclass(frozen=True)
class CapacityStatus:
    free_memory_mb: int
    free_disk_mb: int
    ok: bool
    reason: str = ""


def _read_available_memory_mb() -> int:
    """從 /proc/meminfo 讀 MemAvailable（kB → MB）；讀不到時回傳 -1 表示未知。"""
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError as exc:
        logger.warning(f"Cannot read /proc/meminfo: {exc}")
    return -1


def _read_free_disk_mb(path: str) -> int:
    try:
        stat = os.statvfs(path)
        return int(stat.f_bavail * stat.f_frsize) // (1024 * 1024)
    except OSError as exc:
        logger.warning(f"Cannot statvfs {path}: {exc}")
        return -1


def check_capacity(
    min_free_memory_mb: int = DEFAULT_MIN_FREE_MEMORY_MB,
    min_free_disk_mb: int = DEFAULT_MIN_FREE_DISK_MB,
    disk_path: str = "/",
) -> CapacityStatus:
    """檢查記憶體與磁碟餘裕；量測失敗（-1）視為通過但留 log，不誤殺。"""
    free_mem = _read_available_memory_mb()
    free_disk = _read_free_disk_mb(disk_path)

    if 0 <= free_mem < min_free_memory_mb:
        return CapacityStatus(
            free_mem,
            free_disk,
            ok=False,
            reason=f"free memory {free_mem}MB < required {min_free_memory_mb}MB",
        )
    if 0 <= free_disk < min_free_disk_mb:
        return CapacityStatus(
            free_mem,
            free_disk,
            ok=False,
            reason=f"free disk {free_disk}MB < required {min_free_disk_mb}MB",
        )
    return CapacityStatus(free_mem, free_disk, ok=True)


def ensure_capacity(
    min_free_memory_mb: int = DEFAULT_MIN_FREE_MEMORY_MB,
    min_free_disk_mb: int = DEFAULT_MIN_FREE_DISK_MB,
    disk_path: str = "/",
) -> CapacityStatus:
    """容量不足時 raise CapacityError（session 啟動前 / 高耗用操作前呼叫）。"""
    status = check_capacity(min_free_memory_mb, min_free_disk_mb, disk_path)
    if not status.ok:
        raise CapacityError(status.reason)
    return status
