from fastapi import APIRouter, Request

from src.auto_metrics import observe_api
from src.dependencies import SessionDep, SettingsDep
from src.schemas.health import HealthResponse, ServiceStatus
from src.services.health_service import check_database

router = APIRouter(prefix="/v1")


@router.get("/ping")
@observe_api
async def ping(request: Request):
    """Simple ping endpoint for basic connectivity tests."""
    return {"status": "ok", "message": "pong"}


@router.get("/health", response_model=HealthResponse)
@observe_api
async def health_check(
    request: Request,
    db: SessionDep,
    settings: SettingsDep,
    # qdrant_client: QdrantDep,
    # clickhouse_client: ClickHouseDep,
) -> HealthResponse:
    """Comprehensive health check endpoint for monitoring and load balancer probes.

    :returns: Service health status with version and connectivity checks
    :rtype: HealthResponse
    """
    services = {}
    overall_status = "ok"

    try:
        services["database"] = check_database(db)
        if services["database"].status != "healthy":
            overall_status = "degraded"
    except Exception as e:
        services["database"] = ServiceStatus(status="unhealthy", message=str(e))
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        environment=settings.environment,
        service_name=settings.service_name,
        services=services,
    )
