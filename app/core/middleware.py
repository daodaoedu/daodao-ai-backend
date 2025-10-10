import time

from core.limiter import limiter
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from slowapi import _rate_limit_exceeded_handler
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware


def setup_middlewares(app: FastAPI):
    # === Rate Limiter ===

    app.state.limiter = limiter
    app.add_exception_handler(429, _rate_limit_exceeded_handler)

    # === CORS ===
    origins = [
        "http://localhost.tiangolo.com",
        "https://localhost.tiangolo.com",
        "http://localhost",
        "http://localhost:5173",
        "http://frontend",  # 使用服務名稱作為來源
        "http://localhost:8002",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,  # 先允許所有, 可改為指定 domain
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # === TrustedHost ===
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1"],
    )

    # === Session ===
    # app.add_middleware(SessionMiddleware, secret_key="super-secret-session-key")

    # === Logging Middleware ===
    class LoggingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            start = time.time()
            response: Response = await call_next(request)
            duration = round(time.time() - start, 3)
            print(
                f"{request.method} {request.url.path} - {response.status_code} ({duration}s)"
            )
            return response

    app.add_middleware(LoggingMiddleware)

    # === Prometheus Instrumentator ===
    _ = (
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

    return app
