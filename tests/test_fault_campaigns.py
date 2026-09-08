from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import (
    FaultCampaignStateError,
    FaultStepStateError,
    FaultStepVersionConflictError,
)
from atep.events.models import OutboxEvent
from atep.fault_campaigns.models import FaultCampaign, FaultCampaignExecution, FaultStepResult
from atep.fault_campaigns.schemas import (
    FaultCampaignCreate,
    FaultCampaignStatusUpdate,
    FaultExecutionCancel,
    FaultExecutionCreate,
    FaultStepResultUpdate,
)
from atep.fault_campaigns.service import (
    cancel_execution,
    create_campaign,
    create_execution,
    update_campaign_status,
    update_step_result,
)
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


class ScalarRows:
    def __init__(self, values: list[Any]) -> None:
        self.values = values

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.values)


class FakeSession:
    def __init__(
        self,
        *scalar_values: Any,
        scalar_rows: list[list[Any]] | None = None,
    ) -> None:
        self.scalar_values = list(scalar_values)
        self.scalar_rows = list(scalar_rows or [])
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    async def scalars(self, _: Any) -> ScalarRows:
        values = self.scalar_rows.pop(0) if self.scalar_rows else []
        return ScalarRows(values)

    def begin_nested(self) -> NestedTransaction:
        return NestedTransaction()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    async def refresh(self, _: Any, *, attribute_names: list[str]) -> None:
        assert attribute_names == ["updated_at"]


NOW = datetime(2026, 9, 8, 14, 0, tzinfo=UTC)


def campaign_command() -> FaultCampaignCreate:
    return FaultCampaignCreate(
        campaign_id="battery-thermal-fault",
        name="Battery thermal protection campaign",
        description="Inject and recover a bounded battery temperature fault.",
        blast_radius="single_component",
        tags=["Battery", "Regression"],
        steps=[
            {
                "step_id": "inject-temperature",
                "order": 1,
                "domain": "electric_vehicle",
                "action": "battery_overtemperature",
                "target_id": "battery-pack-main",
                "parameters": {"temperature_celsius": 48.0},
                "duration_ms": 5_000,
                "expected_effect": "BMS warning and diagnostic evidence are produced",
                "recovery": {
                    "action": "restore nominal thermal state",
                    "timeout_ms": 10_000,
                    "verification": "Battery temperature returns below the warning threshold",
                },
            }
        ],
    )


def campaign(*, status: str = "active") -> FaultCampaign:
    command = campaign_command()
    return FaultCampaign(
        id=uuid4(),
        campaign_id=command.campaign_id,
        created_by_user_id=uuid4(),
        name=command.name,
        description=command.description,
        blast_radius=command.blast_radius.value,
        steps=[item.model_dump(mode="json") for item in command.steps],
        tags=command.tags,
        status=status,
        version=2 if status == "active" else 1,
        created_at=NOW,
        updated_at=NOW,
    )


def vehicle() -> Vehicle:
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP EV",
        model="EV Reference Platform",
        description="",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )


def execution_command() -> FaultExecutionCreate:
    return FaultExecutionCreate(
        execution_id="fault-execution-0001",
        vehicle_id="vehicle-001",
        seed=42,
        dry_run=False,
        metadata={"requirement": "TF-F-035"},
    )


def execution(target: Vehicle, source: FaultCampaign) -> FaultCampaignExecution:
    return FaultCampaignExecution(
        id=uuid4(),
        execution_id="fault-execution-0001",
        campaign_id=source.id,
        campaign_version=source.version,
        campaign_snapshot={
            "campaign_id": source.campaign_id,
            "name": source.name,
            "blast_radius": source.blast_radius,
            "steps": source.steps,
            "tags": source.tags,
            "test_run_id": None,
        },
        vehicle_id=target.id,
        test_run_id=None,
        requested_by_user_id=uuid4(),
        seed=42,
        dry_run=False,
        metadata_={"requirement": "TF-F-035"},
        status="queued",
        progress_percent=0,
        version=1,
        summary=None,
        started_at=None,
        completed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def step_result(run: FaultCampaignExecution) -> FaultStepResult:
    return FaultStepResult(
        id=uuid4(),
        execution_id=run.id,
        step_id="inject-temperature",
        order=1,
        domain="electric_vehicle",
        action="battery_overtemperature",
        target_id="battery-pack-main",
        required=True,
        status="pending",
        attempt=0,
        duration_ms=None,
        observed_effect=None,
        evidence_refs=[],
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.parametrize(
    ("domain", "action"),
    [
        ("digital_vehicle", "sensor_stuck"),
        ("ecu", "ecu_memory_corruption"),
        ("can", "can_frame_drop"),
        ("diagnostics", "diagnostic_timeout"),
        ("electric_vehicle", "charging_fault"),
        ("adas", "perception_dropout"),
    ],
)
def test_all_completed_domains_have_allowlisted_actions(domain: str, action: str) -> None:
    payload = campaign_command().model_dump()
    payload["steps"][0]["domain"] = domain
    payload["steps"][0]["action"] = action
    assert FaultCampaignCreate(**payload).steps[0].action.value == action


def test_campaign_contract_rejects_cross_domain_actions_and_unsafe_budgets() -> None:
    payload = campaign_command().model_dump()
    payload["steps"][0]["domain"] = "adas"
    with pytest.raises(ValidationError, match="not allowed"):
        FaultCampaignCreate(**payload)

    payload = campaign_command().model_dump()
    payload["steps"][0]["duration_ms"] = 600_000
    payload["steps"][0]["recovery"]["timeout_ms"] = 600_000
    payload["steps"].append({**payload["steps"][0], "step_id": "second-step", "order": 2})
    with pytest.raises(ValidationError, match="1800000"):
        FaultCampaignCreate(**payload)


@pytest.mark.asyncio
async def test_campaign_creation_is_idempotent_audited_and_evented() -> None:
    actor = uuid4()
    session = FakeSession(None)
    created, duplicate = await create_campaign(
        cast(AsyncSession, session),
        command=campaign_command(),
        actor_user_id=actor,
        correlation_id=uuid4(),
        now=NOW,
    )
    assert duplicate is False
    assert created.status == "draft"
    assert created.tags == ["battery", "regression"]
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    assert [item.event_type for item in events] == ["atep.fault_campaign.created.v1"]
    assert events[0].payload["domains"] == ["electric_vehicle"]
    assert events[0].payload["budget_ms"] == 15_000
    assert len(cast(str, events[0].payload["snapshot_fingerprint"])) == 64
    assert [item.action for item in session.added if isinstance(item, AuditRecord)] == [
        "fault_campaign.created"
    ]

    retry = FakeSession(created)
    returned, duplicate = await create_campaign(
        cast(AsyncSession, retry),
        command=campaign_command(),
        actor_user_id=actor,
        correlation_id=None,
    )
    assert returned is created
    assert duplicate is True
    assert retry.added == []


@pytest.mark.asyncio
async def test_campaign_lifecycle_is_forward_only_and_versioned() -> None:
    source = campaign(status="draft")
    source.version = 1
    updated, duplicate = await update_campaign_status(
        cast(AsyncSession, FakeSession()),
        campaign=source,
        command=FaultCampaignStatusUpdate(expected_version=1, status="active"),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is False
    assert updated.status == "active"
    assert updated.version == 2

    with pytest.raises(FaultCampaignStateError):
        await update_campaign_status(
            cast(AsyncSession, FakeSession()),
            campaign=updated,
            command=FaultCampaignStatusUpdate(expected_version=2, status="draft"),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_execution_snapshots_campaign_and_materializes_pending_steps() -> None:
    source = campaign()
    target = vehicle()
    actor = uuid4()
    session = FakeSession(None)
    created, duplicate = await create_execution(
        cast(AsyncSession, session),
        campaign=source,
        command=execution_command(),
        vehicle=target,
        test_run=None,
        actor_user_id=actor,
        correlation_id=None,
        now=NOW,
    )
    assert duplicate is False
    assert created.status == "queued"
    assert created.campaign_version == 2
    result = next(item for item in session.added if isinstance(item, FaultStepResult))
    assert result.step_id == "inject-temperature"
    assert result.status == "pending"
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.event_type == "atep.fault_campaign.execution.requested.v1"
    assert event.payload["step_count"] == 1
    assert "campaign_snapshot" not in event.payload

    source.steps[0]["parameters"]["temperature_celsius"] = 99.0
    assert created.campaign_snapshot["steps"][0]["parameters"]["temperature_celsius"] == 48.0


@pytest.mark.asyncio
async def test_inactive_campaign_rejects_new_execution_but_exact_replay_survives_archive() -> None:
    source = campaign(status="archived")
    target = vehicle()
    actor = uuid4()
    with pytest.raises(FaultCampaignStateError):
        await create_execution(
            cast(AsyncSession, FakeSession(None)),
            campaign=source,
            command=execution_command(),
            vehicle=target,
            test_run=None,
            actor_user_id=actor,
            correlation_id=None,
        )

    existing = execution(target, source)
    existing.requested_by_user_id = actor
    returned, duplicate = await create_execution(
        cast(AsyncSession, FakeSession(existing)),
        campaign=source,
        command=execution_command(),
        vehicle=target,
        test_run=None,
        actor_user_id=actor,
        correlation_id=None,
    )
    assert returned is existing
    assert duplicate is True


@pytest.mark.asyncio
async def test_step_lifecycle_recovers_and_derives_execution_outcome() -> None:
    source = campaign()
    target = vehicle()
    run = execution(target, source)
    result = step_result(run)
    actor = uuid4()
    statuses = ["injecting", "injected", "recovering", "recovered"]
    for index, status in enumerate(statuses, start=1):
        command = FaultStepResultUpdate(
            expected_version=index,
            status=status,
            attempt=1,
            duration_ms=2_000 if status == "recovered" else None,
            observed_effect="Recovered" if status == "recovered" else status,
            evidence_refs=["telemetry://battery-temperature"] if status == "recovered" else [],
        )
        session = FakeSession(scalar_rows=[[result]])
        returned, duplicate = await update_step_result(
            cast(AsyncSession, session),
            execution=run,
            campaign=source,
            vehicle=target,
            result=result,
            command=command,
            actor_user_id=actor,
            correlation_id=None,
            now=NOW,
        )
        assert returned is result
        assert duplicate is False

    assert run.status == "passed"
    assert run.progress_percent == 100
    assert run.completed_at == NOW
    assert result.status == "recovered"
    assert result.version == 5
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    assert events[0].payload["evidence_count"] == 1
    assert "evidence_refs" not in events[0].payload


@pytest.mark.asyncio
async def test_step_rejects_invalid_transition_and_execution_can_be_cancelled() -> None:
    source = campaign()
    target = vehicle()
    run = execution(target, source)
    result = step_result(run)
    with pytest.raises(FaultStepStateError):
        await update_step_result(
            cast(AsyncSession, FakeSession()),
            execution=run,
            campaign=source,
            vehicle=target,
            result=result,
            command=FaultStepResultUpdate(
                expected_version=1,
                status="recovered",
                attempt=1,
                duration_ms=1,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )

    cancelled, duplicate = await cancel_execution(
        cast(AsyncSession, FakeSession()),
        execution=run,
        campaign=source,
        vehicle=target,
        command=FaultExecutionCancel(expected_version=1, reason="Safety stop"),
        actor_user_id=uuid4(),
        correlation_id=None,
        now=NOW,
    )
    assert duplicate is False
    assert cancelled.status == "cancelled"
    assert cancelled.summary == "Safety stop"


@pytest.mark.asyncio
async def test_required_failure_fails_execution_and_optional_failure_does_not() -> None:
    source = campaign()
    target = vehicle()
    for required, expected in ((True, "failed"), (False, "passed")):
        run = execution(target, source)
        result = step_result(run)
        result.required = required
        result.status = "injecting"
        results = [result]
        if not required:
            recovered = step_result(run)
            recovered.id = uuid4()
            recovered.step_id = "required-recovered"
            recovered.required = True
            recovered.status = "recovered"
            results.append(recovered)
        await update_step_result(
            cast(AsyncSession, FakeSession(scalar_rows=[results])),
            execution=run,
            campaign=source,
            vehicle=target,
            result=result,
            command=FaultStepResultUpdate(
                expected_version=1,
                status="failed",
                attempt=1,
                duration_ms=10,
                observed_effect="Injection adapter rejected the request",
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
            now=NOW,
        )
        assert run.status == expected
        assert run.progress_percent == 100


@pytest.mark.asyncio
async def test_stale_step_version_is_rejected() -> None:
    source = campaign()
    target = vehicle()
    run = execution(target, source)
    result = step_result(run)
    result.version = 2
    with pytest.raises(FaultStepVersionConflictError):
        await update_step_result(
            cast(AsyncSession, FakeSession()),
            execution=run,
            campaign=source,
            vehicle=target,
            result=result,
            command=FaultStepResultUpdate(
                expected_version=1,
                status="injecting",
                attempt=1,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
