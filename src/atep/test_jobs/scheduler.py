import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.config import Settings
from atep.core.observability import Observability
from atep.db.session import session_factory
from atep.test_jobs.models import TestJob
from atep.test_jobs.schemas import TestJobStatus
from atep.test_jobs.service import dispatch_due_test_jobs

log = structlog.get_logger()


@dataclass(frozen=True)
class DueTestJobBacklog:
    count: int
    oldest_age_seconds: float


async def measure_due_test_jobs(
    session: AsyncSession, *, now: datetime | None = None
) -> DueTestJobBacklog:
    observed_at = now or datetime.now(UTC)
    result = await session.execute(
        select(func.count(), func.min(TestJob.scheduled_for)).where(
            TestJob.status == TestJobStatus.SCHEDULED.value,
            TestJob.scheduled_for <= observed_at,
        )
    )
    count, oldest_scheduled_for = result.one()
    oldest_age = (
        max(0.0, (observed_at - oldest_scheduled_for).total_seconds())
        if oldest_scheduled_for is not None
        else 0.0
    )
    return DueTestJobBacklog(count=int(count), oldest_age_seconds=oldest_age)


async def run_test_scheduler(
    stop_event: asyncio.Event, settings: Settings, observability: Observability
) -> None:
    while not stop_event.is_set():
        started_at = time.perf_counter()
        try:
            async with session_factory() as session, session.begin():
                dispatched = await dispatch_due_test_jobs(
                    session, limit=settings.test_scheduler_batch_size
                )
                backlog = await measure_due_test_jobs(session)
            observability.test_jobs_dispatched.inc(dispatched)
            observability.update_test_job_backlog(
                count=backlog.count, oldest_age_seconds=backlog.oldest_age_seconds
            )
            if dispatched:
                log.info("test_jobs_dispatched", count=dispatched)
        except asyncio.CancelledError:
            raise
        except Exception:
            observability.test_scheduler_errors.inc()
            log.exception("test_job_dispatch_failed")
        finally:
            observability.test_scheduler_cycle_duration.observe(time.perf_counter() - started_at)
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=settings.test_scheduler_interval_seconds
            )
        except TimeoutError:
            continue
