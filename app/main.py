"""
Portfolio Health Monitor
Application Entry Point & FastAPI Route Assembly
"""

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import api_router, health_router
from app.core.config import get_settings, setup_logging
from app.core.tracing import setup_tracing, verify_tracing_connectivity
from app.database.connection import check_db_health, close_db_connection

settings = get_settings()
logger = setup_logging(settings)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context managing startup validation and shutdown resource cleanup."""
    logger.info(
        "Portfolio Health Monitor application booting | project=%s | env=%s | version=%s",
        settings.PROJECT_NAME,
        settings.ENVIRONMENT.value,
        settings.VERSION,
    )

    # Configure LangSmith tracing environment
    setup_tracing()
    _, tracing_msg, _ = verify_tracing_connectivity()
    logger.info("Observability status: %s", tracing_msg)

    # Non-blocking connectivity test on startup
    db_status = await check_db_health()
    if db_status.get("connected"):
        logger.info(
            "Database connectivity verified on startup | latency=%sms",
            db_status.get("latency_ms"),
        )
    else:
        logger.warning(
            "Database not reachable during startup: %s",
            db_status.get("error", "Unknown connection error"),
        )

    yield

    # Gracefully dispose database connection pools on shutdown
    logger.info("Application shutdown initiated. Disposing resources...")
    await close_db_connection()
    logger.info("Portfolio Health Monitor application shutdown completed.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Evidence-based multi-agent financial portfolio monitoring system.",
    debug=settings.DEBUG,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ------------------------------------------------------------------------------
# Configurable CORS Middleware
# ------------------------------------------------------------------------------
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ------------------------------------------------------------------------------
# Standardized Error Handling
# ------------------------------------------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Consistent formatting for HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Consistent formatting for Pydantic request validation errors."""
    formatted_errors = []
    for err in exc.errors():
        loc = " -> ".join(str(p) for p in err.get("loc", []))
        formatted_errors.append(f"{loc}: {err.get('msg')}")

    return JSONResponse(
        status_code=422,
        content={
            "detail": "Request validation failed.",
            "errors": formatted_errors,
        },
    )


# ------------------------------------------------------------------------------
# Router Mounts
# ------------------------------------------------------------------------------
# Health probes: GET /health and GET /health/database
app.include_router(health_router, prefix="/health")

# API v1 routes: /api/v1/portfolios ...
app.include_router(api_router, prefix=settings.API_V1_STR)
