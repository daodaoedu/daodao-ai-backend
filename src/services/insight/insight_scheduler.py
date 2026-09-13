from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import Settings
from src.db.interface_db import BaseDatabase
from src.logger import AppLogger
from src.models.AIServiceConfig import AIServiceConfig
from src.models.LLMModel import LLMModel
from src.services.insight import insight_service
from src.services.llm.client import LLMClient
from src.services.llm.logging_client import LoggingLLMClient

logger = AppLogger(__name__).get_logger()


class InsightScheduler:
    """
    APScheduler 排程：每日 01:00（可設定）自動為
    status='completed' 且尚無洞察的 Practice 生成個人成長洞察。
    模型與生成參數優先從 ai_service_configs（service='insight', is_active=True）讀取，
    若無設定則 fallback 至 settings.insight.llm_backend。
    """

    def __init__(self, settings: Settings, database: BaseDatabase):
        self._settings = settings
        self._database = database
        self._scheduler = AsyncIOScheduler()

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

    def _build_fallback_client(self) -> LLMClient:
        return LLMClient(self._settings, self._settings.insight.llm_backend)

    async def _run_job(self) -> None:
        logger.info("[InsightScheduler] 開始執行洞察生成任務")
        total = 0
        failed = 0

        with self._database.get_session() as db:
            # 1. 優先從 ai_service_configs 讀取 active 設定
            config = (
                db.query(AIServiceConfig)
                .filter(
                    AIServiceConfig.service == "insight",
                    AIServiceConfig.is_active.is_(True),
                )
                .first()
            )

            if config is not None:
                model = db.get(LLMModel, config.model_id)
                if model is None:
                    logger.error(
                        f"[InsightScheduler] ai_service_configs.model_id={config.model_id} 不存在，跳過"
                    )
                    return
                try:
                    llm_client = LLMClient(self._settings, model.provider)
                    llm_client._backend.config["model"] = model.model_name  # type: ignore[attr-defined]
                except Exception as exc:
                    logger.warning(
                        f"[InsightScheduler] 從 ai_service_configs 建立 client 失敗: {exc}，使用 fallback"
                    )
                    try:
                        llm_client = self._build_fallback_client()
                    except Exception as fallback_exc:
                        logger.warning(
                            f"[InsightScheduler] fallback 初始化失敗，本次任務跳過: {fallback_exc}"
                        )
                        return

                generate_kwargs: dict = {}
                if config.max_tokens is not None:
                    generate_kwargs["max_tokens"] = int(config.max_tokens)
                if config.temperature is not None:
                    generate_kwargs["temperature"] = float(config.temperature)
                if config.top_p is not None:
                    generate_kwargs["top_p"] = float(config.top_p)
                if config.top_k is not None:
                    generate_kwargs["top_k"] = int(config.top_k)
                system_prompt_id = config.system_prompt_id
                logger.info(
                    f"[InsightScheduler] 使用 ai_service_configs id={config.id} "
                    f"model={model.provider}/{model.model_name} kwargs={generate_kwargs}"
                )
            else:
                # Fallback：使用 settings 中的 llm_backend
                try:
                    llm_client = self._build_fallback_client()
                except Exception as exc:
                    logger.warning(
                        f"[InsightScheduler] LLM client 初始化失敗，本次任務跳過: {exc}"
                    )
                    return
                generate_kwargs = {}
                system_prompt_id = None
                logger.info(
                    "[InsightScheduler] 無 ai_service_configs，使用 settings 預設"
                )

            practices = insight_service.get_pending_practices(db)
            logger.info(f"[InsightScheduler] 待處理 Practice 數量: {len(practices)}")

            logging_client = LoggingLLMClient(
                llm_client=llm_client,
                db_session_factory=self._database.get_session,
                context="insight",
                user_id=None,
                service_config_id=config.id if config is not None else None,
            )

            for practice in practices:
                try:
                    result = await insight_service.generate_for_practice(
                        db,
                        logging_client,
                        practice,
                        system_prompt_id=system_prompt_id,
                        **generate_kwargs,
                    )
                    if result:
                        total += 1
                except Exception as exc:
                    failed += 1
                    logger.error(
                        f"[InsightScheduler] practice_id={practice.id} 失敗: {exc}"
                    )

        logger.info(f"[InsightScheduler] 任務完成 — 成功: {total}, 失敗: {failed}")
