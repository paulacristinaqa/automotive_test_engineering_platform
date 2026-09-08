from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    ResourceNotFoundError,
    TestCaseResultStateError,
    TestCaseResultVersionConflictError,
    TestCatalogStateError,
    TestRunConflictError,
    TestRunStateError,
    TestRunVersionConflictError,
)
from atep.environment_profiles.models import EnvironmentProfile
from atep.events.outbox import enqueue_event
from atep.test_catalog.models import TestSuite
from atep.test_catalog.schemas import CatalogStatus
from atep.test_runs.models import TestCaseResult, TestRun
from atep.test_runs.schemas import (
    TestCaseResultResponse,
    TestCaseResultUpdate,
    TestCaseStatus,
    TestRunCreate,
    TestRunStatus,
    TestRunStatusUpdate,
)
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
    catalog_suite: TestSuite | None = None,
) -> tuple[TestRun, bool]:
    existing = await session.scalar(select(TestRun).where(TestRun.run_id == command.run_id))
    if existing is not None:
        if not _same_creation(
            existing, command, vehicle, environment_profile, catalog_suite, actor_user_id
        ):
            raise TestRunConflictError()
        return existing, True

    if catalog_suite is not None and catalog_suite.status != CatalogStatus.ACTIVE.value:
        raise TestCatalogStateError(current_status=catalog_suite.status, requested_status="execute")

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
        catalog_suite_id=catalog_suite.id if catalog_suite else None,
        catalog_suite_version=catalog_suite.version if catalog_suite else None,
        catalog_suite_snapshot=(
            {
                "suite_id": catalog_suite.suite_id,
                "name": catalog_suite.name,
                "suite_type": catalog_suite.suite_type,
                "cases": catalog_suite.composition,
            }
            if catalog_suite
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
            if catalog_suite is not None:
                for case in catalog_suite.composition:
                    session.add(
                        TestCaseResult(
                            test_run_id=test_run.id,
                            case_id=str(case["definition_id"]),
                            definition_id=str(case["definition_id"]),
                            definition_version=int(case["definition_version"]),
                            order=int(case["order"]),
                            required=bool(case["required"]),
                            status=TestCaseStatus.PENDING.value,
                            attempt=0,
                            duration_ms=None,
                            observed=None,
                            evidence_refs=[],
                            version=1,
                            created_at=created_at,
                            updated_at=created_at,
                        )
                    )
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

    if test_run.catalog_suite_id is not None and command.status is not TestRunStatus.CANCELLED:
        raise TestRunStateError(
            current_status=test_run.status, requested_status=command.status.value
        )

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
        "catalog_suite_id": (
            test_run.catalog_suite_snapshot.get("suite_id")
            if test_run.catalog_suite_snapshot is not None
            else None
        ),
        "catalog_suite_version": test_run.catalog_suite_version,
        "catalog_case_count": (
            len(test_run.catalog_suite_snapshot.get("cases", []))
            if test_run.catalog_suite_snapshot is not None
            else 0
        ),
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
    catalog_suite: TestSuite | None,
    actor_user_id: UUID,
) -> bool:
    return (
        existing.vehicle_id == vehicle.id
        and existing.environment_profile_id
        == (environment_profile.id if environment_profile else None)
        and existing.catalog_suite_id == (catalog_suite.id if catalog_suite else None)
        and existing.requested_by_user_id == actor_user_id
        and existing.name == command.name
        and existing.suite == command.suite.value
        and existing.metadata_ == command.metadata
    )


async def require_catalog_suite(session: AsyncSession, suite_id: str) -> TestSuite:
    suite = await session.scalar(select(TestSuite).where(TestSuite.suite_id == suite_id))
    if suite is None:
        raise ResourceNotFoundError("test_suite")
    return suite


async def list_case_results(
    session: AsyncSession, *, test_run: TestRun, limit: int, offset: int
) -> tuple[list[TestCaseResult], int]:
    query = select(TestCaseResult).where(TestCaseResult.test_run_id == test_run.id)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(TestCaseResult.order, TestCaseResult.id).limit(limit).offset(offset)
    )
    return list(rows), int(total or 0)


async def require_case_result(
    session: AsyncSession, *, test_run: TestRun, case_id: str, for_update: bool = False
) -> TestCaseResult:
    query = select(TestCaseResult).where(
        TestCaseResult.test_run_id == test_run.id, TestCaseResult.case_id == case_id
    )
    if for_update:
        query = query.with_for_update()
    result = await session.scalar(query)
    if result is None:
        raise ResourceNotFoundError("test_case_result")
    return result


CASE_TRANSITIONS = {
    TestCaseStatus.PENDING: {TestCaseStatus.RUNNING, TestCaseStatus.SKIPPED},
    TestCaseStatus.RUNNING: {
        TestCaseStatus.PASSED,
        TestCaseStatus.FAILED,
        TestCaseStatus.SKIPPED,
    },
    TestCaseStatus.PASSED: set(),
    TestCaseStatus.FAILED: set(),
    TestCaseStatus.SKIPPED: set(),
}


async def update_case_result(
    session: AsyncSession,
    *,
    test_run: TestRun,
    vehicle: Vehicle,
    result: TestCaseResult,
    command: TestCaseResultUpdate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[TestCaseResult, bool]:
    if _same_case_result(result, command):
        return result, True
    if test_run.status in {
        TestRunStatus.PASSED.value,
        TestRunStatus.FAILED.value,
        TestRunStatus.CANCELLED.value,
    }:
        raise TestRunStateError(
            current_status=test_run.status, requested_status="record_case_result"
        )
    if command.expected_version != result.version:
        raise TestCaseResultVersionConflictError(current_version=result.version)
    current = TestCaseStatus(result.status)
    if command.status not in CASE_TRANSITIONS[current]:
        raise TestCaseResultStateError(
            current_status=current.value, requested_status=command.status.value
        )
    changed_at = now or datetime.now(UTC)
    previous_status = result.status
    result.status = command.status.value
    result.attempt = command.attempt
    result.duration_ms = command.duration_ms
    result.observed = command.observed
    result.evidence_refs = command.evidence_refs
    result.version += 1
    result.updated_at = changed_at
    await session.flush()
    await _refresh_run_aggregate(session, test_run, changed_at)
    payload = {
        "run_id": test_run.run_id,
        "vehicle_id": vehicle.identifier,
        "case_id": result.case_id,
        "definition_id": result.definition_id,
        "definition_version": result.definition_version,
        "required": result.required,
        "previous_status": previous_status,
        "status": result.status,
        "attempt": result.attempt,
        "duration_ms": result.duration_ms,
        "evidence_count": len(result.evidence_refs),
        "version": result.version,
    }
    enqueue_event(
        session,
        event_type="atep.test_case.result_recorded.v1",
        aggregate_type="test_case_result",
        aggregate_id=result.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="test_case.result_recorded",
        resource_type="test_case_result",
        resource_id=result.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return result, False


async def _refresh_run_aggregate(
    session: AsyncSession, test_run: TestRun, changed_at: datetime
) -> None:
    results = list(
        await session.scalars(
            select(TestCaseResult).where(TestCaseResult.test_run_id == test_run.id)
        )
    )
    terminal = {"passed", "failed", "skipped"}
    complete = sum(item.status in terminal for item in results)
    total = len(results)
    test_run.progress_percent = (
        100 if total and complete == total else min(99, complete * 100 // total)
    )
    if test_run.status == TestRunStatus.QUEUED.value:
        test_run.status = TestRunStatus.RUNNING.value
        test_run.started_at = changed_at
    if total and complete == total:
        failed = any(item.required and item.status in {"failed", "skipped"} for item in results)
        test_run.status = TestRunStatus.FAILED.value if failed else TestRunStatus.PASSED.value
        test_run.completed_at = changed_at
        test_run.summary = f"{complete} of {total} catalog cases completed"
    test_run.version += 1
    test_run.updated_at = changed_at
    await session.flush()


def case_result_response(result: TestCaseResult, run_id: str) -> TestCaseResultResponse:
    return TestCaseResultResponse(
        id=result.id,
        run_id=run_id,
        case_id=result.case_id,
        definition_id=result.definition_id,
        definition_version=result.definition_version,
        order=result.order,
        required=result.required,
        status=result.status,
        attempt=result.attempt,
        duration_ms=result.duration_ms,
        observed=result.observed,
        evidence_refs=result.evidence_refs,
        version=result.version,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


def _same_case_result(result: TestCaseResult, command: TestCaseResultUpdate) -> bool:
    return (
        result.status == command.status.value
        and result.attempt == command.attempt
        and result.duration_ms == command.duration_ms
        and result.observed == command.observed
        and result.evidence_refs == command.evidence_refs
    )


def _same_status(test_run: TestRun, command: TestRunStatusUpdate) -> bool:
    return (
        test_run.status == command.status.value
        and test_run.progress_percent == command.progress_percent
        and test_run.summary == command.summary
    )
