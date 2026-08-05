import asyncio
import time
from typing import Annotated

import aio_pika
import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.config import Settings, get_settings
from atep.db.session import get_session

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    checks: dict[str, str] = {}

    started_at = time.perf_counter()
    try:
        async with asyncio.timeout(2):
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ready"
    except Exception:
        checks["postgres"] = "unavailable"
    request.app.state.observability.observe_dependency_check(
        dependency="postgres",
        outcome=checks["postgres"],
        duration_seconds=time.perf_counter() - started_at,
    )

    redis_client = redis.from_url(settings.redis_url)  # type: ignore[no-untyped-call]
    started_at = time.perf_counter()
    try:
        async with asyncio.timeout(2):
            await redis_client.ping()
        checks["redis"] = "ready"
    except Exception:
        checks["redis"] = "unavailable"
    finally:
        await redis_client.aclose()
    request.app.state.observability.observe_dependency_check(
        dependency="redis",
        outcome=checks["redis"],
        duration_seconds=time.perf_counter() - started_at,
    )

    started_at = time.perf_counter()
    try:
        async with asyncio.timeout(2):
            connection = await aio_pika.connect(settings.rabbitmq_url)
            await connection.close()
        checks["rabbitmq"] = "ready"
    except Exception:
        checks["rabbitmq"] = "unavailable"
    request.app.state.observability.observe_dependency_check(
        dependency="rabbitmq",
        outcome=checks["rabbitmq"],
        duration_seconds=time.perf_counter() - started_at,
    )

    if any(value != "ready" for value in checks.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "not_ready", "checks": checks},
        )
    return {"status": "ready", "checks": checks}
