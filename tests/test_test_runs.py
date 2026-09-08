from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import TestCaseResultStateError as CaseStateError
from atep.core.errors import TestCaseResultVersionConflictError as CaseVersionError
from atep.core.errors import TestCatalogStateError as CatalogStateError
from atep.core.errors import TestRunConflictError as RunConflictError
from atep.core.errors import TestRunStateError as RunStateError
from atep.core.errors import TestRunVersionConflictError as RunVersionConflictError
from atep.events.models import OutboxEvent
from atep.test_catalog.models import TestSuite as CatalogSuite
from atep.test_runs.models import TestCaseResult as CaseResultRecord
from atep.test_runs.models import TestRun as RunRecord
from atep.test_runs.schemas import TestCaseResultUpdate as CaseResultUpdate
from atep.test_runs.schemas import TestRunCreate as RunCreate
from atep.test_runs.schemas import TestRunStatusUpdate as RunStatusUpdate
from atep.test_runs.service import create_test_run, update_case_result, update_test_run_status
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


class FakeSession:
    def __init__(self, *scalar_values: Any, scalar_rows: list[Any] | None = None) -> None:
        self.scalar_values = list(scalar_values)
        self.scalar_rows = scalar_rows or []
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, _: Any) -> list[Any]:
        return self.scalar_rows

    def begin_nested(self) -> NestedTransaction:
        return NestedTransaction()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()


def vehicle() -> Vehicle:
    now = datetime(2026, 8, 4, 20, 0, tzinfo=UTC)
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP Development Vehicle",
        model="EV Reference Platform",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )


def contract(*, name: str = "Battery thermal smoke test") -> RunCreate:
    return RunCreate(
        run_id="01JXYZTESTRUN0001",
        vehicle_id="vehicle-001",
        name=name,
        suite="smoke",
        metadata={"requirement": "ATEP-TR-001"},
    )


def queued_run(target: Vehicle) -> RunRecord:
    now = datetime(2026, 8, 4, 20, 0, tzinfo=UTC)
    return RunRecord(
        id=uuid4(),
        run_id="01JXYZTESTRUN0001",
        vehicle_id=target.id,
        requested_by_user_id=uuid4(),
        name="Battery thermal smoke test",
        suite="smoke",
        metadata_={"requirement": "ATEP-TR-001"},
        status="queued",
        progress_percent=0,
        version=1,
        summary=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )


def test_status_contract_enforces_progress_semantics() -> None:
    with pytest.raises(ValidationError, match="zero progress"):
        RunStatusUpdate(expected_version=1, status="queued", progress_percent=1)
    with pytest.raises(ValidationError, match="between 0 and 99"):
        RunStatusUpdate(expected_version=1, status="running", progress_percent=100)
    with pytest.raises(ValidationError, match="100 percent"):
        RunStatusUpdate(expected_version=1, status="passed", progress_percent=99)


@pytest.mark.asyncio
async def test_creation_is_idempotent_audited_and_evented() -> None:
    target = vehicle()
    actor_id = uuid4()
    session = FakeSession()
    created, duplicate = await create_test_run(
        cast(AsyncSession, session),
        command=contract(),
        vehicle=target,
        actor_user_id=actor_id,
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert created.status == "queued"
    assert created.version == 1
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.test_run.created.v1"
    ]
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "test_run.created"
    ]

    retry_session = FakeSession(created)
    retried, duplicate = await create_test_run(
        cast(AsyncSession, retry_session),
        command=contract(),
        vehicle=target,
        actor_user_id=actor_id,
        correlation_id=uuid4(),
    )
    assert retried is created
    assert duplicate is True
    assert retry_session.added == []

    with pytest.raises(RunConflictError):
        await create_test_run(
            cast(AsyncSession, FakeSession(created)),
            command=contract(name="A different test"),
            vehicle=target,
            actor_user_id=actor_id,
            correlation_id=uuid4(),
        )

    with pytest.raises(RunConflictError):
        await create_test_run(
            cast(AsyncSession, FakeSession(None, uuid4())),
            command=contract(),
            vehicle=target,
            actor_user_id=actor_id,
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_transition_sets_timestamps_version_audit_and_event() -> None:
    target = vehicle()
    test_run = queued_run(target)
    changed_at = datetime(2026, 8, 4, 20, 1, tzinfo=UTC)
    session = FakeSession()
    updated, duplicate = await update_test_run_status(
        cast(AsyncSession, session),
        test_run=test_run,
        vehicle=target,
        command=RunStatusUpdate(
            expected_version=1, status="running", progress_percent=10, summary="Started"
        ),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
        now=changed_at,
    )
    assert duplicate is False
    assert updated.status == "running"
    assert updated.version == 2
    assert updated.started_at == changed_at
    assert [item.event_type for item in session.added if isinstance(item, OutboxEvent)] == [
        "atep.test_run.status_changed.v1"
    ]
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "test_run.status_changed"
    ]


@pytest.mark.asyncio
async def test_transition_rejects_stale_versions_and_illegal_states() -> None:
    target = vehicle()
    test_run = queued_run(target)
    with pytest.raises(RunVersionConflictError) as stale:
        await update_test_run_status(
            cast(AsyncSession, FakeSession()),
            test_run=test_run,
            vehicle=target,
            command=RunStatusUpdate(expected_version=2, status="running", progress_percent=1),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert stale.value.details == {"current_version": 1}

    with pytest.raises(RunStateError):
        await update_test_run_status(
            cast(AsyncSession, FakeSession()),
            test_run=test_run,
            vehicle=target,
            command=RunStatusUpdate(expected_version=1, status="passed", progress_percent=100),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_exact_status_retry_is_idempotent_even_with_stale_version() -> None:
    target = vehicle()
    test_run = queued_run(target)
    test_run.status = "running"
    test_run.progress_percent = 25
    test_run.summary = "Executing"
    test_run.version = 2
    session = FakeSession()
    returned, duplicate = await update_test_run_status(
        cast(AsyncSession, session),
        test_run=test_run,
        vehicle=target,
        command=RunStatusUpdate(
            expected_version=1, status="running", progress_percent=25, summary="Executing"
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is test_run
    assert duplicate is True
    assert session.added == []


@pytest.mark.asyncio
async def test_catalog_backed_run_status_is_derived_from_cases() -> None:
    target = vehicle()
    test_run = queued_run(target)
    test_run.catalog_suite_id = uuid4()
    with pytest.raises(RunStateError):
        await update_test_run_status(
            cast(AsyncSession, FakeSession()),
            test_run=test_run,
            vehicle=target,
            command=RunStatusUpdate(expected_version=1, status="running", progress_percent=10),
            actor_user_id=uuid4(),
            correlation_id=None,
        )

    cancelled, duplicate = await update_test_run_status(
        cast(AsyncSession, FakeSession()),
        test_run=test_run,
        vehicle=target,
        command=RunStatusUpdate(expected_version=1, status="cancelled", progress_percent=0),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is False
    assert cancelled.status == "cancelled"


def catalog_suite(actor_id: Any) -> CatalogSuite:
    now = datetime(2026, 8, 4, 19, 0, tzinfo=UTC)
    return CatalogSuite(
        id=uuid4(),
        suite_id="battery-smoke-suite",
        created_by_user_id=actor_id,
        name="Battery smoke suite",
        description="",
        suite_type="smoke",
        composition=[
            {
                "definition_id": "battery-temp-high",
                "definition_version": 2,
                "name": "High battery temperature",
                "order": 1,
                "required": True,
                "parameter_overrides": {"temperature": 48},
            }
        ],
        tags=["battery"],
        status="active",
        version=3,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_catalog_suite_is_snapshotted_and_materializes_pending_cases() -> None:
    target = vehicle()
    actor_id = uuid4()
    suite = catalog_suite(actor_id)
    command = RunCreate(
        **{**contract().model_dump(mode="json"), "catalog_suite_id": suite.suite_id}
    )
    session = FakeSession(None, None)
    created, duplicate = await create_test_run(
        cast(AsyncSession, session),
        command=command,
        vehicle=target,
        catalog_suite=suite,
        actor_user_id=actor_id,
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert created.catalog_suite_version == 3
    assert created.catalog_suite_snapshot == {
        "suite_id": "battery-smoke-suite",
        "name": "Battery smoke suite",
        "suite_type": "smoke",
        "cases": suite.composition,
    }
    cases = [item for item in session.added if isinstance(item, CaseResultRecord)]
    assert [(item.case_id, item.status, item.definition_version) for item in cases] == [
        ("battery-temp-high", "pending", 2)
    ]


@pytest.mark.asyncio
async def test_inactive_suite_blocks_new_run_but_not_exact_archived_replay() -> None:
    target = vehicle()
    actor_id = uuid4()
    suite = catalog_suite(actor_id)
    suite.status = "archived"
    command = RunCreate(
        **{**contract().model_dump(mode="json"), "catalog_suite_id": suite.suite_id}
    )
    with pytest.raises(CatalogStateError):
        await create_test_run(
            cast(AsyncSession, FakeSession(None)),
            command=command,
            vehicle=target,
            catalog_suite=suite,
            actor_user_id=actor_id,
            correlation_id=None,
        )

    existing = queued_run(target)
    existing.requested_by_user_id = actor_id
    existing.catalog_suite_id = suite.id
    replayed, duplicate = await create_test_run(
        cast(AsyncSession, FakeSession(existing)),
        command=command,
        vehicle=target,
        catalog_suite=suite,
        actor_user_id=actor_id,
        correlation_id=None,
    )
    assert replayed is existing
    assert duplicate is True


@pytest.mark.asyncio
async def test_case_results_drive_aggregate_run_status_and_atomic_evidence() -> None:
    target = vehicle()
    run = queued_run(target)
    now = datetime(2026, 8, 4, 20, 2, tzinfo=UTC)
    result = CaseResultRecord(
        id=uuid4(),
        test_run_id=run.id,
        case_id="battery-temp-high",
        definition_id="battery-temp-high",
        definition_version=2,
        order=1,
        required=True,
        status="running",
        attempt=1,
        duration_ms=None,
        observed=None,
        evidence_refs=[],
        version=2,
        created_at=now,
        updated_at=now,
    )
    session = FakeSession(scalar_rows=[result])
    updated, duplicate = await update_case_result(
        cast(AsyncSession, session),
        test_run=run,
        vehicle=target,
        result=result,
        command=CaseResultUpdate(
            expected_version=2,
            status="passed",
            attempt=1,
            duration_ms=125,
            observed="Temperature warning displayed",
            evidence_refs=["artifact://battery-warning-log"],
        ),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
        now=now,
    )
    assert duplicate is False
    assert updated.status == "passed"
    assert run.status == "passed"
    assert run.progress_percent == 100
    assert run.completed_at == now
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert [item.event_type for item in events] == ["atep.test_case.result_recorded.v1"]
    assert events[0].payload["evidence_count"] == 1
    assert "evidence_refs" not in events[0].payload
    assert [item.action for item in audits] == ["test_case.result_recorded"]


def test_case_result_contract_bounds_attempts_duration_and_evidence() -> None:
    with pytest.raises(ValidationError, match="require an attempt"):
        CaseResultUpdate(expected_version=1, status="passed", attempt=0)
    with pytest.raises(ValidationError, match="duration is accepted only"):
        CaseResultUpdate(expected_version=1, status="running", attempt=1, duration_ms=1)
    with pytest.raises(ValidationError, match="must be unique"):
        CaseResultUpdate(
            expected_version=1,
            status="passed",
            attempt=1,
            evidence_refs=["artifact://same", "artifact://same"],
        )


@pytest.mark.asyncio
async def test_case_result_rejects_stale_version_and_invalid_shortcut() -> None:
    target = vehicle()
    run = queued_run(target)
    now = datetime(2026, 8, 4, 20, 2, tzinfo=UTC)
    result = CaseResultRecord(
        id=uuid4(),
        test_run_id=run.id,
        case_id="battery-temp-high",
        definition_id="battery-temp-high",
        definition_version=2,
        order=1,
        required=True,
        status="pending",
        attempt=0,
        duration_ms=None,
        observed=None,
        evidence_refs=[],
        version=1,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(CaseVersionError):
        await update_case_result(
            cast(AsyncSession, FakeSession()),
            test_run=run,
            vehicle=target,
            result=result,
            command=CaseResultUpdate(expected_version=2, status="running", attempt=1),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    with pytest.raises(CaseStateError):
        await update_case_result(
            cast(AsyncSession, FakeSession()),
            test_run=run,
            vehicle=target,
            result=result,
            command=CaseResultUpdate(expected_version=1, status="failed", attempt=1),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
