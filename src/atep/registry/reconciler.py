import asyncio

import structlog

from atep.core.config import Settings
from atep.core.observability import Observability
from atep.db.session import session_factory
from atep.registry.service import reconcile_expired_modules, summarize_module_health

log = structlog.get_logger()


async def run_registry_reconciler(
    stop_event: asyncio.Event, settings: Settings, observability: Observability
) -> None:
    while not stop_event.is_set():
        try:
            async with session_factory() as session, session.begin():
                reconciled = await reconcile_expired_modules(session)
                health = await summarize_module_health(
                    session,
                    availability_target=settings.module_availability_slo_target,
                    lease_warning_seconds=settings.module_lease_warning_seconds,
                )
            observability.update_module_health(
                counts=health.counts.model_dump(),
                monitored_modules=health.monitored_modules,
                availability_ratio=health.availability_ratio,
                at_risk_leases=health.at_risk_leases,
            )
            if reconciled:
                observability.module_lease_expirations.inc(reconciled)
                log.info("module_leases_reconciled", count=reconciled)
        except asyncio.CancelledError:
            raise
        except Exception:
            observability.module_reconciliation_errors.inc()
            log.exception("module_lease_reconciliation_failed")

        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.module_reconciliation_interval_seconds
            )
        except TimeoutError:
            continue
