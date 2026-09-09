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
    CrossPlatformAutomationConflictError,
    CrossPlatformAutomationContractError,
)
from atep.cross_platform_automation.schemas import AutomationReportCreate
from atep.cross_platform_automation.service import create_report
from atep.events.models import OutboxEvent
from atep.fault_campaigns.models import FaultCampaignExecution
from atep.mutation_analysis.models import MutationExecution
from atep.registry.models import ModuleCapability, PlatformModule
from atep.test_runs.models import TestRun as CatalogRun
from atep.vehicles.models import Vehicle, VehicleCommand, VehicleTelemetryEvent


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
    def __init__(self, *scalar_values: Any) -> None:
        self.scalar_values = list(scalar_values)
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    def begin_nested(self) -> NestedTransaction:
        return NestedTransaction()

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()


NOW = datetime(2026, 9, 9, 14, 0, tzinfo=UTC)


def context() -> tuple[
    Vehicle,
    CatalogRun,
    PlatformModule,
    list[VehicleTelemetryEvent],
    list[VehicleCommand],
    FaultCampaignExecution,
    MutationExecution,
]:
    vehicle = Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP EV",
        model="Reference",
        description="",
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )
    run = CatalogRun(
        id=uuid4(),
        run_id="catalog-run-001",
        vehicle_id=vehicle.id,
        requested_by_user_id=uuid4(),
        name="Cross-platform regression",
        suite="regression",
        metadata_={},
        status="passed",
        progress_percent=100,
        version=4,
        summary="Passed",
        started_at=NOW,
        completed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    gateway = PlatformModule(
        id=uuid4(),
        name="vehicle-gateway-001",
        display_name="Vehicle Gateway",
        description="",
        version="1.0.0",
        base_url=None,
        status="healthy",
        last_seen_at=NOW,
        lease_expires_at=NOW,
        lease_duration_seconds=60,
        heartbeat_token_hash=None,
        created_at=NOW,
        updated_at=NOW,
    )
    gateway.capabilities = [
        ModuleCapability(
            id=uuid4(),
            module_id=gateway.id,
            name=name,
            version="v1",
            description="",
            created_at=NOW,
            updated_at=NOW,
        )
        for name in ("vehicle.telemetry.publish", "vehicle.commands.consume")
    ]
    telemetry = [
        VehicleTelemetryEvent(
            id=uuid4(),
            event_id="telemetry-event-001",
            vehicle_id=vehicle.id,
            source_module_id=gateway.id,
            source="android-automotive",
            property_name="battery_temperature",
            value=48.0,
            unit="celsius",
            observed_at=NOW,
            created_at=NOW,
        )
    ]
    commands = [
        VehicleCommand(
            id=uuid4(),
            command_id="vehicle-command-001",
            vehicle_id=vehicle.id,
            target_module_id=gateway.id,
            requested_by_user_id=uuid4(),
            test_run_id=run.run_id,
            kind="set_property",
            payload={},
            status="succeeded",
            attempt_count=1,
            available_at=NOW,
            leased_until=None,
            lease_token_hash=None,
            completed_at=NOW,
            result={},
            error_code=None,
            error_message=None,
            created_at=NOW,
            updated_at=NOW,
        )
    ]
    fault = FaultCampaignExecution(
        id=uuid4(),
        execution_id="fault-execution-001",
        campaign_id=uuid4(),
        campaign_version=2,
        campaign_snapshot={},
        vehicle_id=vehicle.id,
        test_run_id=run.id,
        requested_by_user_id=uuid4(),
        seed=42,
        dry_run=False,
        metadata_={},
        status="passed",
        progress_percent=100,
        version=5,
        summary="Recovered",
        started_at=NOW,
        completed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    mutation = MutationExecution(
        id=uuid4(),
        execution_id="mutation-run-001",
        campaign_id=uuid4(),
        campaign_version=2,
        campaign_snapshot={},
        vehicle_id=vehicle.id,
        test_run_id=run.id,
        requested_by_user_id=uuid4(),
        status="passed",
        total_mutants=2,
        completed_mutants=2,
        killed_mutants=1,
        survived_mutants=1,
        mutation_score=0.5,
        version=5,
        started_at=NOW,
        completed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    return vehicle, run, gateway, telemetry, commands, fault, mutation


def command(gateway_id) -> AutomationReportCreate:  # type: ignore[no-untyped-def]
    return AutomationReportCreate(
        report_id="automation-report-001",
        vehicle_id="vehicle-001",
        test_run_id="catalog-run-001",
        gateway_module_id=gateway_id,
        fault_execution_id="fault-execution-001",
        mutation_execution_id="mutation-run-001",
        telemetry_event_ids=["telemetry-event-001"],
        vehicle_command_ids=["vehicle-command-001"],
        carsystemui_observations=[
            {
                "observation_id": "ui-observation-001",
                "surface": "test_detail",
                "connection_state": "connected",
                "displayed_run_status": "passed",
                "displayed_run_version": 4,
                "client_version": "1.0.0",
                "captured_at": NOW,
                "evidence_ref": "artifact://carsystemui-screenshot",
            }
        ],
    )


def test_schema_requires_timezone_unique_ids_and_bounded_evidence() -> None:
    _, _, gateway, *_ = context()
    payload = command(gateway.id).model_dump()
    payload["carsystemui_observations"][0]["captured_at"] = datetime(2026, 9, 9)
    with pytest.raises(ValidationError, match="UTC offset"):
        AutomationReportCreate(**payload)
    payload = command(gateway.id).model_dump()
    payload["telemetry_event_ids"] *= 2
    with pytest.raises(ValidationError, match="unique"):
        AutomationReportCreate(**payload)


@pytest.mark.asyncio
async def test_report_correlates_all_platforms_and_minimizes_events() -> None:
    vehicle, run, gateway, telemetry, commands, fault, mutation = context()
    actor = uuid4()
    session = FakeSession(None)
    report, duplicate = await create_report(
        cast(AsyncSession, session),
        command=command(gateway.id),
        vehicle=vehicle,
        test_run=run,
        gateway=gateway,
        telemetry_events=telemetry,
        vehicle_commands=commands,
        fault_execution=fault,
        mutation_execution=mutation,
        actor_user_id=actor,
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert report.outcome == "passed"
    assert report.summary["mutation_score"] == 0.5
    assert report.summary["connected_observation_count"] == 1
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    assert event.event_type == "atep.cross_platform_automation.report.created.v1"
    assert event.payload["telemetry_event_count"] == 1
    assert "carsystemui_observations" not in event.payload
    assert (
        next(item for item in session.added if isinstance(item, AuditRecord)).action
        == "cross_platform_automation.report_created"
    )

    report.created_by_user_id = actor
    replay, duplicate = await create_report(
        cast(AsyncSession, FakeSession(report)),
        command=command(gateway.id),
        vehicle=vehicle,
        test_run=run,
        gateway=gateway,
        telemetry_events=telemetry,
        vehicle_commands=commands,
        fault_execution=fault,
        mutation_execution=mutation,
        actor_user_id=actor,
        correlation_id=None,
    )
    assert replay is report
    assert duplicate is True


@pytest.mark.asyncio
async def test_report_rejects_cross_vehicle_or_stale_ui_evidence() -> None:
    vehicle, run, gateway, telemetry, commands, fault, mutation = context()
    stale = command(gateway.id)
    stale.carsystemui_observations[0].displayed_run_version = 3
    with pytest.raises(CrossPlatformAutomationContractError) as error:
        await create_report(
            cast(AsyncSession, FakeSession(None)),
            command=stale,
            vehicle=vehicle,
            test_run=run,
            gateway=gateway,
            telemetry_events=telemetry,
            vehicle_commands=commands,
            fault_execution=fault,
            mutation_execution=mutation,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert "status and version" in str(error.value.details)

    telemetry[0].vehicle_id = uuid4()
    with pytest.raises(CrossPlatformAutomationContractError) as error:
        await create_report(
            cast(AsyncSession, FakeSession(None)),
            command=command(gateway.id),
            vehicle=vehicle,
            test_run=run,
            gateway=gateway,
            telemetry_events=telemetry,
            vehicle_commands=commands,
            fault_execution=fault,
            mutation_execution=mutation,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert "vehicle and selected gateway" in str(error.value.details)


@pytest.mark.asyncio
async def test_report_rejects_changed_replay_and_incomplete_gateway() -> None:
    vehicle, run, gateway, telemetry, commands, fault, mutation = context()
    existing, _ = await create_report(
        cast(AsyncSession, FakeSession(None)),
        command=command(gateway.id),
        vehicle=vehicle,
        test_run=run,
        gateway=gateway,
        telemetry_events=telemetry,
        vehicle_commands=commands,
        fault_execution=fault,
        mutation_execution=mutation,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    changed = command(gateway.id)
    changed.carsystemui_observations[0].client_version = "1.0.1"
    with pytest.raises(CrossPlatformAutomationConflictError):
        await create_report(
            cast(AsyncSession, FakeSession(existing)),
            command=changed,
            vehicle=vehicle,
            test_run=run,
            gateway=gateway,
            telemetry_events=telemetry,
            vehicle_commands=commands,
            fault_execution=fault,
            mutation_execution=mutation,
            actor_user_id=uuid4(),
            correlation_id=None,
        )

    gateway.capabilities = gateway.capabilities[:1]
    with pytest.raises(CrossPlatformAutomationContractError) as error:
        await create_report(
            cast(AsyncSession, FakeSession(None)),
            command=command(gateway.id),
            vehicle=vehicle,
            test_run=run,
            gateway=gateway,
            telemetry_events=telemetry,
            vehicle_commands=commands,
            fault_execution=fault,
            mutation_execution=mutation,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert "publish telemetry and consume vehicle commands" in str(error.value.details)


@pytest.mark.asyncio
async def test_report_derives_failed_outcome_and_requires_terminal_components() -> None:
    vehicle, run, gateway, telemetry, commands, fault, mutation = context()
    mutation.status = "failed"
    report, _ = await create_report(
        cast(AsyncSession, FakeSession(None)),
        command=command(gateway.id),
        vehicle=vehicle,
        test_run=run,
        gateway=gateway,
        telemetry_events=telemetry,
        vehicle_commands=commands,
        fault_execution=fault,
        mutation_execution=mutation,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert report.outcome == "failed"

    run.status = "running"
    with pytest.raises(CrossPlatformAutomationContractError) as error:
        await create_report(
            cast(AsyncSession, FakeSession(None)),
            command=command(gateway.id),
            vehicle=vehicle,
            test_run=run,
            gateway=gateway,
            telemetry_events=telemetry,
            vehicle_commands=commands,
            fault_execution=fault,
            mutation_execution=mutation,
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert "must be terminal" in str(error.value.details)
