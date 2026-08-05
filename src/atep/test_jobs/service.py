from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    ResourceNotFoundError,
    TestJobConflictError,
    TestJobStateError,
    TestJobVersionConflictError,
)
from atep.environment_profiles.models import EnvironmentProfile
from atep.events.outbox import enqueue_event
from atep.test_jobs.models import TestJob
from atep.test_jobs.schemas import TestJobCancel, TestJobCreate, TestJobStatus
from atep.test_runs.models import TestRun
from atep.test_runs.schemas import TestRunStatus
from atep.test_runs.service import test_run_event_payload
from atep.vehicles.models import Vehicle


async def create_test_job(
    session: AsyncSession,
    *,
    command: TestJobCreate,
    vehicle: Vehicle,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    environment_profile: EnvironmentProfile | None = None,
    now: datetime | None = None,
) -> tuple[TestJob, bool]:
    existing = await session.scalar(select(TestJob).where(TestJob.job_id == command.job_id))
    if existing is not None:
        if not _same_creation(existing, command, vehicle, environment_profile, actor_user_id):
            raise TestJobConflictError()
        return existing, True
    conflicting_job = await session.scalar(
        select(TestJob.id).where(TestJob.run_id == command.run_id)
    )
    existing_run = await session.scalar(select(TestRun.id).where(TestRun.run_id == command.run_id))
    if conflicting_job is not None or existing_run is not None:
        raise TestJobConflictError()

    created_at = now or datetime.now(UTC)
    snapshot = _profile_snapshot(environment_profile)
    job = TestJob(
        job_id=command.job_id,
        run_id=command.run_id,
        vehicle_id=vehicle.id,
        requested_by_user_id=actor_user_id,
        environment_profile_id=environment_profile.id if environment_profile else None,
        environment_profile_version=environment_profile.version if environment_profile else None,
        environment_snapshot=snapshot,
        name=command.name,
        suite=command.suite.value,
        metadata_=command.metadata,
        scheduled_for=command.scheduled_for,
        status=TestJobStatus.SCHEDULED.value,
        version=1,
        test_run_id=None,
        dispatched_at=None,
        cancelled_at=None,
        cancellation_reason=None,
        created_at=created_at,
        updated_at=created_at,
    )
    try:
        async with session.begin_nested():
            session.add(job)
            await session.flush()
    except IntegrityError as exc:
        raise TestJobConflictError() from exc
    payload = test_job_event_payload(job, vehicle.identifier)
    enqueue_event(
        session,
        event_type="atep.test_job.scheduled.v1",
        aggregate_type="test_job",
        aggregate_id=job.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="test_job.scheduled",
        resource_type="test_job",
        resource_id=job.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return job, False


async def require_test_job(
    session: AsyncSession, job_id: str, *, for_update: bool = False
) -> tuple[TestJob, Vehicle]:
    query = (
        select(TestJob, Vehicle)
        .join(Vehicle, Vehicle.id == TestJob.vehicle_id)
        .where(TestJob.job_id == job_id)
    )
    if for_update:
        query = query.with_for_update(of=TestJob)
    row = (await session.execute(query)).one_or_none()
    if row is None:
        raise ResourceNotFoundError("test_job")
    return row.tuple()


async def list_test_jobs(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: TestJobStatus | None = None,
    vehicle_identifier: str | None = None,
) -> tuple[list[tuple[TestJob, Vehicle]], int]:
    query = select(TestJob, Vehicle).join(Vehicle, Vehicle.id == TestJob.vehicle_id)
    if status is not None:
        query = query.where(TestJob.status == status.value)
    if vehicle_identifier is not None:
        query = query.where(Vehicle.identifier == vehicle_identifier)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.order_by(TestJob.scheduled_for, TestJob.id).limit(limit).offset(offset)
    )
    return [row.tuple() for row in rows.all()], int(total or 0)


async def cancel_test_job(
    session: AsyncSession,
    *,
    job: TestJob,
    vehicle: Vehicle,
    command: TestJobCancel,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[TestJob, bool]:
    if job.status == TestJobStatus.CANCELLED.value and job.cancellation_reason == command.reason:
        return job, True
    if command.expected_version != job.version:
        raise TestJobVersionConflictError(current_version=job.version)
    if job.status != TestJobStatus.SCHEDULED.value:
        raise TestJobStateError(current_status=job.status, requested_status="cancelled")
    changed_at = now or datetime.now(UTC)
    job.status = TestJobStatus.CANCELLED.value
    job.version += 1
    job.cancelled_at = changed_at
    job.cancellation_reason = command.reason
    job.updated_at = changed_at
    await session.flush()
    payload = test_job_event_payload(job, vehicle.identifier)
    enqueue_event(
        session,
        event_type="atep.test_job.cancelled.v1",
        aggregate_type="test_job",
        aggregate_id=job.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="test_job.cancelled",
        resource_type="test_job",
        resource_id=job.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return job, False


async def dispatch_due_test_jobs(
    session: AsyncSession, *, now: datetime | None = None, limit: int = 20
) -> int:
    dispatched_at = now or datetime.now(UTC)
    rows = await session.execute(
        select(TestJob, Vehicle)
        .join(Vehicle, Vehicle.id == TestJob.vehicle_id)
        .where(
            TestJob.status == TestJobStatus.SCHEDULED.value,
            TestJob.scheduled_for <= dispatched_at,
        )
        .order_by(TestJob.scheduled_for, TestJob.id)
        .limit(limit)
        .with_for_update(of=TestJob, skip_locked=True)
    )
    count = 0
    for job, vehicle in rows.all():
        test_run = TestRun(
            run_id=job.run_id,
            vehicle_id=job.vehicle_id,
            requested_by_user_id=job.requested_by_user_id,
            environment_profile_id=job.environment_profile_id,
            environment_profile_version=job.environment_profile_version,
            environment_snapshot=job.environment_snapshot,
            name=job.name,
            suite=job.suite,
            metadata_=job.metadata_,
            status=TestRunStatus.QUEUED.value,
            progress_percent=0,
            version=1,
            summary=None,
            started_at=None,
            completed_at=None,
            created_at=dispatched_at,
            updated_at=dispatched_at,
        )
        session.add(test_run)
        await session.flush()
        job.status = TestJobStatus.DISPATCHED.value
        job.version += 1
        job.test_run_id = test_run.id
        job.dispatched_at = dispatched_at
        job.updated_at = dispatched_at
        run_payload = test_run_event_payload(test_run, vehicle.identifier)
        job_payload = test_job_event_payload(job, vehicle.identifier)
        enqueue_event(
            session,
            event_type="atep.test_run.created.v1",
            aggregate_type="test_run",
            aggregate_id=test_run.id,
            payload=run_payload,
        )
        enqueue_event(
            session,
            event_type="atep.test_job.dispatched.v1",
            aggregate_type="test_job",
            aggregate_id=job.id,
            payload=job_payload,
        )
        record_audit(
            session,
            actor_user_id=None,
            action="test_job.dispatched",
            resource_type="test_job",
            resource_id=job.id,
            correlation_id=None,
            details=job_payload,
        )
        count += 1
    await session.flush()
    return count


def test_job_event_payload(job: TestJob, vehicle_identifier: str) -> dict[str, object]:
    return {
        "job_id": job.job_id,
        "run_id": job.run_id,
        "vehicle_id": vehicle_identifier,
        "requested_by_user_id": str(job.requested_by_user_id),
        "environment_profile_id": (
            job.environment_snapshot.get("profile_id") if job.environment_snapshot else None
        ),
        "environment_profile_version": job.environment_profile_version,
        "environment_snapshot": job.environment_snapshot,
        "name": job.name,
        "suite": job.suite,
        "metadata": job.metadata_,
        "scheduled_for": job.scheduled_for.isoformat(),
        "status": job.status,
        "version": job.version,
        "test_run_id": str(job.test_run_id) if job.test_run_id else None,
        "dispatched_at": job.dispatched_at.isoformat() if job.dispatched_at else None,
        "cancelled_at": job.cancelled_at.isoformat() if job.cancelled_at else None,
        "cancellation_reason": job.cancellation_reason,
    }


def _profile_snapshot(profile: EnvironmentProfile | None) -> dict[str, object] | None:
    if profile is None:
        return None
    return {
        "profile_id": profile.profile_id,
        "name": profile.name,
        "vehicle_kind": profile.vehicle_kind,
        "property_source": profile.property_source,
        "configuration": profile.configuration,
    }


def _same_creation(
    job: TestJob,
    command: TestJobCreate,
    vehicle: Vehicle,
    profile: EnvironmentProfile | None,
    actor_user_id: UUID,
) -> bool:
    return (
        job.run_id == command.run_id
        and job.vehicle_id == vehicle.id
        and job.requested_by_user_id == actor_user_id
        and job.environment_profile_id == (profile.id if profile else None)
        and job.name == command.name
        and job.suite == command.suite.value
        and job.metadata_ == command.metadata
        and job.scheduled_for == command.scheduled_for
    )
