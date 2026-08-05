from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import TestJobStateError as JobStateError
from atep.core.errors import TestJobVersionConflictError as JobVersionConflictError
from atep.events.models import OutboxEvent
from atep.test_jobs.models import TestJob as JobRecord
from atep.test_jobs.schemas import TestJobCancel as JobCancel
from atep.test_jobs.schemas import TestJobCreate as JobCreate
from atep.test_jobs.service import cancel_test_job, create_test_job, dispatch_due_test_jobs
from atep.test_runs.models import TestRun as RunRecord
from atep.vehicles.models import Vehicle


class NestedTransaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class Rows:
    def __init__(self, values: list[tuple[Any, ...]]) -> None:
        self.values = values

    def all(self) -> list[tuple[Any, ...]]:
        return self.values


class FakeSession:
    def __init__(self, *scalar_values: Any, rows: list[tuple[Any, ...]] | None = None) -> None:
        self.scalar_values = list(scalar_values)
        self.rows = rows or []
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def execute(self, _: Any) -> Rows:
        return Rows(self.rows)

    def begin_nested(self) -> NestedTransaction:
        return NestedTransaction()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()


NOW = datetime(2026, 8, 5, 10, 0, tzinfo=UTC)


def vehicle() -> Vehicle:
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP Development Vehicle",
        model="EV Reference Platform",
        description="",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )


def command() -> JobCreate:
    return JobCreate(
        job_id="job-battery-0001",
        run_id="run-battery-0001",
        vehicle_id="vehicle-001",
        name="Battery thermal scheduled smoke",
        suite="smoke",
        metadata={"requirement": "ATEP-JOB-001"},
        scheduled_for=NOW + timedelta(minutes=5),
    )


def scheduled_job(target: Vehicle) -> JobRecord:
    return JobRecord(
        id=uuid4(),
        job_id="job-battery-0001",
        run_id="run-battery-0001",
        vehicle_id=target.id,
        requested_by_user_id=uuid4(),
        environment_profile_id=None,
        environment_profile_version=None,
        environment_snapshot=None,
        name="Battery thermal scheduled smoke",
        suite="smoke",
        metadata_={"requirement": "ATEP-JOB-001"},
        scheduled_for=NOW - timedelta(seconds=1),
        status="scheduled",
        version=1,
        test_run_id=None,
        dispatched_at=None,
        cancelled_at=None,
        cancellation_reason=None,
        created_at=NOW - timedelta(minutes=5),
        updated_at=NOW - timedelta(minutes=5),
    )


def test_schedule_contract_requires_timezone_and_bounded_identifier() -> None:
    payload = command().model_dump()
    payload["scheduled_for"] = datetime(2026, 8, 5, 10, 5)
    with pytest.raises(ValidationError, match="timezone offset"):
        JobCreate(**payload)
    payload = command().model_dump()
    payload["job_id"] = "short"
    with pytest.raises(ValidationError, match="8 characters"):
        JobCreate(**payload)


@pytest.mark.asyncio
async def test_creation_is_idempotent_audited_and_evented() -> None:
    target = vehicle()
    actor_id = uuid4()
    session = FakeSession(None, None, None)
    created, duplicate = await create_test_job(
        cast(AsyncSession, session),
        command=command(),
        vehicle=target,
        actor_user_id=actor_id,
        correlation_id=uuid4(),
        now=NOW,
    )
    assert duplicate is False
    assert created.status == "scheduled"
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.test_job.scheduled.v1"
    ]
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "test_job.scheduled"
    ]

    retry_session = FakeSession(created)
    returned, duplicate = await create_test_job(
        cast(AsyncSession, retry_session),
        command=command(),
        vehicle=target,
        actor_user_id=actor_id,
        correlation_id=None,
    )
    assert returned is created
    assert duplicate is True
    assert retry_session.added == []


@pytest.mark.asyncio
async def test_cancel_is_versioned_idempotent_and_rejects_dispatched_job() -> None:
    target = vehicle()
    job = scheduled_job(target)
    session = FakeSession()
    cancelled, duplicate = await cancel_test_job(
        cast(AsyncSession, session),
        job=job,
        vehicle=target,
        command=JobCancel(expected_version=1, reason="No longer required"),
        actor_user_id=uuid4(),
        correlation_id=None,
        now=NOW,
    )
    assert duplicate is False
    assert cancelled.status == "cancelled"
    assert cancelled.version == 2

    returned, duplicate = await cancel_test_job(
        cast(AsyncSession, FakeSession()),
        job=job,
        vehicle=target,
        command=JobCancel(expected_version=1, reason="No longer required"),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is job
    assert duplicate is True

    other = scheduled_job(target)
    with pytest.raises(JobVersionConflictError):
        await cancel_test_job(
            cast(AsyncSession, FakeSession()),
            job=other,
            vehicle=target,
            command=JobCancel(expected_version=2),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    other.status = "dispatched"
    with pytest.raises(JobStateError):
        await cancel_test_job(
            cast(AsyncSession, FakeSession()),
            job=other,
            vehicle=target,
            command=JobCancel(expected_version=1),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_due_dispatch_creates_run_and_atomic_evidence() -> None:
    target = vehicle()
    job = scheduled_job(target)
    session = FakeSession(rows=[(job, target)])
    count = await dispatch_due_test_jobs(cast(AsyncSession, session), now=NOW, limit=10)
    assert count == 1
    assert job.status == "dispatched"
    assert job.version == 2
    created_runs = [item for item in session.added if isinstance(item, RunRecord)]
    assert len(created_runs) == 1
    assert created_runs[0].run_id == job.run_id
    assert job.test_run_id == created_runs[0].id
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.test_run.created.v1",
        "atep.test_job.dispatched.v1",
    ]
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "test_job.dispatched"
    ]
