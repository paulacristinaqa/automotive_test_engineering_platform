import asyncio
from typing import Annotated

import aio_pika
import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, status
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
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    checks: dict[str, str] = {}

    try:
        async with asyncio.timeout(2):
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ready"
    except Exception:
        checks["postgres"] = "unavailable"

    redis_client = redis.from_url(settings.redis_url)  # type: ignore[no-untyped-call]
    try:
        async with asyncio.timeout(2):
            await redis_client.ping()
        checks["redis"] = "ready"
    except Exception:
        checks["redis"] = "unavailable"
    finally:
        await redis_client.aclose()

    try:
        async with asyncio.timeout(2):
            connection = await aio_pika.connect(settings.rabbitmq_url)
            await connection.close()
        checks["rabbitmq"] = "ready"
    except Exception:
        checks["rabbitmq"] = "unavailable"

    if any(value != "ready" for value in checks.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "not_ready", "checks": checks},
        )
    return {"status": "ready", "checks": checks}
