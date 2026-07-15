import asyncio

import structlog

from atep.core.config import Settings
from atep.db.session import session_factory
from atep.registry.service import reconcile_expired_modules

log = structlog.get_logger()


async def run_registry_reconciler(stop_event: asyncio.Event, settings: Settings) -> None:
    while not stop_event.is_set():
        try:
            async with session_factory() as session, session.begin():
                reconciled = await reconcile_expired_modules(session)
            if reconciled:
                log.info("module_leases_reconciled", count=reconciled)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("module_lease_reconciliation_failed")

        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.module_reconciliation_interval_seconds
            )
        except TimeoutError:
            continue
