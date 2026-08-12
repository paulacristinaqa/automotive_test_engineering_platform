from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import VehicleStateVersionConflictError
from atep.events.models import OutboxEvent
from atep.identity.dependencies import require_permissions
from atep.identity.permissions import PermissionName
from atep.vehicles.models import (
    Vehicle,
    VehicleDigitalState,
    VehicleSimulationStep,
    VehicleSimulationTransition,
)
from atep.vehicles.schemas import (
    DigitalVehicleStatePayload,
    DigitalVehicleStateReplace,
    VehicleCreate,
    VehicleSimulationStepCommand,
    VehicleSimulationTransitionCommand,
)
from atep.vehicles.service import (
    create_vehicle,
    execute_vehicle_simulation_step,
    execute_vehicle_simulation_transition,
    replace_vehicle_digital_state,
)


class FakeSession:
    def __init__(self, *scalar_values: Any) -> None:
        self.scalar_values = list(scalar_values)
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.scalar_values.pop(0) if self.scalar_values else None

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    async def refresh(self, _: object, *, attribute_names: list[str]) -> None:
        assert attribute_names == ["updated_at"]

    def begin_nested(self) -> Any:
        class Transaction:
            async def __aenter__(self) -> None:
                return None

            async def __aexit__(self, *_: object) -> None:
                return None

        return Transaction()


def vehicle() -> Vehicle:
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP Digital Vehicle",
        model="EV Reference Platform",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )


def state() -> VehicleDigitalState:
    now = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)
    baseline = DigitalVehicleStatePayload()
    return VehicleDigitalState(
        id=uuid4(),
        vehicle_id=uuid4(),
        operational_mode=baseline.operational_mode.value,
        battery_state=baseline.battery.model_dump(mode="json"),
        powertrain_state=baseline.powertrain.model_dump(mode="json"),
        brake_state=baseline.brakes.model_dump(mode="json"),
        steering_state=baseline.steering.model_dump(mode="json"),
        lighting_state=baseline.lighting.model_dump(mode="json"),
        version=1,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )


def driving_command(*, expected_version: int = 1) -> DigitalVehicleStateReplace:
    return DigitalVehicleStateReplace(
        expected_version=expected_version,
        operational_mode="driving",
        battery={
            "state_of_charge_pct": 79.5,
            "state_of_health_pct": 99.8,
            "pack_voltage_v": 398.0,
            "pack_current_a": 120.0,
            "temperature_c": 31.0,
            "contactors_closed": True,
            "charging_status": "disconnected",
        },
        powertrain={
            "motor_enabled": True,
            "gear": "drive",
            "speed_kph": 45.0,
            "requested_torque_nm": 180.0,
            "delivered_torque_nm": 176.0,
        },
        brakes={
            "pedal_pct": 0.0,
            "hydraulic_pressure_bar": 0.0,
            "parking_brake_applied": False,
            "abs_active": False,
        },
        steering={"wheel_angle_deg": 3.5, "assist_active": True},
        lighting={"exterior_mode": "auto", "brake_lights": False, "indicator": "off"},
    )


def test_digital_vehicle_defaults_are_safe_and_bounded() -> None:
    baseline = DigitalVehicleStatePayload()
    assert baseline.operational_mode == "parked"
    assert baseline.powertrain.gear == "park"
    assert baseline.brakes.parking_brake_applied is True
    assert baseline.battery.contactors_closed is False

    with pytest.raises(ValidationError, match="less than or equal to 100"):
        DigitalVehicleStatePayload(battery={"state_of_charge_pct": 101})


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "operational_mode": "parked",
                "powertrain": {"motor_enabled": True, "gear": "drive", "speed_kph": 10},
                "brakes": {"parking_brake_applied": False},
                "battery": {"contactors_closed": True},
            },
            "moving vehicle must be in driving mode",
        ),
        (
            {
                "operational_mode": "charging",
                "battery": {"charging_status": "charging", "contactors_closed": False},
            },
            "charging requires",
        ),
        (
            {"powertrain": {"motor_enabled": False, "requested_torque_nm": 10}},
            "disabled motor",
        ),
    ],
)
def test_cross_component_invariants_reject_impossible_states(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        DigitalVehicleStatePayload.model_validate(payload)


@pytest.mark.asyncio
async def test_vehicle_registration_creates_safe_digital_state() -> None:
    session = FakeSession()
    registered = await create_vehicle(
        cast(AsyncSession, session),
        command=VehicleCreate(identifier="vehicle-001", display_name="Digital Vehicle"),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert registered.digital_state.operational_mode == "parked"
    assert registered.digital_state.version == 1
    assert registered.digital_state.brake_state["parking_brake_applied"] is True


@pytest.mark.asyncio
async def test_state_replace_is_versioned_audited_and_evented_atomically() -> None:
    target = vehicle()
    current = state()
    current.vehicle_id = target.id
    session = FakeSession(current)
    updated, duplicate = await replace_vehicle_digital_state(
        cast(AsyncSession, session),
        vehicle=target,
        command=driving_command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert updated.version == 2
    assert updated.operational_mode == "driving"
    assert updated.powertrain_state["speed_kph"] == 45.0
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert [item.event_type for item in events] == ["atep.digital_vehicle.state.updated.v1"]
    assert events[0].payload["previous_version"] == 1
    assert [item.action for item in audits] == ["digital_vehicle.state_updated"]
    assert "state" not in audits[0].details


@pytest.mark.asyncio
async def test_exact_retry_is_idempotent_but_stale_different_state_conflicts() -> None:
    target = vehicle()
    current = state()
    current.vehicle_id = target.id
    await replace_vehicle_digital_state(
        cast(AsyncSession, FakeSession(current)),
        vehicle=target,
        command=driving_command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    retry_session = FakeSession(current)
    returned, duplicate = await replace_vehicle_digital_state(
        cast(AsyncSession, retry_session),
        vehicle=target,
        command=driving_command(expected_version=1),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is current
    assert duplicate is True
    assert retry_session.added == []

    with pytest.raises(VehicleStateVersionConflictError) as error:
        await replace_vehicle_digital_state(
            cast(AsyncSession, FakeSession(current)),
            vehicle=target,
            command=DigitalVehicleStateReplace(expected_version=1),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert error.value.details == {"current_version": 2}


def test_digital_vehicle_permissions_are_independent() -> None:
    assert PermissionName.DIGITAL_VEHICLE_READ.value == "digital_vehicle:read"
    assert PermissionName.DIGITAL_VEHICLE_WRITE.value == "digital_vehicle:write"
    assert require_permissions(PermissionName.DIGITAL_VEHICLE_READ.value) is not None


def transition_command(
    *,
    command_id: str,
    expected_version: int,
    target_mode: str,
    duration_ms: int = 1000,
    speed_kph: float | None = None,
) -> VehicleSimulationTransitionCommand:
    return VehicleSimulationTransitionCommand(
        command_id=command_id,
        expected_version=expected_version,
        target_mode=target_mode,
        duration_ms=duration_ms,
        speed_kph=speed_kph,
    )


@pytest.mark.asyncio
async def test_deterministic_transition_sequence_advances_only_logical_time() -> None:
    target = vehicle()
    current = state()
    current.vehicle_id = target.id
    actor_id = uuid4()
    sequence = [
        transition_command(
            command_id="transition-ready-001",
            expected_version=1,
            target_mode="ready",
            duration_ms=500,
        ),
        transition_command(
            command_id="transition-drive-001",
            expected_version=2,
            target_mode="driving",
            duration_ms=1500,
            speed_kph=36,
        ),
        transition_command(
            command_id="transition-park-001",
            expected_version=3,
            target_mode="parked",
            duration_ms=700,
        ),
    ]
    transitions: list[VehicleSimulationTransition] = []
    for command in sequence:
        session = FakeSession(None, current)
        transition, duplicate = await execute_vehicle_simulation_transition(
            cast(AsyncSession, session),
            vehicle=target,
            command=command,
            actor_user_id=actor_id,
            correlation_id=uuid4(),
        )
        assert duplicate is False
        transitions.append(transition)
        events = [item for item in session.added if isinstance(item, OutboxEvent)]
        audits = [item for item in session.added if isinstance(item, AuditRecord)]
        assert [item.event_type for item in events] == [
            "atep.digital_vehicle.simulation.transitioned.v1"
        ]
        assert [item.action for item in audits] == ["digital_vehicle.simulation_transitioned"]

    assert [(item.from_mode, item.to_mode) for item in transitions] == [
        ("parked", "ready"),
        ("ready", "driving"),
        ("driving", "parked"),
    ]
    assert [item.simulation_time_ms for item in transitions] == [500, 2000, 2700]
    assert current.simulation_time_ms == 2700
    assert current.version == 4
    assert current.operational_mode == "parked"
    assert current.powertrain_state["speed_kph"] == 0
    assert current.powertrain_state["motor_enabled"] is False


@pytest.mark.asyncio
async def test_exact_simulation_transition_retry_is_idempotent() -> None:
    target = vehicle()
    command = transition_command(
        command_id="transition-ready-002", expected_version=1, target_mode="ready"
    )
    existing = VehicleSimulationTransition(
        id=uuid4(),
        vehicle_id=target.id,
        command_id=command.command_id,
        from_mode="parked",
        to_mode="ready",
        duration_ms=command.duration_ms,
        requested_speed_kph=None,
        previous_state_version=1,
        state_version=2,
        simulation_time_ms=1000,
        requested_by_user_id=uuid4(),
        created_at=datetime(2026, 8, 12, 11, 0, tzinfo=UTC),
        updated_at=datetime(2026, 8, 12, 11, 0, tzinfo=UTC),
    )
    session = FakeSession(existing)
    returned, duplicate = await execute_vehicle_simulation_transition(
        cast(AsyncSession, session),
        vehicle=target,
        command=command,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert returned is existing
    assert duplicate is True
    assert session.added == []


@pytest.mark.asyncio
async def test_simulation_command_identifier_cannot_be_reused_differently() -> None:
    from atep.core.errors import VehicleSimulationTransitionConflictError

    target = vehicle()
    existing = VehicleSimulationTransition(
        id=uuid4(),
        vehicle_id=target.id,
        command_id="transition-ready-004",
        from_mode="parked",
        to_mode="ready",
        duration_ms=1000,
        requested_speed_kph=None,
        previous_state_version=1,
        state_version=2,
        simulation_time_ms=1000,
        requested_by_user_id=uuid4(),
    )
    with pytest.raises(VehicleSimulationTransitionConflictError):
        await execute_vehicle_simulation_transition(
            cast(AsyncSession, FakeSession(existing)),
            vehicle=target,
            command=transition_command(
                command_id=existing.command_id,
                expected_version=1,
                target_mode="ready",
                duration_ms=2000,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


def test_simulation_transition_parameters_are_bounded_by_target() -> None:
    with pytest.raises(ValidationError, match="require speed_kph"):
        transition_command(
            command_id="transition-drive-005", expected_version=1, target_mode="driving"
        )


def test_simulation_step_contract_rejects_conflicting_inputs_and_invalid_faults() -> None:
    with pytest.raises(ValidationError, match="cannot be applied together"):
        VehicleSimulationStepCommand(
            command_id="step-command-001",
            expected_version=1,
            duration_ms=1000,
            inputs={"accelerator_pct": 10, "brake_pct": 20},
        )
    with pytest.raises(ValidationError, match="require fault_value"):
        VehicleSimulationStepCommand(
            command_id="step-command-001",
            expected_version=1,
            duration_ms=1000,
            sensors={"speed": {"fault_mode": "stuck"}},
        )


@pytest.mark.asyncio
async def test_seeded_sensor_and_actuator_step_is_deterministic_and_atomic() -> None:
    current = state()
    current.operational_mode = "driving"
    current.battery_state.update(contactors_closed=True)
    current.powertrain_state.update(motor_enabled=True, gear="drive", speed_kph=20.0)
    current.brake_state.update(parking_brake_applied=False)
    session = FakeSession(None, current)
    command = VehicleSimulationStepCommand(
        command_id="step-command-001",
        expected_version=1,
        duration_ms=2000,
        seed=42,
        inputs={"accelerator_pct": 20, "steering_angle_deg": 5},
        sensors={
            "speed": {"noise_amplitude": 0.5},
            "battery_soc": {"fault_mode": "offset", "fault_value": -2},
            "battery_temperature": {"fault_mode": "stuck", "fault_value": 48},
        },
    )
    step, duplicate = await execute_vehicle_simulation_step(
        cast(AsyncSession, session),
        vehicle=vehicle(),
        command=command,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert step.state_version == 2
    assert step.simulation_time_ms == 2000
    assert step.sensor_readings["battery_temperature_c"] == 48
    assert step.sensor_readings["battery_soc_pct"] < current.battery_state["state_of_charge_pct"]
    assert current.powertrain_state["speed_kph"] == 22.0
    assert current.steering_state["wheel_angle_deg"] == 5
    assert current.version == 2
    assert [type(item) for item in session.added] == [
        VehicleSimulationStep,
        OutboxEvent,
        AuditRecord,
    ]
    assert session.added[1].event_type == "atep.digital_vehicle.simulation.stepped.v1"
    assert session.added[2].action == "digital_vehicle.simulation_stepped"

    replay = VehicleSimulationStep(
        id=step.id,
        vehicle_id=step.vehicle_id,
        command_id=step.command_id,
        duration_ms=step.duration_ms,
        seed=step.seed,
        inputs=step.inputs,
        sensor_configuration=step.sensor_configuration,
        sensor_readings=step.sensor_readings,
        previous_state_version=step.previous_state_version,
        state_version=step.state_version,
        simulation_time_ms=step.simulation_time_ms,
        requested_by_user_id=step.requested_by_user_id,
        created_at=datetime(2026, 8, 12, 10, 1, tzinfo=UTC),
        updated_at=datetime(2026, 8, 12, 10, 1, tzinfo=UTC),
    )
    returned, duplicate = await execute_vehicle_simulation_step(
        cast(AsyncSession, FakeSession(replay)),
        vehicle=vehicle(),
        command=command,
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert returned is replay
    assert duplicate is True
    with pytest.raises(ValidationError, match="only valid for driving"):
        transition_command(
            command_id="transition-ready-005",
            expected_version=1,
            target_mode="ready",
            speed_kph=10,
        )


@pytest.mark.asyncio
async def test_simulation_rejects_skipped_transition_and_stale_version() -> None:
    from atep.core.errors import VehicleSimulationStateError

    target = vehicle()
    current = state()
    current.vehicle_id = target.id
    with pytest.raises(VehicleSimulationStateError):
        await execute_vehicle_simulation_transition(
            cast(AsyncSession, FakeSession(None, current)),
            vehicle=target,
            command=transition_command(
                command_id="transition-drive-003",
                expected_version=1,
                target_mode="driving",
                speed_kph=20,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    with pytest.raises(VehicleStateVersionConflictError):
        await execute_vehicle_simulation_transition(
            cast(AsyncSession, FakeSession(None, current)),
            vehicle=target,
            command=transition_command(
                command_id="transition-ready-003", expected_version=2, target_mode="ready"
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
