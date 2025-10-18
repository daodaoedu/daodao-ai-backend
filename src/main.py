from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from src.config import get_settings
from src.db.factory import make_database
from src.logger import AppLogger
from src.middleware.middleware import setup_middlewares
from src.routers import ping, recommendation
from src.services.cache.factory import make_cache_client
from src.services.clickhouse.factory import make_clickhouse_client
from src.services.llm.factory import make_llm_client
from src.services.qdrant.factory import make_qdrant_client

logger = AppLogger(__name__).get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan for the API.
    # 啟動前
    yield
    # 關閉前

    """
    logger.info("Starting daodao ai backend API...")
    logger.info("API ready")

    settings = get_settings()
    app.state.settings = settings

    app.state.database = make_database()

    qdrant_client = make_qdrant_client()
    app.state.qdrant_client = qdrant_client

    clickhouse_client = make_clickhouse_client()
    app.state.clickhouse_client = clickhouse_client

    llm_client = make_llm_client()
    app.state.llm_client = llm_client

    cache_client = make_cache_client(settings)
    app.state.cache_client = cache_client

    # 啟動時檢查 Redis
    if not cache_client.check_redis_health():
        raise RuntimeError("Redis service is unavailable. App startup aborted!")

    logger.info("🚀 startup_event triggered")
    await run_in_threadpool(app.state.qdrant_client.create_collection)
    logger.info("✅ daodao_collection ready")

    yield

    # Cleanup

    # database.teardown()
    logger.info("API shutdown complete")


app = FastAPI(
    title="DAODAO AI backend API",
    version="1.0.0",
    servers=[
        {"url": "http://127.0.0.1:8002", "description": "dev"},
        {"url": "http://127.0.0.1:8001", "description": "Production"},
    ],
    lifespan=lifespan,
)

setup_middlewares(app)


# app.include_router(feedback.router, prefix="/api", tags=["feedback"])
# app.include_router(resource.router, prefix="/api", tags=["resource"])
app.include_router(recommendation.router, prefix="/api", tags=["recommendation"])
app.include_router(ping.router, prefix="/api", tags=["Health"])


@app.get("/")
async def root():
    return {"message": "Welcome to my FastAPI project!"}
