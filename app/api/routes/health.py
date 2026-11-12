"""
Portfolio Health Monitor
System & Database Health Endpoints
"""

from typing import Any, Dict

from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.core.tracing import verify_tracing_connectivity
from app.database.connection import check_db_health

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get(
    "",
    summary="Application Health Probe",
    description="Returns high-level application runtime health and version metadata.",
    response_model=Dict[str, Any],
)
@router.get(
    "/",
    include_in_schema=False,
    response_model=Dict[str, Any],
)
async def get_application_health() -> Dict[str, Any]:
    """Basic container/orchestrator liveness probe."""
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT.value,
    }


@router.get(
    "/database",
    summary="Database Connectivity Health Probe",
    description="Executes a live query against PostgreSQL and measures round-trip latency.",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "Database is reachable and responding normally."},
        503: {"description": "Database is unreachable or unhealthy."},
    },
)
async def get_database_health(response: Response) -> Dict[str, Any]:
    """Readiness probe specifically validating the PostgreSQL database connection."""
    db_status = await check_db_health()
    if not db_status.get("connected"):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return db_status


@router.get(
    "/tracing",
    summary="Observability & LangSmith Tracing Probe",
    description="Reports whether LangSmith tracing is active, configured, or disabled.",
    response_model=Dict[str, Any],
)
async def get_tracing_health() -> Dict[str, Any]:
    """Inspect observability configuration and credential status."""
    is_confirmed, status_msg, details = verify_tracing_connectivity()
    return {
        "status": "connected" if is_confirmed else "configured" if details.get("tracing_enabled_in_config") else "disabled",
        "message": status_msg,
        "details": details,
    }

