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
    RangeBatteryVersionConflictError,
    RangeEstimationCommandConflictError,
    RangeStateVersionConflictError,
    RangeThermalVersionConflictError,
)
from atep.electric_vehicle.models import (
    BatteryPackState,
    RangeEstimationStep,
    RangeEstimatorState,
    ThermalManagementState,
)
from atep.electric_vehicle.schemas import RangeEstimationCommand, RangeEstimatorCreate
from atep.electric_vehicle.service import create_range_estimator, simulate_range_cycle
from atep.events.models import OutboxEvent
from atep.vehicles.models import Vehicle


class FakeSession:
    def __init__(self, *values: Any) -> None:
        self.values = list(values)
        self.added: list[Any] = []

    async def scalar(self, _: Any) -> Any:
        return self.values.pop(0) if self.values else None

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
    now = datetime(2026, 9, 4, tzinfo=UTC)
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


def battery(item: Vehicle, *, soc: float = 80.0) -> BatteryPackState:
    return BatteryPackState(
        vehicle_id=item.id,
        chemistry="lfp",
        series_cell_count=192,
        nominal_capacity_ah=200.0,
        nominal_cell_voltage_v=3.2,
        internal_resistance_ohm=0.08,
        soc_pct=soc,
        soh_pct=100.0,
        pack_voltage_v=614.4,
        pack_current_a=0.0,
        pack_temperature_c=25.0,
        contactor_state="closed",
        operating_state="normal",
        cells=[],
        version=2,
        simulation_time_ms=0,
    )


def thermal(item: Vehicle, *, auxiliary: float = 1.0) -> ThermalManagementState:
    return ThermalManagementState(
        vehicle_id=item.id,
        max_battery_thermal_power_kw=8.0,
        max_powertrain_thermal_power_kw=12.0,
        max_cabin_thermal_power_kw=8.0,
        battery_target_temperature_c=25.0,
        motor_target_temperature_c=70.0,
        inverter_target_temperature_c=60.0,
        cabin_target_temperature_c=22.0,
        cabin_temperature_c=22.0,
        battery_thermal_power_kw=0.0,
        motor_thermal_power_kw=0.0,
        inverter_thermal_power_kw=0.0,
        cabin_thermal_power_kw=0.0,
        auxiliary_power_kw=auxiliary,
        operating_state="standby",
        limiting_reason=None,
        fault_code=None,
        version=3,
        simulation_time_ms=0,
    )


def estimator(item: Vehicle, *, reserve: float = 5.0) -> RangeEstimatorState:
    return RangeEstimatorState(
        id=uuid4(),
        vehicle_id=item.id,
        **RangeEstimatorCreate(reserve_soc_pct=reserve).model_dump(),
        last_cycle_id=None,
        distance_km=0.0,
        traction_energy_kwh=0.0,
        auxiliary_energy_kwh=0.0,
        recovered_energy_kwh=0.0,
        net_energy_kwh=0.0,
        consumption_kwh_per_100km=0.0,
        estimated_range_km=0.0,
        operating_state="ready",
        limiting_reason=None,
        version=1,
        simulation_time_ms=0,
    )


def command(**changes: Any) -> RangeEstimationCommand:
    data: dict[str, Any] = {
        "command_id": "range-001",
        "cycle_id": "mixed-001",
        "segments": [
            {"duration_ms": 600_000, "speed_kph": 60.0},
            {"duration_ms": 60_000, "speed_kph": 40.0, "acceleration_mps2": -0.5},
        ],
        "expected_version": 1,
        "expected_battery_version": 2,
        "expected_thermal_version": 3,
    }
    data.update(changes)
    return RangeEstimationCommand(**data)


def test_range_contracts_are_bounded() -> None:
    with pytest.raises(ValidationError):
        RangeEstimatorCreate(reserve_soc_pct=31.0)
    with pytest.raises(ValidationError):
        command(segments=[])
    with pytest.raises(ValidationError):
        command(segments=[{"duration_ms": 10, "speed_kph": 20.0}])


@pytest.mark.asyncio
async def test_create_range_estimator_records_atomic_evidence() -> None:
    current = vehicle()
    session = FakeSession(None)
    state = await create_range_estimator(
        cast(AsyncSession, session),
        vehicle=current,
        pack=battery(current),
        thermal=thermal(current),
        command=RangeEstimatorCreate(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert state.operating_state == "ready"
    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert events[0].event_type == "atep.electric_vehicle.range_estimator.created.v1"
    assert audits[0].action == "electric_vehicle.range_estimator_created"


@pytest.mark.asyncio
async def test_cycle_estimates_consumption_range_and_regeneration() -> None:
    current = vehicle()
    session = FakeSession(None, battery(current), thermal(current), estimator(current))
    result, duplicate = await simulate_range_cycle(
        cast(AsyncSession, session),
        vehicle=current,
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert not duplicate
    assert result.distance_km > 10.0
    assert result.traction_energy_kwh > 0
    assert result.recovered_energy_kwh > 0
    assert result.auxiliary_energy_kwh > 0
    assert result.consumption_kwh_per_100km > 0
    assert result.estimated_range_km > 0
    assert result.operating_state == "completed"
    assert any(isinstance(item, RangeEstimationStep) for item in session.added)


@pytest.mark.asyncio
async def test_auxiliary_load_reduces_estimated_range() -> None:
    current = vehicle()
    low, _ = await simulate_range_cycle(
        cast(
            AsyncSession,
            FakeSession(
                None, battery(current), thermal(current, auxiliary=0.0), estimator(current)
            ),
        ),
        vehicle=current,
        command=command(command_id="low"),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    high, _ = await simulate_range_cycle(
        cast(
            AsyncSession,
            FakeSession(
                None, battery(current), thermal(current, auxiliary=8.0), estimator(current)
            ),
        ),
        vehicle=current,
        command=command(command_id="high"),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert high.consumption_kwh_per_100km > low.consumption_kwh_per_100km
    assert high.estimated_range_km < low.estimated_range_km


@pytest.mark.asyncio
async def test_stationary_cycle_is_limited_without_division_by_zero() -> None:
    current = vehicle()
    result, _ = await simulate_range_cycle(
        cast(
            AsyncSession,
            FakeSession(None, battery(current), thermal(current), estimator(current)),
        ),
        vehicle=current,
        command=command(
            command_id="stationary",
            segments=[{"duration_ms": 60_000, "speed_kph": 0.0}],
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert result.consumption_kwh_per_100km == 0.0
    assert result.estimated_range_km == 0.0
    assert result.limiting_reason == "insufficient_distance"


@pytest.mark.asyncio
async def test_reserve_soc_produces_zero_available_range() -> None:
    current = vehicle()
    result, _ = await simulate_range_cycle(
        cast(
            AsyncSession,
            FakeSession(
                None,
                battery(current, soc=5.0),
                thermal(current),
                estimator(current, reserve=5.0),
            ),
        ),
        vehicle=current,
        command=command(command_id="reserve"),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert result.available_energy_kwh == 0.0
    assert result.estimated_range_km == 0.0
    assert result.limiting_reason == "reserve_reached"


@pytest.mark.asyncio
async def test_duplicate_is_replayed_and_changed_reuse_conflicts() -> None:
    current = vehicle()
    original = command()
    stored = RangeEstimationStep(
        vehicle_id=current.id,
        command_id=original.command_id,
        cycle_id=original.cycle_id,
        segments=[item.model_dump(mode="json") for item in original.segments],
        duration_ms=660_000,
        previous_version=1,
        state_version=2,
        previous_battery_version=2,
        previous_thermal_version=3,
        result={
            "vehicle_id": current.identifier,
            "cycle_id": original.cycle_id,
            "distance_km": 10.0,
            "duration_ms": 660000,
            "traction_energy_kwh": 2.0,
            "auxiliary_energy_kwh": 0.2,
            "recovered_energy_kwh": 0.1,
            "net_energy_kwh": 2.1,
            "consumption_kwh_per_100km": 21.0,
            "available_energy_kwh": 90.0,
            "estimated_range_km": 428.57,
            "battery_soc_pct": 80.0,
            "battery_version": 2,
            "thermal_version": 3,
            "operating_state": "completed",
            "limiting_reason": None,
            "version": 2,
            "duplicate": False,
        },
        requested_by_user_id=uuid4(),
    )
    replay, duplicate = await simulate_range_cycle(
        cast(AsyncSession, FakeSession(stored)),
        vehicle=current,
        command=original,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate and replay.duplicate
    with pytest.raises(RangeEstimationCommandConflictError):
        await simulate_range_cycle(
            cast(AsyncSession, FakeSession(stored)),
            vehicle=current,
            command=command(cycle_id="other"),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"expected_version": 9}, RangeStateVersionConflictError),
        ({"expected_battery_version": 9}, RangeBatteryVersionConflictError),
        ({"expected_thermal_version": 9}, RangeThermalVersionConflictError),
    ],
)
async def test_optimistic_version_conflicts(
    changes: dict[str, int], error: type[Exception]
) -> None:
    current = vehicle()
    with pytest.raises(error):
        await simulate_range_cycle(
            cast(
                AsyncSession,
                FakeSession(None, battery(current), thermal(current), estimator(current)),
            ),
            vehicle=current,
            command=command(**changes),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
