from fastapi import APIRouter

from src.routers.admin import (
    ai_service_configs,
    dashboard,
    feed_ranking_configs,
    llm_models,
    ping,
    playground,
    query_logs,
    system_prompts,
    user_quotas,
)

router = APIRouter(prefix="/v1/admin")

router.include_router(ping.router, tags=["admin"])
router.include_router(ai_service_configs.router, tags=["admin-ai-service-configs"])
router.include_router(feed_ranking_configs.router, tags=["admin-feed-ranking-configs"])
router.include_router(dashboard.router, tags=["admin-dashboard"])
router.include_router(query_logs.router, tags=["admin-query-logs"])
router.include_router(system_prompts.router, tags=["admin-system-prompts"])
router.include_router(llm_models.router, tags=["admin-llm-models"])
router.include_router(user_quotas.router, tags=["admin-user-quotas"])
router.include_router(playground.router, tags=["admin-playground"])
