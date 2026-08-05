from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    ResourceNotFoundError,
    TestRunConflictError,
    TestRunStateError,
    TestRunVersionConflictError,
)
from atep.environment_profiles.models import EnvironmentProfile
from atep.events.outbox import enqueue_event
from atep.test_runs.models import TestRun
from atep.test_runs.schemas import TestRunCreate, TestRunStatus, TestRunStatusUpdate
from atep.vehicles.models import Vehicle

ALLOWED_TRANSITIONS = {
    TestRunStatus.QUEUED: {TestRunStatus.RUNNING, TestRunStatus.CANCELLED},
    TestRunStatus.RUNNING: {
        TestRunStatus.PASSED,
        TestRunStatus.FAILED,
        TestRunStatus.CANCELLED,
    },
    TestRunStatus.PASSED: set(),
    TestRunStatus.FAILED: set(),
    TestRunStatus.CANCELLED: set(),
}


async def create_test_run(
    session: AsyncSession,
    *,
    command: TestRunCreate,
    vehicle: Vehicle,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
    environment_profile: EnvironmentProfile | None = None,
) -> tuple[TestRun, bool]:
    existing = await session.scalar(select(TestRun).where(TestRun.run_id == command.run_id))
    if existing is not None:
        if not _same_creation(existing, command, vehicle, environment_profile, actor_user_id):
            raise TestRunConflictError()
        return existing, True

    # A scheduled job reserves its target run identifier until dispatch. The local import
    # avoids coupling model import order while preserving one public identifier namespace.
    from atep.test_jobs.models import TestJob

    reserved_run_id = await session.scalar(
        select(TestJob.id).where(TestJob.run_id == command.run_id)
    )
    if reserved_run_id is not None:
        raise TestRunConflictError()

    created_at = now or datetime.now(UTC)
    test_run = TestRun(
        run_id=command.run_id,
        vehicle_id=vehicle.id,
        requested_by_user_id=actor_user_id,
        environment_profile_id=environment_profile.id if environment_profile else None,
        environment_profile_version=environment_profile.version if environment_profile else None,
        environment_snapshot=(
            {
                "profile_id": environment_profile.profile_id,
                "name": environment_profile.name,
                "vehicle_kind": environment_profile.vehicle_kind,
                "property_source": environment_profile.property_source,
                "configuration": environment_profile.configuration,
            }
            if environment_profile
            else None
        ),
        name=command.name,
        suite=command.suite.value,
        metadata_=command.metadata,
        status=TestRunStatus.QUEUED.value,
        progress_percent=0,
        version=1,
        summary=None,
        started_at=None,
        completed_at=None,
        created_at=created_at,
        updated_at=created_at,
    )
    try:
        async with session.begin_nested():
            session.add(test_run)
            await session.flush()
    except IntegrityError as exc:
        raise TestRunConflictError() from exc

    payload = test_run_event_payload(test_run, vehicle.identifier)
    enqueue_event(
        session,
        event_type="atep.test_run.created.v1",
        aggregate_type="test_run",
        aggregate_id=test_run.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="test_run.created",
        resource_type="test_run",
        resource_id=test_run.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return test_run, False


async def require_test_run(
    session: AsyncSession, run_id: str, *, for_update: bool = False
) -> tuple[TestRun, Vehicle]:
    query = (
        select(TestRun, Vehicle)
        .join(Vehicle, Vehicle.id == TestRun.vehicle_id)
        .where(TestRun.run_id == run_id)
    )
    if for_update:
        query = query.with_for_update(of=TestRun)
    row = (await session.execute(query)).one_or_none()
    if row is None:
        raise ResourceNotFoundError("test_run")
    return row.tuple()


async def list_test_runs(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: TestRunStatus | None = None,
    vehicle_identifier: str | None = None,
) -> tuple[list[tuple[TestRun, Vehicle]], int]:
    query = select(TestRun, Vehicle).join(Vehicle, Vehicle.id == TestRun.vehicle_id)
    if status is not None:
        query = query.where(TestRun.status == status.value)
    if vehicle_identifier is not None:
        query = query.where(Vehicle.identifier == vehicle_identifier)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(
        query.order_by(TestRun.created_at.desc(), TestRun.id.desc()).limit(limit).offset(offset)
    )
    return [row.tuple() for row in rows.all()], int(total or 0)


async def update_test_run_status(
    session: AsyncSession,
    *,
    test_run: TestRun,
    vehicle: Vehicle,
    command: TestRunStatusUpdate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[TestRun, bool]:
    if _same_status(test_run, command):
        return test_run, True
    if command.expected_version != test_run.version:
        raise TestRunVersionConflictError(current_version=test_run.version)

    current = TestRunStatus(test_run.status)
    if command.status not in ALLOWED_TRANSITIONS[current]:
        raise TestRunStateError(current_status=current.value, requested_status=command.status.value)

    changed_at = now or datetime.now(UTC)
    previous_status = test_run.status
    test_run.status = command.status.value
    test_run.progress_percent = command.progress_percent
    test_run.summary = command.summary
    test_run.version += 1
    test_run.updated_at = changed_at
    if command.status is TestRunStatus.RUNNING and test_run.started_at is None:
        test_run.started_at = changed_at
    if command.status in {
        TestRunStatus.PASSED,
        TestRunStatus.FAILED,
        TestRunStatus.CANCELLED,
    }:
        test_run.completed_at = changed_at
    await session.flush()

    payload = {
        **test_run_event_payload(test_run, vehicle.identifier),
        "previous_status": previous_status,
    }
    enqueue_event(
        session,
        event_type="atep.test_run.status_changed.v1",
        aggregate_type="test_run",
        aggregate_id=test_run.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="test_run.status_changed",
        resource_type="test_run",
        resource_id=test_run.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return test_run, False


def test_run_event_payload(test_run: TestRun, vehicle_identifier: str) -> dict[str, object]:
    return {
        "run_id": test_run.run_id,
        "vehicle_id": vehicle_identifier,
        "requested_by_user_id": str(test_run.requested_by_user_id),
        "environment_profile_id": (
            test_run.environment_snapshot.get("profile_id")
            if test_run.environment_snapshot is not None
            else None
        ),
        "environment_profile_version": test_run.environment_profile_version,
        "environment_snapshot": test_run.environment_snapshot,
        "name": test_run.name,
        "suite": test_run.suite,
        "metadata": test_run.metadata_,
        "status": test_run.status,
        "progress_percent": test_run.progress_percent,
        "version": test_run.version,
        "summary": test_run.summary,
        "started_at": test_run.started_at.isoformat() if test_run.started_at else None,
        "completed_at": test_run.completed_at.isoformat() if test_run.completed_at else None,
        "created_at": test_run.created_at.isoformat(),
        "updated_at": test_run.updated_at.isoformat(),
    }


def _same_creation(
    existing: TestRun,
    command: TestRunCreate,
    vehicle: Vehicle,
    environment_profile: EnvironmentProfile | None,
    actor_user_id: UUID,
) -> bool:
    return (
        existing.vehicle_id == vehicle.id
        and existing.environment_profile_id
        == (environment_profile.id if environment_profile else None)
        and existing.requested_by_user_id == actor_user_id
        and existing.name == command.name
        and existing.suite == command.suite.value
        and existing.metadata_ == command.metadata
    )


def _same_status(test_run: TestRun, command: TestRunStatusUpdate) -> bool:
    return (
        test_run.status == command.status.value
        and test_run.progress_percent == command.progress_percent
        and test_run.summary == command.summary
    )
