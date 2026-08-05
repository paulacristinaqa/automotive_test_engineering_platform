import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import redis.asyncio as redis
import structlog
from fastapi import Depends, FastAPI, Request

from atep.api.health import router as health_router
from atep.audit.router import router as audit_router
from atep.core.config import get_settings
from atep.core.errors import install_exception_handlers
from atep.core.logging import configure_logging
from atep.core.rate_limit import api_rate_limit
from atep.db.session import session_factory
from atep.identity.bootstrap import ensure_bootstrap_admin
from atep.identity.roles_router import router as roles_router
from atep.identity.router import router as identity_router
from atep.identity.users_router import router as users_router
from atep.registry.reconciler import run_registry_reconciler
from atep.registry.router import router as registry_router
from atep.vehicles.router import router as vehicles_router

settings = get_settings()
configure_logging(settings.log_level)
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    async with session_factory() as session, session.begin():
        created = await ensure_bootstrap_admin(session, settings)
    if created:
        log.info("bootstrap_administrator_created")
    redis_client = redis.from_url(settings.redis_url)  # type: ignore[no-untyped-call]
    application.state.redis = redis_client
    reconciler_stop = asyncio.Event()
    reconciler_task: asyncio.Task[None] | None = None
    if settings.module_reconciliation_enabled:
        reconciler_task = asyncio.create_task(run_registry_reconciler(reconciler_stop, settings))
    try:
        yield
    finally:
        reconciler_stop.set()
        if reconciler_task is not None:
            await reconciler_task
        await redis_client.aclose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Control plane for the Automotive Test Engineering Platform.",
    lifespan=lifespan,
)
app.include_router(health_router)
rate_limited = [Depends(api_rate_limit)]
app.include_router(identity_router, prefix="/api/v1", dependencies=rate_limited)
app.include_router(users_router, prefix="/api/v1", dependencies=rate_limited)
app.include_router(roles_router, prefix="/api/v1", dependencies=rate_limited)
app.include_router(audit_router, prefix="/api/v1", dependencies=rate_limited)
app.include_router(registry_router, prefix="/api/v1", dependencies=rate_limited)
app.include_router(vehicles_router, prefix="/api/v1", dependencies=rate_limited)
install_exception_handlers(app)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    requested_id = request.headers.get("X-Correlation-ID")
    try:
        correlation_id = UUID(requested_id) if requested_id else uuid4()
    except ValueError:
        correlation_id = uuid4()

    request.state.correlation_id = correlation_id

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        correlation_id=str(correlation_id),
        method=request.method,
        path=request.url.path,
    )
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = str(correlation_id)
    return response
