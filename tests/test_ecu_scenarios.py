from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import EcuScenarioExecutionConflictError
from atep.ecus.models import EcuScenarioExecution
from atep.ecus.scenario_service import (
    _campaign_seed,
    _command_id,
    execute_scenario,
    scenario_response,
)
from atep.ecus.schemas import (
    EcuScenarioActionResult,
    EcuScenarioExecuteCommand,
    EcuScenarioResourceMetrics,
    EcuScenarioTimingDiagnostics,
)
from atep.events.models import OutboxEvent
from atep.vehicles.models import Vehicle


class ScenarioSession:
    def __init__(self, *scalar_values: Any) -> None:
        self.scalar_values = list(scalar_values)
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        now = datetime(2026, 8, 24, 20, 0, tzinfo=UTC)
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()
            if getattr(value, "created_at", None) is None:
                value.created_at = now
            if getattr(value, "updated_at", None) is None:
                value.updated_at = now


def target_vehicle() -> Vehicle:
    now = datetime(2026, 8, 24, 20, 0, tzinfo=UTC)
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP Scenario Vehicle",
        model="EV",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )


def scenario_command(*, execution_id: str = "campaign-001") -> EcuScenarioExecuteCommand:
    return EcuScenarioExecuteCommand(
        execution_id=execution_id,
        iterations=2,
        base_seed=42,
        actions=[
            {"kind": "advance_time", "ecu_id": "bms-ecu", "duration_ms": 100},
            {"kind": "corrupt_memory", "ecu_id": "bms-ecu", "bit_flips": 1},
        ],
    )


def test_scenario_contract_bounds_actions_and_requires_kind_fields() -> None:
    with pytest.raises(ValidationError, match="requires ecu_id, duration_ms"):
        EcuScenarioExecuteCommand(
            execution_id="scenario-001", actions=[{"kind": "advance_time"}]
        )
    with pytest.raises(ValidationError, match="at most 16 ECUs"):
        EcuScenarioExecuteCommand(
            execution_id="scenario-002",
            actions=[
                {"kind": "advance_time", "ecu_id": f"ecu-{index:02d}", "duration_ms": 1}
                for index in range(17)
            ],
        )
    with pytest.raises(ValidationError, match="at most 32 items"):
        EcuScenarioExecuteCommand(
            execution_id="scenario-003",
            actions=[
                {"kind": "advance_time", "ecu_id": "bms-ecu", "duration_ms": 1}
                for _ in range(33)
            ],
        )


def test_campaign_identity_and_seed_are_deterministic_and_coordinate_specific() -> None:
    assert _command_id("campaign-001", 2, 3) == "scn-campaign-001-2-3"
    assert _campaign_seed(42, 2, 3) == _campaign_seed(42, 2, 3)
    assert _campaign_seed(42, 2, 3) != _campaign_seed(42, 2, 4)


def install_orchestration_stubs(
    monkeypatch: pytest.MonkeyPatch, metrics: list[EcuScenarioResourceMetrics]
) -> None:
    from atep.ecus import scenario_service

    async def fake_metrics(*_: Any, **__: Any) -> EcuScenarioResourceMetrics:
        return metrics.pop(0)

    async def fake_timing(*_: Any, **__: Any) -> EcuScenarioTimingDiagnostics:
        return EcuScenarioTimingDiagnostics(
            minimum_time_ms=100,
            maximum_time_ms=200,
            clock_skew_ms=100,
            synchronized=False,
            ecus=[],
        )

    async def fake_action(*_: Any, **kwargs: Any) -> EcuScenarioActionResult:
        action = kwargs["action"]
        return EcuScenarioActionResult(
            iteration=kwargs["iteration"],
            action_index=kwargs["action_index"],
            kind=action.kind,
            ecu_id=action.ecu_id,
            state_version=kwargs["iteration"] * 2 + kwargs["action_index"],
            simulation_time_ms=kwargs["iteration"] * 100,
            outcome="completed",
        )

    monkeypatch.setattr(scenario_service, "_resource_metrics", fake_metrics)
    monkeypatch.setattr(scenario_service, "_timing_diagnostics", fake_timing)
    monkeypatch.setattr(scenario_service, "_execute_action", fake_action)


@pytest.mark.asyncio
async def test_scenario_execution_is_bounded_repeatable_and_evented(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = [
        EcuScenarioResourceMetrics(
            ecu_count=2,
            memory_cell_count=4,
            signal_count=2,
            active_fault_count=0,
            route_count=1,
            aggregate_version=4,
        ),
        EcuScenarioResourceMetrics(
            ecu_count=2,
            memory_cell_count=4,
            signal_count=2,
            active_fault_count=0,
            route_count=1,
            aggregate_version=8,
        ),
    ]
    install_orchestration_stubs(monkeypatch, metrics)
    vehicle = target_vehicle()
    session = ScenarioSession(vehicle, None)
    execution, duplicate = await execute_scenario(
        cast(AsyncSession, session),
        vehicle=vehicle,
        command=scenario_command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )

    assert duplicate is False
    assert len(execution.request_hash) == 64
    assert len(execution.result["actions"]) == 4
    assert [
        (item["iteration"], item["action_index"], item["kind"])
        for item in execution.result["actions"]
    ] == [
        (1, 1, "advance_time"),
        (1, 2, "corrupt_memory"),
        (2, 1, "advance_time"),
        (2, 2, "corrupt_memory"),
    ]
    assert execution.result["timing"]["clock_skew_ms"] == 100
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert event.event_type == "atep.ecu.scenario.completed.v1"
    assert "actions" not in event.payload
    assert audit.details["action_count"] == 4
    assert "request" not in audit.details


@pytest.mark.asyncio
async def test_scenario_execution_allows_exact_replay_and_rejects_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zero = EcuScenarioResourceMetrics(
        ecu_count=0,
        memory_cell_count=0,
        signal_count=0,
        active_fault_count=0,
        route_count=0,
        aggregate_version=0,
    )
    install_orchestration_stubs(monkeypatch, [zero, zero])
    vehicle = target_vehicle()
    command = scenario_command()
    original, _ = await execute_scenario(
        cast(AsyncSession, ScenarioSession(vehicle, None)),
        vehicle=vehicle,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    replay, duplicate = await execute_scenario(
        cast(AsyncSession, ScenarioSession(vehicle, original)),
        vehicle=vehicle,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert replay is original
    assert duplicate is True
    assert scenario_response(replay, vehicle=vehicle, duplicate=True).duplicate is True

    conflicting = scenario_command(execution_id=command.execution_id)
    conflicting.base_seed = 99
    with pytest.raises(EcuScenarioExecutionConflictError):
        await execute_scenario(
            cast(AsyncSession, ScenarioSession(vehicle, original)),
            vehicle=vehicle,
            command=conflicting,
            actor_user_id=uuid4(),
            correlation_id=None,
        )


def test_scenario_model_retains_bounded_aggregate_evidence() -> None:
    assert set(EcuScenarioExecution.__table__.columns.keys()) == {
        "id",
        "vehicle_id",
        "execution_id",
        "request_hash",
        "request",
        "result",
        "iteration_count",
        "requested_by_user_id",
        "created_at",
        "updated_at",
    }
