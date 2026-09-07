import hashlib
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.models import (
    AdasIntegrationEvidence,
    AdasTestScenarioExecution,
    AdasWorldScene,
)
from atep.adas.schemas import (
    AdasAlert,
    AdasDashboardSummary,
    AdasIntegrationEvidenceCreate,
    AdasIntegrationEvidenceResponse,
)
from atep.audit.service import record_audit
from atep.core.errors import (
    AdasIntegrationEvidenceConflictError,
    AdasIntegrationEvidenceContractError,
    ResourceNotFoundError,
)
from atep.events.outbox import enqueue_event
from atep.test_runs.models import TestRun
from atep.vehicles.models import VehicleCommand, VehicleTelemetryEvent


def _request_hash(command: AdasIntegrationEvidenceCreate) -> str:
    payload = command.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def integration_evidence_response(
    evidence: AdasIntegrationEvidence,
    *,
    scene: AdasWorldScene,
    scenario: AdasTestScenarioExecution,
    test_run: TestRun,
    duplicate: bool = False,
) -> AdasIntegrationEvidenceResponse:
    return AdasIntegrationEvidenceResponse(
        id=evidence.id,
        evidence_id=evidence.evidence_id,
        scene_id=scene.scene_id,
        scenario_execution_id=scenario.execution_id,
        test_run_id=test_run.run_id,
        telemetry_event_ids=evidence.telemetry_event_ids,
        vehicle_command_ids=evidence.vehicle_command_ids,
        carsystemui_evidence=evidence.carsystemui_evidence,
        dashboard_summary=evidence.dashboard_summary,
        duplicate=duplicate,
        requested_by_user_id=evidence.requested_by_user_id,
        created_at=evidence.created_at,
    )


async def require_integration_evidence(
    session: AsyncSession, *, scenario_execution_id: UUID
) -> AdasIntegrationEvidence:
    evidence = await session.scalar(
        select(AdasIntegrationEvidence).where(
            AdasIntegrationEvidence.scenario_execution_id == scenario_execution_id
        )
    )
    if evidence is None:
        raise ResourceNotFoundError("adas_integration_evidence")
    return evidence


async def create_integration_evidence(
    session: AsyncSession,
    *,
    scene: AdasWorldScene,
    scenario: AdasTestScenarioExecution,
    test_run: TestRun,
    telemetry_events: list[VehicleTelemetryEvent],
    vehicle_commands: list[VehicleCommand],
    command: AdasIntegrationEvidenceCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[AdasIntegrationEvidence, bool]:
    request_hash = _request_hash(command)
    existing = await session.scalar(
        select(AdasIntegrationEvidence).where(
            (AdasIntegrationEvidence.scenario_execution_id == scenario.id)
            | (AdasIntegrationEvidence.evidence_id == command.evidence_id)
        )
    )
    if existing is not None:
        if existing.scenario_execution_id == scenario.id and existing.request_hash == request_hash:
            return existing, True
        raise AdasIntegrationEvidenceConflictError()
    _validate_evidence(
        scene=scene,
        scenario=scenario,
        test_run=test_run,
        telemetry_events=telemetry_events,
        vehicle_commands=vehicle_commands,
        command=command,
    )
    alerts = [AdasAlert.model_validate(item) for item in scenario.alerts]
    summary = AdasDashboardSummary(
        scenario_status=scenario.status,
        maneuver=scenario.maneuver,
        alert_types=[item.alert_type for item in alerts],
        assertion_coverage=float(scenario.coverage["assertion_coverage"]),
        regression_fingerprint=scenario.regression_fingerprint,
        telemetry_event_count=len(telemetry_events),
        vehicle_command_count=len(vehicle_commands),
        carsystemui_evidence_count=len(command.carsystemui_evidence),
    )
    evidence = AdasIntegrationEvidence(
        scenario_execution_id=scenario.id,
        test_run_id=test_run.id,
        evidence_id=command.evidence_id,
        request_hash=request_hash,
        telemetry_event_ids=command.telemetry_event_ids,
        vehicle_command_ids=command.vehicle_command_ids,
        carsystemui_evidence=[
            item.model_dump(mode="json") for item in command.carsystemui_evidence
        ],
        dashboard_summary=summary.model_dump(mode="json"),
        requested_by_user_id=actor_user_id,
    )
    try:
        async with session.begin_nested():
            session.add(evidence)
            await session.flush()
    except IntegrityError as exc:
        raise AdasIntegrationEvidenceConflictError() from exc
    event_evidence = {
        "evidence_id": evidence.evidence_id,
        "scene_id": scene.scene_id,
        "scenario_execution_id": scenario.execution_id,
        "test_run_id": test_run.run_id,
        "scenario_status": scenario.status,
        "telemetry_event_count": len(telemetry_events),
        "vehicle_command_count": len(vehicle_commands),
        "carsystemui_evidence_count": len(command.carsystemui_evidence),
        "regression_fingerprint": scenario.regression_fingerprint,
    }
    enqueue_event(
        session,
        event_type="atep.adas.integration_evidence.created.v1",
        aggregate_type="adas_integration_evidence",
        aggregate_id=evidence.id,
        payload=event_evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="adas.integration_evidence_created",
        resource_type="adas_integration_evidence",
        resource_id=evidence.id,
        correlation_id=correlation_id,
        details=event_evidence,
    )
    return evidence, False


def _validate_evidence(
    *,
    scene: AdasWorldScene,
    scenario: AdasTestScenarioExecution,
    test_run: TestRun,
    telemetry_events: list[VehicleTelemetryEvent],
    vehicle_commands: list[VehicleCommand],
    command: AdasIntegrationEvidenceCreate,
) -> None:
    if scenario.scene_id != scene.id or test_run.run_id != command.test_run_id:
        raise AdasIntegrationEvidenceContractError("scenario or test-run identity does not match")
    if test_run.vehicle_id != scene.vehicle_id:
        raise AdasIntegrationEvidenceContractError("the test run belongs to a different vehicle")
    telemetry_ids = {item.event_id for item in telemetry_events}
    if telemetry_ids != set(command.telemetry_event_ids):
        raise AdasIntegrationEvidenceContractError("one or more telemetry events do not exist")
    if any(item.vehicle_id != scene.vehicle_id for item in telemetry_events):
        raise AdasIntegrationEvidenceContractError("telemetry belongs to a different vehicle")
    vehicle_command_ids = {item.command_id for item in vehicle_commands}
    if vehicle_command_ids != set(command.vehicle_command_ids):
        raise AdasIntegrationEvidenceContractError("one or more vehicle commands do not exist")
    if any(
        item.vehicle_id != scene.vehicle_id or item.test_run_id != test_run.run_id
        for item in vehicle_commands
    ):
        raise AdasIntegrationEvidenceContractError(
            "vehicle commands must belong to the same vehicle and test run"
        )
    if any(
        item.displayed_scenario_status.value != scenario.status
        for item in command.carsystemui_evidence
    ):
        raise AdasIntegrationEvidenceContractError(
            "CarSystemUI evidence must display the persisted scenario status"
        )
