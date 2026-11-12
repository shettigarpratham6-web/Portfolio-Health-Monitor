"""
Portfolio Health Monitor
Asynchronous PostgreSQL Database Connection & Session Management
"""

import logging
import time
from typing import Any, AsyncGenerator, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger("agentx.database")
settings = get_settings()

# ------------------------------------------------------------------------------
# Asynchronous Engine Configuration with Connection Pooling
# ------------------------------------------------------------------------------
# pool_pre_ping=True: Tests connections before checkout to prevent stale socket errors
# pool_recycle=1800: Recycles connections every 30 minutes to prevent server-side disconnects
engine: AsyncEngine = create_async_engine(
    url=settings.async_database_url,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={
        "server_settings": {
            "application_name": "agentx_backend",
        }
    },
)

# ------------------------------------------------------------------------------
# Asynchronous Session Factory
# ------------------------------------------------------------------------------
# expire_on_commit=False: Avoids unexpected lazy-loading attributes after commit in async contexts
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ------------------------------------------------------------------------------
# FastAPI Database Dependency
# ------------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an asynchronous SQLAlchemy session.
    Automatically commits successful transactions, rolls back on exceptions,
    and guarantees proper session cleanup.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("Transaction rolled back due to exception: %s", exc)
            raise
        finally:
            await session.close()


# ------------------------------------------------------------------------------
# Database Health Check
# ------------------------------------------------------------------------------
async def check_db_health() -> Dict[str, Any]:
    """
    Executes a lightweight query (SELECT 1) to verify PostgreSQL connectivity.
    Measures latency and returns diagnostic information without raising unhandled exceptions.
    """
    start_time = time.perf_counter()
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            val = result.scalar()
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

            if val == 1:
                return {
                    "status": "healthy",
                    "database": "postgresql",
                    "connected": True,
                    "latency_ms": latency_ms,
                }
            return {
                "status": "degraded",
                "database": "postgresql",
                "connected": True,
                "latency_ms": latency_ms,
                "detail": f"Unexpected response from ping query: {val}",
            }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.warning("Database connectivity health check failed: %s", exc)
        return {
            "status": "unhealthy",
            "database": "postgresql",
            "connected": False,
            "latency_ms": latency_ms,
            "error": str(exc),
        }


# ------------------------------------------------------------------------------
# Clean Connection Shutdown
# ------------------------------------------------------------------------------
async def close_db_connection() -> None:
    """
    Disposes of the connection pool and terminates existing pooled connections.
    Should be called during application lifespan shutdown.
    """
    if engine is not None:
        logger.info("Closing PostgreSQL connection pool...")
        await engine.dispose()
        logger.info("PostgreSQL connection pool disposed.")

