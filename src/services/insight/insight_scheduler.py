from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import Settings
from src.db.interface_db import BaseDatabase
from src.logger import AppLogger
from src.services.insight import insight_service
from src.services.llm.client import LLMClient

logger = AppLogger(__name__).get_logger()


class InsightScheduler:
    """
    APScheduler 排程：每日 01:00（可設定）自動為
    status='completed' 且尚無洞察的 Practice 生成個人成長洞察。
    """

    def __init__(self, settings: Settings, database: BaseDatabase):
        self._settings = settings
        self._database = database
        self._scheduler = AsyncIOScheduler()
        self._llm_client = LLMClient(settings, settings.insight.llm_backend)

    def start(self) -> None:
        cron = self._settings.insight.schedule_cron
        trigger = CronTrigger.from_crontab(cron, timezone="UTC")
        self._scheduler.add_job(
            self._run_job,
            trigger=trigger,
            id="generate_practice_insights",
            replace_existing=True,
            misfire_grace_time=3600,  # 若錯過最多補跑 1 小時內
        )
        self._scheduler.start()
        logger.info(f"[InsightScheduler] 已啟動，排程: {cron}")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("[InsightScheduler] 已停止")

    async def _run_job(self) -> None:
        logger.info("[InsightScheduler] 開始執行洞察生成任務")
        total = 0
        failed = 0

        with self._database.get_session() as db:
            practices = insight_service.get_pending_practices(db)
            logger.info(f"[InsightScheduler] 待處理 Practice 數量: {len(practices)}")

            for practice in practices:
                try:
                    result = await insight_service.generate_for_practice(
                        db, self._llm_client, practice
                    )
                    if result:
                        total += 1
                except Exception as exc:
                    failed += 1
                    logger.error(
                        f"[InsightScheduler] practice_id={practice.id} 失敗: {exc}"
                    )

        logger.info(f"[InsightScheduler] 任務完成 — 成功: {total}, 失敗: {failed}")
