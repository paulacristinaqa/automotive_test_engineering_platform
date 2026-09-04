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
    ThermalBatteryVersionConflictError,
    ThermalCommandConflictError,
    ThermalMotorVersionConflictError,
    ThermalStateVersionConflictError,
)
from atep.electric_vehicle.models import (
    BatteryPackState,
    MotorInverterState,
    ThermalManagementState,
    ThermalManagementStep,
)
from atep.electric_vehicle.schemas import ThermalManagementCommand, ThermalManagementCreate
from atep.electric_vehicle.service import create_thermal_management, simulate_thermal_step
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
    now = datetime(2026, 9, 4, 16, 0, tzinfo=UTC)
    return Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="Reference EV",
        model="EV",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )


def battery(current_vehicle: Vehicle, temperature_c: float = 45.0) -> BatteryPackState:
    now = datetime(2026, 9, 4, 16, 0, tzinfo=UTC)
    return BatteryPackState(
        id=uuid4(),
        vehicle_id=current_vehicle.id,
        chemistry="lfp",
        series_cell_count=96,
        nominal_capacity_ah=100.0,
        nominal_cell_voltage_v=3.2,
        internal_resistance_ohm=0.08,
        soc_pct=60.0,
        soh_pct=100.0,
        pack_voltage_v=307.2,
        pack_current_a=0.0,
        pack_temperature_c=temperature_c,
        contactor_state="closed",
        operating_state="normal",
        cells=[
            {"index": i + 1, "voltage_v": 3.2, "temperature_c": temperature_c, "soc_pct": 60.0}
            for i in range(96)
        ],
        version=2,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )


def motor(current_vehicle: Vehicle, temperature_c: float = 110.0) -> MotorInverterState:
    now = datetime(2026, 9, 4, 16, 0, tzinfo=UTC)
    return MotorInverterState(
        id=uuid4(),
        vehicle_id=current_vehicle.id,
        max_torque_nm=400.0,
        max_speed_rpm=16000,
        max_inverter_power_kw=180.0,
        base_efficiency_pct=94.0,
        requested_torque_nm=0.0,
        delivered_torque_nm=0.0,
        motor_speed_rpm=0,
        mechanical_power_kw=0.0,
        electrical_power_kw=0.0,
        efficiency_pct=94.0,
        power_loss_kw=0.0,
        motor_temperature_c=temperature_c,
        inverter_temperature_c=90.0,
        drive_mode="normal",
        operating_state="ready",
        limiting_reason=None,
        version=3,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )


def thermal(current_vehicle: Vehicle, cabin_temperature_c: float = 10.0) -> ThermalManagementState:
    now = datetime(2026, 9, 4, 16, 0, tzinfo=UTC)
    return ThermalManagementState(
        id=uuid4(),
        vehicle_id=current_vehicle.id,
        max_battery_thermal_power_kw=8.0,
        max_powertrain_thermal_power_kw=12.0,
        max_cabin_thermal_power_kw=8.0,
        battery_target_temperature_c=25.0,
        motor_target_temperature_c=70.0,
        inverter_target_temperature_c=60.0,
        cabin_target_temperature_c=22.0,
        cabin_temperature_c=cabin_temperature_c,
        battery_thermal_power_kw=0.0,
        motor_thermal_power_kw=0.0,
        inverter_thermal_power_kw=0.0,
        cabin_thermal_power_kw=0.0,
        auxiliary_power_kw=0.0,
        operating_state="standby",
        limiting_reason=None,
        fault_code=None,
        version=1,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )


def command(**changes: Any) -> ThermalManagementCommand:
    values: dict[str, Any] = {
        "command_id": "thermal-001",
        "duration_ms": 60_000,
        "ambient_temperature_c": 25.0,
        "expected_version": 1,
        "expected_battery_version": 2,
        "expected_motor_version": 3,
    }
    values.update(changes)
    return ThermalManagementCommand(**values)


def test_thermal_contracts_are_bounded() -> None:
    with pytest.raises(ValidationError):
        ThermalManagementCreate(max_cabin_thermal_power_kw=31.0)
    with pytest.raises(ValidationError):
        command(duration_ms=0)
    with pytest.raises(ValidationError):
        command(fault_code="invalid fault")


@pytest.mark.asyncio
async def test_create_thermal_management_records_atomic_evidence() -> None:
    current_vehicle = vehicle()
    session = FakeSession(None)
    state = await create_thermal_management(
        cast(AsyncSession, session),
        vehicle=current_vehicle,
        pack=battery(current_vehicle),
        motor=motor(current_vehicle),
        command=ThermalManagementCreate(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert state.operating_state == "standby"
    assert any(isinstance(item, AuditRecord) for item in session.added)
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    assert events[0].event_type == "atep.electric_vehicle.thermal_management.created.v1"


@pytest.mark.asyncio
async def test_step_cools_hot_components_and_heats_cabin_atomically() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    drive = motor(current_vehicle)
    state = thermal(current_vehicle)
    session = FakeSession(None, pack, drive, state)
    result, duplicate = await simulate_thermal_step(
        cast(AsyncSession, session),
        vehicle=current_vehicle,
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert result.operating_state == "mixed"
    assert result.battery_temperature_c < 45.0
    assert result.motor_temperature_c < 110.0
    assert result.cabin_temperature_c > 10.0
    assert result.auxiliary_power_kw > 0.0
    assert abs(result.motor_thermal_power_kw) + abs(result.inverter_thermal_power_kw) <= 12.0
    assert (result.version, result.battery_version, result.motor_version) == (2, 3, 4)
    assert len([item for item in session.added if isinstance(item, ThermalManagementStep)]) == 1


@pytest.mark.asyncio
async def test_disabled_step_uses_passive_exchange_without_auxiliary_power() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    drive = motor(current_vehicle)
    state = thermal(current_vehicle)
    result, _ = await simulate_thermal_step(
        cast(AsyncSession, FakeSession(None, pack, drive, state)),
        vehicle=current_vehicle,
        command=command(enabled=False),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert result.operating_state == "standby"
    assert result.auxiliary_power_kw == 0.0
    assert result.limiting_reason == "thermal_management_disabled"
    assert result.battery_temperature_c < 45.0


@pytest.mark.asyncio
async def test_cabin_heat_load_changes_temperature_deterministically() -> None:
    current_vehicle = vehicle()
    pack_a, pack_b = battery(current_vehicle), battery(current_vehicle)
    motor_a, motor_b = motor(current_vehicle), motor(current_vehicle)
    state_a, state_b = (
        thermal(current_vehicle, cabin_temperature_c=22.0),
        thermal(current_vehicle, cabin_temperature_c=22.0),
    )
    baseline, _ = await simulate_thermal_step(
        cast(AsyncSession, FakeSession(None, pack_a, motor_a, state_a)),
        vehicle=current_vehicle,
        command=command(command_id="thermal-load-0", cabin_heat_load_kw=0.0),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    loaded, _ = await simulate_thermal_step(
        cast(AsyncSession, FakeSession(None, pack_b, motor_b, state_b)),
        vehicle=current_vehicle,
        command=command(command_id="thermal-load-1", cabin_heat_load_kw=2.0),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert loaded.cabin_temperature_c > baseline.cabin_temperature_c


@pytest.mark.asyncio
async def test_fault_disables_actuators_and_is_visible() -> None:
    current_vehicle = vehicle()
    result, _ = await simulate_thermal_step(
        cast(
            AsyncSession,
            FakeSession(
                None, battery(current_vehicle), motor(current_vehicle), thermal(current_vehicle)
            ),
        ),
        vehicle=current_vehicle,
        command=command(fault_code="COOLANT_PUMP_FAILURE"),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert result.operating_state == "faulted"
    assert result.fault_code == "COOLANT_PUMP_FAILURE"
    assert result.auxiliary_power_kw == 0.0


@pytest.mark.asyncio
async def test_exact_replay_returns_snapshot_and_changed_reuse_conflicts() -> None:
    current_vehicle = vehicle()
    prior = ThermalManagementStep(
        vehicle_id=current_vehicle.id,
        command_id="thermal-001",
        duration_ms=60_000,
        ambient_temperature_c=25.0,
        cabin_heat_load_kw=0.0,
        enabled=True,
        fault_code=None,
        previous_version=1,
        state_version=2,
        previous_battery_version=2,
        battery_state_version=3,
        previous_motor_version=3,
        motor_state_version=4,
        result={
            "vehicle_id": "vehicle-001",
            "battery_target_temperature_c": 25.0,
            "motor_target_temperature_c": 70.0,
            "inverter_target_temperature_c": 60.0,
            "cabin_target_temperature_c": 22.0,
            "battery_temperature_c": 40.0,
            "motor_temperature_c": 100.0,
            "inverter_temperature_c": 80.0,
            "cabin_temperature_c": 15.0,
            "battery_thermal_power_kw": -8.0,
            "motor_thermal_power_kw": -7.2,
            "inverter_thermal_power_kw": -4.8,
            "cabin_thermal_power_kw": 6.0,
            "auxiliary_power_kw": 26.0,
            "battery_version": 3,
            "motor_version": 4,
            "operating_state": "mixed",
            "limiting_reason": None,
            "fault_code": None,
            "version": 2,
            "simulation_time_ms": 60_000,
            "duplicate": False,
        },
        requested_by_user_id=uuid4(),
    )
    result, duplicate = await simulate_thermal_step(
        cast(AsyncSession, FakeSession(prior)),
        vehicle=current_vehicle,
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is True
    assert result.duplicate is True
    with pytest.raises(ThermalCommandConflictError):
        await simulate_thermal_step(
            cast(AsyncSession, FakeSession(prior)),
            vehicle=current_vehicle,
            command=command(duration_ms=120_000),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("versions", "error"),
    [
        ((9, 2, 3), ThermalStateVersionConflictError),
        ((1, 9, 3), ThermalBatteryVersionConflictError),
        ((1, 2, 9), ThermalMotorVersionConflictError),
    ],
)
async def test_independent_versions_are_enforced(
    versions: tuple[int, int, int], error: type[Exception]
) -> None:
    current_vehicle = vehicle()
    state = thermal(current_vehicle)
    pack = battery(current_vehicle)
    drive = motor(current_vehicle)
    state.version, pack.version, drive.version = versions
    with pytest.raises(error):
        await simulate_thermal_step(
            cast(AsyncSession, FakeSession(None, pack, drive, state)),
            vehicle=current_vehicle,
            command=command(),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
