import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.adas.integration_service import create_integration_evidence
from atep.adas.models import AdasIntegrationEvidence, AdasTestScenarioExecution, AdasWorldScene
from atep.adas.schemas import (
    AdasDashboardSummary,
    AdasIntegrationEvidenceCreate,
    AdasTestRunEvidenceStreamEvent,
)
from atep.audit.models import AuditRecord
from atep.core.errors import (
    AdasIntegrationEvidenceConflictError,
    AdasIntegrationEvidenceContractError,
)
from atep.events.models import OutboxEvent
from atep.test_runs.models import TestRun as RunRecord
from atep.test_runs.realtime import publish_test_run_message
from atep.vehicles.models import VehicleCommand, VehicleTelemetryEvent


class FakeSession:
    def __init__(self, existing: AdasIntegrationEvidence | None = None) -> None:
        self.existing = existing
        self.added: list[Any] = []

    async def scalar(self, _query: Any) -> Any:
        return self.existing

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    @asynccontextmanager
    async def begin_nested(self) -> AsyncIterator[None]:
        yield


class FakeRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> None:
        if self.fail:
            raise ConnectionError("Redis unavailable")
        self.messages.append((channel, payload))


def fixtures() -> tuple[
    AdasWorldScene,
    AdasTestScenarioExecution,
    RunRecord,
    VehicleTelemetryEvent,
    VehicleCommand,
]:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    vehicle_id = uuid4()
    scene = AdasWorldScene(
        id=uuid4(),
        vehicle_id=vehicle_id,
        scene_id="integration-scene-001",
        name="Integration scene",
        coordinate_frame={},
        roads=[],
        actors=[],
        environment={},
        traffic_controls=[],
        revision=1,
        simulation_time_ms=0,
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    scenario = AdasTestScenarioExecution(
        id=uuid4(),
        scene_id=scene.id,
        perception_result_id=uuid4(),
        execution_id="adas-scenario-001",
        scenario_type="aeb_car_to_car",
        scene_revision=1,
        request_hash="a" * 64,
        status="passed",
        maneuver="emergency_brake",
        alerts=[
            {
                "alert_type": "forward_collision",
                "severity": "critical",
                "message": "Forward collision risk detected.",
            }
        ],
        assertions=[],
        fault_injections=[],
        coverage={"assertion_coverage": 1.0},
        regression_fingerprint="b" * 64,
        requested_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )
    test_run = RunRecord(
        id=uuid4(),
        run_id="adas-test-run-001",
        vehicle_id=vehicle_id,
        requested_by_user_id=uuid4(),
        name="ADAS integration",
        suite="regression",
        metadata_={},
        status="running",
        progress_percent=80,
        version=2,
        created_at=now,
        updated_at=now,
    )
    telemetry = VehicleTelemetryEvent(
        id=uuid4(),
        event_id="telemetry-event-001",
        vehicle_id=vehicle_id,
        source_module_id=uuid4(),
        source="android-automotive",
        property_name="vehicle_speed",
        value=0,
        unit="mps",
        observed_at=now,
        created_at=now,
    )
    vehicle_command = VehicleCommand(
        id=uuid4(),
        command_id="gateway-command-001",
        vehicle_id=vehicle_id,
        target_module_id=uuid4(),
        requested_by_user_id=uuid4(),
        test_run_id=test_run.run_id,
        kind="set_property",
        payload={},
        status="succeeded",
        attempt_count=1,
        available_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    return scene, scenario, test_run, telemetry, vehicle_command


def command() -> AdasIntegrationEvidenceCreate:
    return AdasIntegrationEvidenceCreate(
        evidence_id="integration-evidence-001",
        test_run_id="adas-test-run-001",
        telemetry_event_ids=["telemetry-event-001"],
        vehicle_command_ids=["gateway-command-001"],
        carsystemui_evidence=[
            {
                "event_id": "carsystemui-event-001",
                "surface": "adas_alerts",
                "connection_state": "connected",
                "displayed_scenario_status": "passed",
                "client_version": "1.0.0",
                "captured_at": "2026-09-07T12:00:00Z",
            }
        ],
    )


def test_integration_contract_requires_evidence_timezone_and_unique_ids() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        AdasIntegrationEvidenceCreate(
            evidence_id="integration-evidence-001", test_run_id="adas-test-run-001"
        )
    invalid = command().model_dump(mode="json")
    invalid["carsystemui_evidence"][0]["captured_at"] = "2026-09-07T12:00:00"
    with pytest.raises(ValidationError, match="UTC offset"):
        AdasIntegrationEvidenceCreate.model_validate(invalid)
    invalid_reference = command().model_dump(mode="json")
    invalid_reference["telemetry_event_ids"] = ["bad identifier"]
    with pytest.raises(ValidationError, match="String should match pattern"):
        AdasIntegrationEvidenceCreate.model_validate(invalid_reference)


@pytest.mark.asyncio
async def test_cross_platform_evidence_is_correlated_audited_and_minimized() -> None:
    scene, scenario, test_run, telemetry, vehicle_command = fixtures()
    fake = FakeSession()
    evidence, duplicate = await create_integration_evidence(
        cast(AsyncSession, fake),
        scene=scene,
        scenario=scenario,
        test_run=test_run,
        telemetry_events=[telemetry],
        vehicle_commands=[vehicle_command],
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert evidence.dashboard_summary == {
        "scenario_status": "passed",
        "maneuver": "emergency_brake",
        "alert_types": ["forward_collision"],
        "assertion_coverage": 1.0,
        "regression_fingerprint": "b" * 64,
        "telemetry_event_count": 1,
        "vehicle_command_count": 1,
        "carsystemui_evidence_count": 1,
    }
    event = next(item for item in fake.added if isinstance(item, OutboxEvent))
    audit = next(item for item in fake.added if isinstance(item, AuditRecord))
    assert event.event_type == "atep.adas.integration_evidence.created.v1"
    assert "carsystemui_evidence" not in event.payload
    assert "telemetry_event_ids" not in event.payload
    assert audit.action == "adas.integration_evidence_created"


@pytest.mark.asyncio
async def test_integration_evidence_rejects_cross_vehicle_and_wrong_ui_status() -> None:
    scene, scenario, test_run, telemetry, vehicle_command = fixtures()
    telemetry.vehicle_id = uuid4()
    with pytest.raises(AdasIntegrationEvidenceContractError, match="inconsistent"):
        await create_integration_evidence(
            cast(AsyncSession, FakeSession()),
            scene=scene,
            scenario=scenario,
            test_run=test_run,
            telemetry_events=[telemetry],
            vehicle_commands=[vehicle_command],
            command=command(),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    wrong_ui = command().model_dump(mode="json")
    wrong_ui["carsystemui_evidence"][0]["displayed_scenario_status"] = "failed"
    telemetry.vehicle_id = scene.vehicle_id
    with pytest.raises(AdasIntegrationEvidenceContractError, match="inconsistent"):
        await create_integration_evidence(
            cast(AsyncSession, FakeSession()),
            scene=scene,
            scenario=scenario,
            test_run=test_run,
            telemetry_events=[telemetry],
            vehicle_commands=[vehicle_command],
            command=AdasIntegrationEvidenceCreate.model_validate(wrong_ui),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_integration_evidence_exact_replay_and_conflict_are_stable() -> None:
    scene, scenario, test_run, telemetry, vehicle_command = fixtures()
    original, _ = await create_integration_evidence(
        cast(AsyncSession, FakeSession()),
        scene=scene,
        scenario=scenario,
        test_run=test_run,
        telemetry_events=[telemetry],
        vehicle_commands=[vehicle_command],
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    returned, duplicate = await create_integration_evidence(
        cast(AsyncSession, FakeSession(existing=original)),
        scene=scene,
        scenario=scenario,
        test_run=test_run,
        telemetry_events=[],
        vehicle_commands=[],
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is original and duplicate is True
    changed = AdasIntegrationEvidenceCreate.model_validate(
        {**command().model_dump(mode="json"), "vehicle_command_ids": []}
    )
    with pytest.raises(AdasIntegrationEvidenceConflictError):
        await create_integration_evidence(
            cast(AsyncSession, FakeSession(existing=original)),
            scene=scene,
            scenario=scenario,
            test_run=test_run,
            telemetry_events=[],
            vehicle_commands=[],
            command=changed,
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_dashboard_event_is_minimized_and_publish_failure_is_non_blocking() -> None:
    event = AdasTestRunEvidenceStreamEvent(
        run_id="adas-test-run-001",
        evidence_id="integration-evidence-001",
        scenario_execution_id="adas-scenario-001",
        dashboard_summary=AdasDashboardSummary(
            scenario_status="passed",
            maneuver="emergency_brake",
            alert_types=["forward_collision"],
            assertion_coverage=1,
            regression_fingerprint="b" * 64,
            telemetry_event_count=1,
            vehicle_command_count=1,
            carsystemui_evidence_count=1,
        ),
        occurred_at=datetime(2026, 9, 7, tzinfo=UTC),
    )
    redis = FakeRedis()
    await publish_test_run_message(
        redis,
        run_id=event.run_id,
        event=event,
        event_type=event.type,
    )
    channel, payload = redis.messages[0]
    body = json.loads(payload)
    assert channel == "atep:test-runs:adas-test-run-001"
    assert "telemetry_event_ids" not in body
    assert "vehicle_command_ids" not in body
    assert "carsystemui_evidence" not in body

    await publish_test_run_message(
        FakeRedis(fail=True),
        run_id=event.run_id,
        event=event,
        event_type=event.type,
    )
