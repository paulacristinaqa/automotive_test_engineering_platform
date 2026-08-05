import asyncio

import structlog

from atep.core.config import Settings
from atep.db.session import session_factory
from atep.test_jobs.service import dispatch_due_test_jobs

log = structlog.get_logger()


async def run_test_scheduler(stop_event: asyncio.Event, settings: Settings) -> None:
    while not stop_event.is_set():
        try:
            async with session_factory() as session, session.begin():
                dispatched = await dispatch_due_test_jobs(
                    session, limit=settings.test_scheduler_batch_size
                )
            if dispatched:
                log.info("test_jobs_dispatched", count=dispatched)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("test_job_dispatch_failed")
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.test_scheduler_interval_seconds
            )
        except TimeoutError:
            continue
