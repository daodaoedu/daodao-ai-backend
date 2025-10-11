from api.auto_metrics import observe_api
from dependencies import ClickHouseDep, QdrantDep, SessionDep, SettingsDep
from fastapi import APIRouter, Request
from qdrant_client.http.exceptions import UnexpectedResponse
from schemas.health import HealthResponse, ServiceStatus
from sqlalchemy import text

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
    qdrant_client: QdrantDep,
    clickhouse_client: ClickHouseDep,
) -> HealthResponse:
    """Comprehensive health check endpoint for monitoring and load balancer probes.

    :returns: Service health status with version and connectivity checks
    :rtype: HealthResponse
    """
    services = {}
    overall_status = "ok"

    def _check_service(name: str, check_func, *args, **kwargs):
        """Helper to standardize service health checks."""
        try:
            if kwargs.get("is_async"):
                # Handle async functions separately in the calling code
                return check_func(*args)
            result = check_func(*args)
            services[name] = result
            if result.status != "healthy":
                nonlocal overall_status
                overall_status = "degraded"
        except Exception as e:
            services[name] = ServiceStatus(status="unhealthy", message=str(e))
            overall_status = "degraded"

    # Database check

    def _check_database():
        db.execute(text("SELECT 1"))
        return ServiceStatus(status="healthy", message="Connected successfully")

    def _check_qdrant():
        try:
            collections = qdrant_client.get_collections()
            col_names = [c.name for c in collections.collections]
            if settings.collection_name in col_names:
                return ServiceStatus(status="healthy", message="Qdrant reachable")
            else:
                return ServiceStatus(
                    status="unhealthy",
                    message=f"Collection `{settings.collection_name}` not found",
                )
        except UnexpectedResponse as e:
            return ServiceStatus(status="unhealthy", message=str(e))

    def _check_clickhouse():
        try:
            result = clickhouse_client.client.execute("SELECT 1")
            if result and result[0][0] == 1:
                return ServiceStatus(status="healthy", message="ClickHouse reachable")
            else:
                return ServiceStatus(
                    status="unhealthy", message="Unexpected response from ClickHouse"
                )
        except Exception as e:
            return ServiceStatus(status="unhealthy", message=str(e))

    # Run synchronous checks
    _check_service("database", _check_database)
    _check_service("qdrant", _check_qdrant)
    _check_service("clickhouse", _check_clickhouse)

    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        environment=settings.environment,
        service_name=settings.service_name,
        services=services,
    )
