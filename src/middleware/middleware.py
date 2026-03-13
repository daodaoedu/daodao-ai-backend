import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from slowapi import _rate_limit_exceeded_handler
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.config import get_settings
from src.middleware.limiter import limiter


def setup_middlewares(app: FastAPI):
    settings = get_settings()
    # === Rate Limiter ===

    app.state.limiter = limiter
    app.add_exception_handler(429, _rate_limit_exceeded_handler)

    # === CORS ===
    if settings.environment == "development":
        origins = ["https://server.daodao.so", "http://localhost:8002"]
    else:
        origins = ["https://dao-server.daodao.so"]

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
        allowed_hosts=[
            "localhost",
            "127.0.0.1",
            "server-ai.daodao.so",
            "dao-server-ai.daodao.so",
        ],
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

    from fastapi import HTTPException

    class ApiKeyMiddleware(BaseHTTPMiddleware):
        def __init__(self, app, api_key: str, environment: str):
            super().__init__(app)
            self.api_key = api_key
            self.environment = environment
            self.exempt_paths = (
                "/api/v1/ping",
                "/api/v1/health",
                "/metrics",
                "/docs",
                "/redoc",
                "/openapi.json",
            )

        async def dispatch(self, request: Request, call_next):
            if self.environment == "development":
                return await call_next(request)

            # 不驗證的路徑
            for path in self.exempt_paths:
                if request.url.path.startswith(path):
                    return await call_next(request)

            api_key = request.headers.get("x-api-key")
            expected_key = settings.api_secret_key
            if not api_key or api_key != expected_key:
                raise HTTPException(
                    status_code=403, detail="Forbidden: Invalid API Key"
                )
            return await call_next(request)

    app.add_middleware(
        ApiKeyMiddleware,
        api_key=settings.api_secret_key,
        environment=settings.environment,
    )

    # === Prometheus Instrumentator === 
    # /metrics endpoint for Prometheus to scrape
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
