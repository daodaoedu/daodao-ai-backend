import uvicorn
from contextlib import asynccontextmanager
from api.routers import feedback, recommendation, resource
from fastapi import FastAPI

from core.middleware import setup_middlewares

from services.db.factory import make_database
from services.llm.factory import make_llm_client
from services.cache.factory import make_cache_client
from services.qdrant.factory import make_qdrant_client

from config import get_settings
from logger import AppLogger

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
    
    llm_client = make_llm_client()
    app.state.llm_client = llm_client
    
    
    cache_client = make_cache_client(settings)
    app.state.cache_client = cache_client
    
    
    
    # 啟動時檢查 Redis
    if not cache_client.check_redis_health():
        raise RuntimeError("Redis service is unavailable. App startup aborted!")

    
    
    

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


app.include_router(feedback.router, prefix="/api", tags=["feedback"])
app.include_router(resource.router, prefix="/api", tags=["resource"])
app.include_router(recommendation.router, prefix="/api", tags=["recommendation"])


@app.get("/")
async def root():
    return {"message": "Welcome to my FastAPI project!"}

    