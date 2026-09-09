import hashlib
import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    CrossPlatformAutomationConflictError,
    CrossPlatformAutomationContractError,
    ResourceNotFoundError,
)
from atep.cross_platform_automation.models import CrossPlatformAutomationReport
from atep.cross_platform_automation.schemas import (
    AutomationOutcome,
    AutomationReportCreate,
    AutomationReportResponse,
    AutomationReportSummary,
    ConnectionState,
)
from atep.events.outbox import enqueue_event
from atep.fault_campaigns.models import FaultCampaignExecution
from atep.mutation_analysis.models import MutationExecution
from atep.registry.models import PlatformModule
from atep.test_runs.models import TestRun
from atep.vehicles.models import Vehicle, VehicleCommand, VehicleTelemetryEvent

TERMINAL_RUN_STATUSES = {"passed", "failed", "cancelled"}
TERMINAL_FAULT_STATUSES = {"passed", "failed", "cancelled"}
TERMINAL_MUTATION_STATUSES = {"passed", "failed", "cancelled"}
GATEWAY_CAPABILITIES = {"vehicle.telemetry.publish", "vehicle.commands.consume"}


def _request_hash(command: AutomationReportCreate) -> str:
    encoded = json.dumps(
        command.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def report_response(
    report: CrossPlatformAutomationReport,
    *,
    vehicle: Vehicle,
    test_run: TestRun,
    fault_execution: FaultCampaignExecution | None,
    mutation_execution: MutationExecution | None,
    duplicate: bool = False,
) -> AutomationReportResponse:
    return AutomationReportResponse(
        id=report.id,
        report_id=report.report_id,
        vehicle_id=vehicle.identifier,
        test_run_id=test_run.run_id,
        gateway_module_id=report.gateway_module_id,
        fault_execution_id=fault_execution.execution_id if fault_execution else None,
        mutation_execution_id=mutation_execution.execution_id if mutation_execution else None,
        telemetry_event_ids=report.telemetry_event_ids,
        vehicle_command_ids=report.vehicle_command_ids,
        carsystemui_observations=report.carsystemui_observations,
        outcome=report.outcome,
        summary=report.summary,
        duplicate=duplicate,
        created_by_user_id=report.created_by_user_id,
        created_at=report.created_at,
    )


async def create_report(
    session: AsyncSession,
    *,
    command: AutomationReportCreate,
    vehicle: Vehicle,
    test_run: TestRun,
    gateway: PlatformModule,
    telemetry_events: list[VehicleTelemetryEvent],
    vehicle_commands: list[VehicleCommand],
    fault_execution: FaultCampaignExecution | None,
    mutation_execution: MutationExecution | None,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[CrossPlatformAutomationReport, bool]:
    request_hash = _request_hash(command)
    existing = await session.scalar(
        select(CrossPlatformAutomationReport).where(
            (CrossPlatformAutomationReport.report_id == command.report_id)
            | (CrossPlatformAutomationReport.test_run_id == test_run.id)
        )
    )
    if existing is not None:
        if existing.report_id == command.report_id and existing.request_hash == request_hash:
            return existing, True
        raise CrossPlatformAutomationConflictError()

    _validate_report(
        command=command,
        vehicle=vehicle,
        test_run=test_run,
        gateway=gateway,
        telemetry_events=telemetry_events,
        vehicle_commands=vehicle_commands,
        fault_execution=fault_execution,
        mutation_execution=mutation_execution,
    )
    outcome = _outcome(test_run, fault_execution, mutation_execution)
    summary = AutomationReportSummary(
        test_run_status=test_run.status,
        test_run_version=test_run.version,
        fault_execution_status=fault_execution.status if fault_execution else None,
        mutation_execution_status=mutation_execution.status if mutation_execution else None,
        mutation_score=mutation_execution.mutation_score if mutation_execution else None,
        telemetry_event_count=len(telemetry_events),
        vehicle_command_count=len(vehicle_commands),
        carsystemui_observation_count=len(command.carsystemui_observations),
        connected_observation_count=sum(
            item.connection_state is ConnectionState.CONNECTED
            for item in command.carsystemui_observations
        ),
    )
    report = CrossPlatformAutomationReport(
        report_id=command.report_id,
        request_hash=request_hash,
        vehicle_id=vehicle.id,
        test_run_id=test_run.id,
        gateway_module_id=gateway.id,
        fault_execution_id=fault_execution.id if fault_execution else None,
        mutation_execution_id=mutation_execution.id if mutation_execution else None,
        telemetry_event_ids=command.telemetry_event_ids,
        vehicle_command_ids=command.vehicle_command_ids,
        carsystemui_observations=[
            item.model_dump(mode="json") for item in command.carsystemui_observations
        ],
        outcome=outcome.value,
        summary=summary.model_dump(mode="json"),
        created_by_user_id=actor_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(report)
            await session.flush()
    except IntegrityError as exc:
        raise CrossPlatformAutomationConflictError() from exc

    evidence = {
        "report_id": report.report_id,
        "vehicle_id": vehicle.identifier,
        "test_run_id": test_run.run_id,
        "gateway_module_id": str(gateway.id),
        "fault_execution_id": fault_execution.execution_id if fault_execution else None,
        "mutation_execution_id": mutation_execution.execution_id if mutation_execution else None,
        "outcome": outcome.value,
        "test_run_status": test_run.status,
        "telemetry_event_count": len(telemetry_events),
        "vehicle_command_count": len(vehicle_commands),
        "carsystemui_observation_count": len(command.carsystemui_observations),
    }
    enqueue_event(
        session,
        event_type="atep.cross_platform_automation.report.created.v1",
        aggregate_type="cross_platform_automation_report",
        aggregate_id=report.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="cross_platform_automation.report_created",
        resource_type="cross_platform_automation_report",
        resource_id=report.id,
        details=evidence,
        correlation_id=correlation_id,
    )
    return report, False


def _validate_report(
    *,
    command: AutomationReportCreate,
    vehicle: Vehicle,
    test_run: TestRun,
    gateway: PlatformModule,
    telemetry_events: list[VehicleTelemetryEvent],
    vehicle_commands: list[VehicleCommand],
    fault_execution: FaultCampaignExecution | None,
    mutation_execution: MutationExecution | None,
) -> None:
    if command.fault_execution_id is not None and fault_execution is None:
        raise CrossPlatformAutomationContractError("the fault execution does not exist")
    if command.mutation_execution_id is not None and mutation_execution is None:
        raise CrossPlatformAutomationContractError("the mutation execution does not exist")
    if test_run.vehicle_id != vehicle.id or test_run.run_id != command.test_run_id:
        raise CrossPlatformAutomationContractError("the test run belongs to a different vehicle")
    if test_run.status not in TERMINAL_RUN_STATUSES:
        raise CrossPlatformAutomationContractError("the test run must be terminal")
    capabilities = {item.name for item in gateway.capabilities}
    if not GATEWAY_CAPABILITIES.issubset(capabilities):
        raise CrossPlatformAutomationContractError(
            "the gateway must publish telemetry and consume vehicle commands"
        )
    if {item.event_id for item in telemetry_events} != set(command.telemetry_event_ids):
        raise CrossPlatformAutomationContractError("one or more telemetry events do not exist")
    if any(
        item.vehicle_id != vehicle.id or item.source_module_id != gateway.id
        for item in telemetry_events
    ):
        raise CrossPlatformAutomationContractError(
            "telemetry must belong to the vehicle and selected gateway"
        )
    if {item.command_id for item in vehicle_commands} != set(command.vehicle_command_ids):
        raise CrossPlatformAutomationContractError("one or more vehicle commands do not exist")
    if any(
        item.vehicle_id != vehicle.id
        or item.target_module_id != gateway.id
        or item.test_run_id != test_run.run_id
        or item.status not in {"succeeded", "rejected"}
        for item in vehicle_commands
    ):
        raise CrossPlatformAutomationContractError(
            "vehicle commands must be terminal and belong to the vehicle, gateway, and test run"
        )
    if any(
        item.displayed_run_status.value != test_run.status
        or item.displayed_run_version != test_run.version
        for item in command.carsystemui_observations
    ):
        raise CrossPlatformAutomationContractError(
            "CarSystemUI observations must display the persisted test-run status and version"
        )
    if fault_execution is not None:
        if (
            fault_execution.vehicle_id != vehicle.id
            or fault_execution.test_run_id != test_run.id
            or fault_execution.status not in TERMINAL_FAULT_STATUSES
        ):
            raise CrossPlatformAutomationContractError(
                "fault execution must be terminal and belong to the vehicle and test run"
            )
    if mutation_execution is not None:
        if (
            mutation_execution.vehicle_id != vehicle.id
            or mutation_execution.test_run_id != test_run.id
            or mutation_execution.status not in TERMINAL_MUTATION_STATUSES
        ):
            raise CrossPlatformAutomationContractError(
                "mutation execution must be terminal and belong to the vehicle and test run"
            )


def _outcome(
    test_run: TestRun,
    fault_execution: FaultCampaignExecution | None,
    mutation_execution: MutationExecution | None,
) -> AutomationOutcome:
    statuses = [
        test_run.status,
        *(item.status for item in (fault_execution, mutation_execution) if item is not None),
    ]
    if "failed" in statuses:
        return AutomationOutcome.FAILED
    if "cancelled" in statuses:
        return AutomationOutcome.CANCELLED
    return AutomationOutcome.PASSED


async def require_report(
    session: AsyncSession, report_id: str
) -> tuple[
    CrossPlatformAutomationReport,
    Vehicle,
    TestRun,
    FaultCampaignExecution | None,
    MutationExecution | None,
]:
    row = (
        await session.execute(
            select(
                CrossPlatformAutomationReport,
                Vehicle,
                TestRun,
                FaultCampaignExecution,
                MutationExecution,
            )
            .join(Vehicle, Vehicle.id == CrossPlatformAutomationReport.vehicle_id)
            .join(TestRun, TestRun.id == CrossPlatformAutomationReport.test_run_id)
            .outerjoin(
                FaultCampaignExecution,
                FaultCampaignExecution.id == CrossPlatformAutomationReport.fault_execution_id,
            )
            .outerjoin(
                MutationExecution,
                MutationExecution.id == CrossPlatformAutomationReport.mutation_execution_id,
            )
            .where(CrossPlatformAutomationReport.report_id == report_id)
        )
    ).one_or_none()
    if row is None:
        raise ResourceNotFoundError("cross_platform_automation_report")
    return row.tuple()


async def list_reports(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    outcome: AutomationOutcome | None,
) -> tuple[
    list[
        tuple[
            CrossPlatformAutomationReport,
            Vehicle,
            TestRun,
            FaultCampaignExecution | None,
            MutationExecution | None,
        ]
    ],
    int,
]:
    filters = []
    if outcome is not None:
        filters.append(CrossPlatformAutomationReport.outcome == outcome.value)
    total = int(
        await session.scalar(
            select(func.count()).select_from(CrossPlatformAutomationReport).where(*filters)
        )
        or 0
    )
    rows = (
        await session.execute(
            select(
                CrossPlatformAutomationReport,
                Vehicle,
                TestRun,
                FaultCampaignExecution,
                MutationExecution,
            )
            .join(Vehicle, Vehicle.id == CrossPlatformAutomationReport.vehicle_id)
            .join(TestRun, TestRun.id == CrossPlatformAutomationReport.test_run_id)
            .outerjoin(
                FaultCampaignExecution,
                FaultCampaignExecution.id == CrossPlatformAutomationReport.fault_execution_id,
            )
            .outerjoin(
                MutationExecution,
                MutationExecution.id == CrossPlatformAutomationReport.mutation_execution_id,
            )
            .where(*filters)
            .order_by(CrossPlatformAutomationReport.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [row.tuple() for row in rows], total
