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
    BrakeBatteryVersionConflictError,
    BrakeSimulationCommandConflictError,
    BrakeStateVersionConflictError,
)
from atep.electric_vehicle.models import (
    BatteryPackState,
    BrakeSimulationStep,
    MotorInverterState,
    RegenerativeBrakeState,
)
from atep.electric_vehicle.schemas import BrakeSimulationCommand, RegenerativeBrakeCreate
from atep.electric_vehicle.service import (
    _battery_charge_acceptance_kw,
    create_regenerative_brake,
    regenerative_brake_response,
    simulate_brake_step,
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
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
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


def battery(
    current_vehicle: Vehicle,
    *,
    soc_pct: float = 80.0,
    temperature_c: float = 25.0,
    contactor_state: str = "closed",
) -> BatteryPackState:
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    return BatteryPackState(
        id=uuid4(),
        vehicle_id=current_vehicle.id,
        chemistry="lfp",
        series_cell_count=96,
        nominal_capacity_ah=100.0,
        nominal_cell_voltage_v=3.2,
        internal_resistance_ohm=0.08,
        soc_pct=soc_pct,
        soh_pct=100.0,
        pack_voltage_v=328.32,
        pack_current_a=0.0,
        pack_temperature_c=temperature_c,
        contactor_state=contactor_state,
        operating_state="normal",
        cells=[
            {
                "index": index + 1,
                "voltage_v": 3.42,
                "temperature_c": temperature_c,
                "soc_pct": soc_pct,
            }
            for index in range(96)
        ],
        version=2,
        simulation_time_ms=1_000,
        created_at=now,
        updated_at=now,
    )


def motor(current_vehicle: Vehicle) -> MotorInverterState:
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
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
        motor_temperature_c=25.0,
        inverter_temperature_c=25.0,
        drive_mode="normal",
        operating_state="standby",
        limiting_reason=None,
        version=1,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )


def braking(current_vehicle: Vehicle) -> RegenerativeBrakeState:
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    return RegenerativeBrakeState(
        id=uuid4(),
        vehicle_id=current_vehicle.id,
        vehicle_mass_kg=2_000.0,
        wheel_radius_m=0.34,
        final_drive_ratio=9.0,
        drivetrain_efficiency_pct=90.0,
        max_regen_torque_nm=180.0,
        max_regen_power_kw=100.0,
        regen_efficiency_pct=85.0,
        max_friction_deceleration_mps2=9.0,
        requested_deceleration_mps2=0.0,
        delivered_deceleration_mps2=0.0,
        vehicle_speed_mps=0.0,
        regenerative_deceleration_mps2=0.0,
        friction_deceleration_mps2=0.0,
        regenerative_motor_torque_nm=0.0,
        recovered_power_kw=0.0,
        recovered_energy_kwh=0.0,
        cumulative_recovered_energy_kwh=0.0,
        battery_charge_acceptance_kw=98.496,
        operating_state="standby",
        limiting_reason=None,
        version=1,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )


def command(**changes: Any) -> BrakeSimulationCommand:
    values: dict[str, Any] = {
        "command_id": "brake-001",
        "duration_ms": 10_000,
        "requested_deceleration_mps2": 1.0,
        "vehicle_speed_mps": 20.0,
        "expected_version": 1,
        "expected_battery_version": 2,
    }
    values.update(changes)
    return BrakeSimulationCommand(**values)


def test_brake_contracts_are_bounded() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 15"):
        command(requested_deceleration_mps2=15.1)
    with pytest.raises(ValidationError, match="greater than or equal to 500"):
        RegenerativeBrakeCreate(vehicle_mass_kg=499.0)


@pytest.mark.asyncio
async def test_create_regenerative_brake_records_atomic_evidence() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    session = FakeSession(None)
    state = await create_regenerative_brake(
        cast(AsyncSession, session),
        vehicle=current_vehicle,
        pack=pack,
        motor=motor(current_vehicle),
        command=RegenerativeBrakeCreate(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )

    assert state.operating_state == "standby"
    assert state.max_regen_torque_nm == 180.0
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert events[0].event_type == "atep.electric_vehicle.regenerative_brake.created.v1"
    assert audits[0].action == "electric_vehicle.regenerative_brake_created"


@pytest.mark.asyncio
async def test_regenerative_step_recovers_energy_and_increases_soc() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    session = FakeSession(None, motor(current_vehicle), pack, braking(current_vehicle))
    result, duplicate = await simulate_brake_step(
        cast(AsyncSession, session),
        vehicle=current_vehicle,
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert duplicate is False
    assert result.operating_state == "regenerative"
    assert result.delivered_deceleration_mps2 == 1.0
    assert result.friction_deceleration_mps2 == 0.0
    assert result.recovered_power_kw == 34.0
    assert result.recovered_energy_kwh > 0.0
    assert result.battery_soc_pct > 80.0
    assert result.battery_version == 3
    assert result.version == 2
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert events[0].event_type == "atep.electric_vehicle.brake.step.completed.v1"
    assert "cells" not in events[0].payload
    assert audits[0].action == "electric_vehicle.brake_step_completed"


@pytest.mark.asyncio
async def test_high_deceleration_blends_regen_and_friction() -> None:
    current_vehicle = vehicle()
    result, _ = await simulate_brake_step(
        cast(
            AsyncSession,
            FakeSession(
                None,
                motor(current_vehicle),
                battery(current_vehicle),
                braking(current_vehicle),
            ),
        ),
        vehicle=current_vehicle,
        command=command(requested_deceleration_mps2=4.0),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.operating_state == "blended"
    assert result.regenerative_deceleration_mps2 > 0.0
    assert result.friction_deceleration_mps2 > 0.0
    assert result.delivered_deceleration_mps2 == 4.0
    assert result.limiting_reason == "regenerative_torque_limit"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("speed_mps", "soc_pct", "temperature_c", "contactor_state", "reason"),
    [
        (0.0, 80.0, 25.0, "closed", "vehicle_speed_too_low"),
        (20.0, 95.0, 25.0, "closed", "battery_charge_unavailable"),
        (20.0, 80.0, -1.0, "closed", "battery_charge_unavailable"),
        (20.0, 80.0, 25.0, "open", "battery_charge_unavailable"),
    ],
)
async def test_regen_unavailable_uses_friction(
    speed_mps: float,
    soc_pct: float,
    temperature_c: float,
    contactor_state: str,
    reason: str,
) -> None:
    current_vehicle = vehicle()
    pack = battery(
        current_vehicle,
        soc_pct=soc_pct,
        temperature_c=temperature_c,
        contactor_state=contactor_state,
    )
    result, _ = await simulate_brake_step(
        cast(
            AsyncSession,
            FakeSession(None, motor(current_vehicle), pack, braking(current_vehicle)),
        ),
        vehicle=current_vehicle,
        command=command(vehicle_speed_mps=speed_mps),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.operating_state == "friction"
    assert result.regenerative_deceleration_mps2 == 0.0
    assert result.friction_deceleration_mps2 == 1.0
    assert result.recovered_energy_kwh == 0.0
    assert result.battery_version == 2
    assert result.limiting_reason == reason


def test_charge_acceptance_tapers_near_high_soc() -> None:
    current_vehicle = vehicle()
    at_eighty = _battery_charge_acceptance_kw(
        battery(current_vehicle, soc_pct=80.0), 100.0
    )
    near_full = _battery_charge_acceptance_kw(
        battery(current_vehicle, soc_pct=90.0), 100.0
    )

    assert near_full < at_eighty


@pytest.mark.asyncio
async def test_battery_charge_power_limit_blends_friction() -> None:
    current_vehicle = vehicle()
    state = braking(current_vehicle)
    state.max_regen_torque_nm = 400.0
    result, _ = await simulate_brake_step(
        cast(
            AsyncSession,
            FakeSession(None, motor(current_vehicle), battery(current_vehicle), state),
        ),
        vehicle=current_vehicle,
        command=command(requested_deceleration_mps2=1.0, vehicle_speed_mps=100.0),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.operating_state == "blended"
    assert result.recovered_power_kw <= 98.496
    assert result.limiting_reason == "battery_charge_limit"


@pytest.mark.asyncio
async def test_long_regenerative_step_does_not_exceed_soc_acceptance_ceiling() -> None:
    current_vehicle = vehicle()
    result, _ = await simulate_brake_step(
        cast(
            AsyncSession,
            FakeSession(
                None,
                motor(current_vehicle),
                battery(current_vehicle, soc_pct=94.0),
                braking(current_vehicle),
            ),
        ),
        vehicle=current_vehicle,
        command=command(duration_ms=3_600_000, requested_deceleration_mps2=4.0),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.battery_soc_pct == 95.0
    assert result.recovered_energy_kwh <= 0.308
    assert result.friction_deceleration_mps2 > 0.0


@pytest.mark.asyncio
async def test_brake_capacity_limit_is_explicit() -> None:
    current_vehicle = vehicle()
    result, _ = await simulate_brake_step(
        cast(
            AsyncSession,
            FakeSession(
                None,
                motor(current_vehicle),
                battery(current_vehicle),
                braking(current_vehicle),
            ),
        ),
        vehicle=current_vehicle,
        command=command(requested_deceleration_mps2=15.0),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.operating_state == "limited"
    assert result.delivered_deceleration_mps2 < 15.0
    assert result.limiting_reason == "brake_capacity_limit"


@pytest.mark.asyncio
async def test_brake_replay_and_version_conflicts_are_stable() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    state = braking(current_vehicle)
    snapshot = regenerative_brake_response(state, current_vehicle, pack).model_dump(mode="json")
    existing = BrakeSimulationStep(
        id=uuid4(),
        vehicle_id=current_vehicle.id,
        command_id="brake-001",
        duration_ms=10_000,
        requested_deceleration_mps2=1.0,
        vehicle_speed_mps=20.0,
        previous_version=1,
        state_version=2,
        previous_battery_version=2,
        battery_state_version=3,
        result=snapshot,
        requested_by_user_id=uuid4(),
    )
    replay, duplicate = await simulate_brake_step(
        cast(AsyncSession, FakeSession(existing)),
        vehicle=current_vehicle,
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is True
    assert replay.duplicate is True

    with pytest.raises(BrakeSimulationCommandConflictError):
        await simulate_brake_step(
            cast(AsyncSession, FakeSession(existing)),
            vehicle=current_vehicle,
            command=command(duration_ms=20_000),
            actor_user_id=uuid4(),
            correlation_id=None,
        )

    with pytest.raises(BrakeStateVersionConflictError):
        await simulate_brake_step(
            cast(AsyncSession, FakeSession(None, motor(current_vehicle), pack, state)),
            vehicle=current_vehicle,
            command=command(expected_version=2),
            actor_user_id=uuid4(),
            correlation_id=None,
        )

    with pytest.raises(BrakeBatteryVersionConflictError):
        await simulate_brake_step(
            cast(AsyncSession, FakeSession(None, motor(current_vehicle), pack, state)),
            vehicle=current_vehicle,
            command=command(expected_battery_version=3),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
