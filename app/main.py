import uvicorn
from api.routers import feedback, recommendation, resource
from fastapi import FastAPI
from utils.redis_utils import check_redis_health
from core.middleware import setup_middlewares

app = FastAPI(
    title="DAODAO AI backend API",
    version="1.0.0",
    servers=[
        {"url": "http://127.0.0.1:8002", "description": "dev"},
        {"url": "http://127.0.0.1:8001", "description": "Production"},
    ],
)

setup_middlewares(app)


app.include_router(feedback.router, prefix="/api", tags=["feedback"])
app.include_router(resource.router, prefix="/api", tags=["resource"])
app.include_router(recommendation.router, prefix="/api", tags=["recommendation"])


@app.get("/")
async def root():
    return {"message": "Welcome to my FastAPI project!"}


@app.on_event("startup")
async def startup_event():
    # 啟動時檢查 Redis
    if not check_redis_health():
        raise RuntimeError("Redis service is unavailable. App startup aborted!")

