"""
Portfolio Health Monitor
API Routes Assembly
"""

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.portfolios import router as portfolios_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(portfolios_router)

__all__ = [
    "api_router",
    "auth_router",
    "health_router",
    "portfolios_router",
]

