import uvicorn
from api.routers import feedback, recommendation, resource
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from utils.redis_utils import check_redis_health

app = FastAPI(
    title="DAODAO AI backend API",
    version="1.0.0",
    servers=[
        {"url": "http://127.0.0.1:8002", "description": "dev"},
        {"url": "http://127.0.0.1:8001", "description": "Production"},
    ],
)


instrumentator = (
    Instrumentator()
    .add(
        metrics.default(
            metric_namespace="daodao",  # Don't user -
            metric_subsystem="daodao-ai-backend",
            custom_labels={"environment": "backend", "app": "daodao-ai-backend"},
        )
    )
    .instrument(app)
    .expose(app)
)

origins = [
    "http://localhost.tiangolo.com",
    "https://localhost.tiangolo.com",
    "http://localhost",
    "http://localhost:5173",
    "http://frontend",  # 使用服務名稱作為來源
    # "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# app.include_router(api_router, prefix="/apis")
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
