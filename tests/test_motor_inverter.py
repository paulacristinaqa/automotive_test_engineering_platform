from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.core.errors import (
    MotorSimulationCommandConflictError,
    MotorStateVersionConflictError,
)
from atep.electric_vehicle.models import (
    BatteryPackState,
    MotorInverterState,
    MotorSimulationStep,
)
from atep.electric_vehicle.schemas import MotorInverterCreate, MotorSimulationCommand
from atep.electric_vehicle.service import (
    create_motor_inverter,
    motor_inverter_response,
    simulate_motor_step,
)
from atep.events.models import OutboxEvent
from atep.vehicles.models import Vehicle


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

    @asynccontextmanager
    async def begin_nested(self) -> AsyncIterator[None]:
        yield


def vehicle() -> Vehicle:
    now = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="ATEP Reference EV",
        model="EV",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )


def battery(current_vehicle: Vehicle, *, available: bool = True) -> BatteryPackState:
    now = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    return BatteryPackState(
        id=uuid4(),
        vehicle_id=current_vehicle.id,
        chemistry="lfp",
        series_cell_count=96,
        nominal_capacity_ah=100.0,
        nominal_cell_voltage_v=3.2,
        internal_resistance_ohm=0.08,
        soc_pct=80.0,
        soh_pct=100.0,
        pack_voltage_v=328.32,
        pack_current_a=0.0,
        pack_temperature_c=25.0,
        contactor_state="closed" if available else "open",
        operating_state="normal",
        cells=[
            {"index": index + 1, "voltage_v": 3.42, "temperature_c": 25.0, "soc_pct": 80.0}
            for index in range(96)
        ],
        version=2,
        simulation_time_ms=1_000,
        created_at=now,
        updated_at=now,
    )


def powertrain(
    current_vehicle: Vehicle, *, motor_temperature_c: float = 25.0
) -> MotorInverterState:
    now = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    return MotorInverterState(
        id=uuid4(),
        vehicle_id=current_vehicle.id,
        max_torque_nm=400.0,
        max_speed_rpm=16_000,
        max_inverter_power_kw=180.0,
        base_efficiency_pct=94.0,
        requested_torque_nm=0.0,
        delivered_torque_nm=0.0,
        motor_speed_rpm=0,
        mechanical_power_kw=0.0,
        electrical_power_kw=0.0,
        efficiency_pct=94.0,
        power_loss_kw=0.0,
        motor_temperature_c=motor_temperature_c,
        inverter_temperature_c=25.0,
        drive_mode="normal",
        operating_state="standby",
        limiting_reason=None,
        version=1,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )


def test_motor_contracts_reject_regen_and_unsafe_speed() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        MotorSimulationCommand(
            command_id="regen-deferred",
            duration_ms=1_000,
            requested_torque_nm=-1.0,
            motor_speed_rpm=1_000,
            expected_version=1,
        )
    with pytest.raises(ValidationError, match="less than or equal to 30000"):
        MotorInverterCreate(max_speed_rpm=30_001)


@pytest.mark.asyncio
async def test_create_motor_inverter_records_atomic_evidence() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    session = FakeSession(None)
    state = await create_motor_inverter(
        cast(AsyncSession, session),
        vehicle=current_vehicle,
        pack=pack,
        command=MotorInverterCreate(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )

    assert state.max_torque_nm == 400.0
    assert state.operating_state == "standby"
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert events[0].event_type == "atep.electric_vehicle.motor_inverter.created.v1"
    assert audits[0].action == "electric_vehicle.motor_inverter_created"


@pytest.mark.asyncio
async def test_motor_step_calculates_torque_power_efficiency_and_heat() -> None:
    current_vehicle = vehicle()
    state = powertrain(current_vehicle)
    pack = battery(current_vehicle)
    session = FakeSession(None, state, pack)
    result, duplicate = await simulate_motor_step(
        cast(AsyncSession, session),
        vehicle=current_vehicle,
        command=MotorSimulationCommand(
            command_id="motor-001",
            duration_ms=1_000,
            requested_torque_nm=100.0,
            motor_speed_rpm=3_000,
            drive_mode="normal",
            expected_version=1,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert duplicate is False
    assert result.delivered_torque_nm == 100.0
    assert result.mechanical_power_kw == 31.416
    assert result.electrical_power_kw > result.mechanical_power_kw
    assert result.power_loss_kw > 0.0
    assert result.motor_temperature_c > 25.0
    assert result.operating_state == "ready"
    assert result.version == 2
    assert result.simulation_time_ms == 1_000


@pytest.mark.asyncio
async def test_drive_mode_battery_and_speed_limits_are_explicit() -> None:
    current_vehicle = vehicle()
    eco, _ = await simulate_motor_step(
        cast(
            AsyncSession, FakeSession(None, powertrain(current_vehicle), battery(current_vehicle))
        ),
        vehicle=current_vehicle,
        command=MotorSimulationCommand(
            command_id="eco-limit",
            duration_ms=1,
            requested_torque_nm=400.0,
            motor_speed_rpm=0,
            drive_mode="eco",
            expected_version=1,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert eco.delivered_torque_nm == 240.0
    assert eco.limiting_reason == "drive_mode_limit"
    assert eco.operating_state == "derated"

    unavailable, _ = await simulate_motor_step(
        cast(
            AsyncSession,
            FakeSession(
                None, powertrain(current_vehicle), battery(current_vehicle, available=False)
            ),
        ),
        vehicle=current_vehicle,
        command=MotorSimulationCommand(
            command_id="battery-open",
            duration_ms=1,
            requested_torque_nm=100.0,
            motor_speed_rpm=1_000,
            expected_version=1,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert unavailable.delivered_torque_nm == 0.0
    assert unavailable.limiting_reason == "battery_unavailable"

    overspeed, _ = await simulate_motor_step(
        cast(
            AsyncSession, FakeSession(None, powertrain(current_vehicle), battery(current_vehicle))
        ),
        vehicle=current_vehicle,
        command=MotorSimulationCommand(
            command_id="overspeed",
            duration_ms=1,
            requested_torque_nm=100.0,
            motor_speed_rpm=16_001,
            expected_version=1,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert overspeed.delivered_torque_nm == 0.0
    assert overspeed.limiting_reason == "speed_limit"


@pytest.mark.asyncio
async def test_battery_power_limit_derates_high_speed_torque() -> None:
    current_vehicle = vehicle()
    result, _ = await simulate_motor_step(
        cast(
            AsyncSession, FakeSession(None, powertrain(current_vehicle), battery(current_vehicle))
        ),
        vehicle=current_vehicle,
        command=MotorSimulationCommand(
            command_id="battery-power-limit",
            duration_ms=1,
            requested_torque_nm=400.0,
            motor_speed_rpm=10_000,
            drive_mode="sport",
            expected_version=1,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.delivered_torque_nm < 400.0
    assert result.electrical_power_kw <= result.battery_power_limit_kw
    assert result.limiting_reason == "battery_power_limit"
    assert result.operating_state == "derated"


@pytest.mark.asyncio
async def test_motor_thermal_protection_removes_delivered_power() -> None:
    current_vehicle = vehicle()
    result, _ = await simulate_motor_step(
        cast(
            AsyncSession,
            FakeSession(
                None,
                powertrain(current_vehicle, motor_temperature_c=149.9),
                battery(current_vehicle),
            ),
        ),
        vehicle=current_vehicle,
        command=MotorSimulationCommand(
            command_id="thermal-trip",
            duration_ms=60_000,
            requested_torque_nm=400.0,
            motor_speed_rpm=10_000,
            drive_mode="sport",
            expected_version=1,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.operating_state == "protection"
    assert result.limiting_reason == "thermal_protection"
    assert result.delivered_torque_nm == 0.0
    assert result.electrical_power_kw == 0.0
    assert result.motor_temperature_c == 150.0


@pytest.mark.asyncio
async def test_motor_replay_conflict_and_stale_version_are_stable() -> None:
    current_vehicle = vehicle()
    state = powertrain(current_vehicle)
    pack = battery(current_vehicle)
    snapshot = motor_inverter_response(state, current_vehicle, pack).model_dump(mode="json")
    existing = MotorSimulationStep(
        id=uuid4(),
        vehicle_id=current_vehicle.id,
        command_id="motor-replay",
        duration_ms=1_000,
        requested_torque_nm=50.0,
        motor_speed_rpm=2_000,
        drive_mode="normal",
        ambient_temperature_c=25.0,
        previous_version=1,
        state_version=2,
        result=snapshot,
        requested_by_user_id=uuid4(),
    )
    replay, duplicate = await simulate_motor_step(
        cast(AsyncSession, FakeSession(existing)),
        vehicle=current_vehicle,
        command=MotorSimulationCommand(
            command_id="motor-replay",
            duration_ms=1_000,
            requested_torque_nm=50.0,
            motor_speed_rpm=2_000,
            expected_version=1,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is True
    assert replay.duplicate is True

    with pytest.raises(MotorSimulationCommandConflictError):
        await simulate_motor_step(
            cast(AsyncSession, FakeSession(existing)),
            vehicle=current_vehicle,
            command=MotorSimulationCommand(
                command_id="motor-replay",
                duration_ms=2_000,
                requested_torque_nm=50.0,
                motor_speed_rpm=2_000,
                expected_version=1,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )

    with pytest.raises(MotorStateVersionConflictError) as exc:
        await simulate_motor_step(
            cast(AsyncSession, FakeSession(None, state, pack)),
            vehicle=current_vehicle,
            command=MotorSimulationCommand(
                command_id="motor-stale",
                duration_ms=1_000,
                requested_torque_nm=50.0,
                motor_speed_rpm=2_000,
                expected_version=2,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert exc.value.details == {"current_version": 1}
