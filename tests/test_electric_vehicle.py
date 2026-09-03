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
    BatterySimulationCommandConflictError,
    BatteryStateVersionConflictError,
)
from atep.electric_vehicle.models import BatteryPackState, BatterySimulationStep
from atep.electric_vehicle.schemas import BatteryPackCreate, BatterySimulationCommand
from atep.electric_vehicle.service import (
    battery_response,
    create_battery_pack,
    simulate_battery_step,
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


def reference_vehicle() -> Vehicle:
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


def reference_pack(vehicle: Vehicle, *, temperature_c: float = 25.0) -> BatteryPackState:
    cells = [
        {
            "index": index + 1,
            "voltage_v": round(3.42 + (index - 47.5) * 0.0002, 4),
            "temperature_c": round(temperature_c + (index - 47.5) * 0.002, 3),
            "soc_pct": 80.0,
        }
        for index in range(96)
    ]
    now = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
    return BatteryPackState(
        id=uuid4(),
        vehicle_id=vehicle.id,
        chemistry="lfp",
        series_cell_count=96,
        nominal_capacity_ah=100.0,
        nominal_cell_voltage_v=3.2,
        internal_resistance_ohm=0.08,
        soc_pct=80.0,
        soh_pct=100.0,
        pack_voltage_v=328.32,
        pack_current_a=0.0,
        pack_temperature_c=temperature_c,
        contactor_state="open",
        operating_state="normal",
        cells=cells,
        version=1,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )


def test_battery_contracts_have_safe_physical_bounds() -> None:
    command = BatteryPackCreate(series_cell_count=96, initial_soc_pct=75.0)
    assert command.series_cell_count == 96
    with pytest.raises(ValidationError, match="greater than or equal to 4"):
        BatteryPackCreate(series_cell_count=3)
    with pytest.raises(ValidationError, match="less than or equal to 1000"):
        BatterySimulationCommand(
            command_id="step-1",
            duration_ms=1_000,
            pack_current_a=1_001.0,
            expected_version=1,
        )


@pytest.mark.asyncio
async def test_create_battery_pack_records_minimized_atomic_evidence() -> None:
    vehicle = reference_vehicle()
    fake = FakeSession(None)
    pack = await create_battery_pack(
        cast(AsyncSession, fake),
        vehicle=vehicle,
        command=BatteryPackCreate(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )

    assert pack.series_cell_count == 96
    assert len(pack.cells) == 96
    assert pack.contactor_state == "open"
    events = [item for item in fake.added if isinstance(item, OutboxEvent)]
    audits = [item for item in fake.added if isinstance(item, AuditRecord)]
    assert [item.event_type for item in events] == ["atep.electric_vehicle.battery.created.v1"]
    assert audits[0].action == "electric_vehicle.battery_created"
    assert "cells" not in events[0].payload


@pytest.mark.asyncio
async def test_battery_step_is_deterministic_and_updates_soc_thermal_and_bms_state() -> None:
    vehicle = reference_vehicle()
    pack = reference_pack(vehicle)
    fake = FakeSession(None, pack)
    result, duplicate = await simulate_battery_step(
        cast(AsyncSession, fake),
        vehicle=vehicle,
        command=BatterySimulationCommand(
            command_id="drive-001",
            duration_ms=3_600_000,
            pack_current_a=10.0,
            ambient_temperature_c=25.0,
            expected_version=1,
        ),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )

    assert duplicate is False
    assert result.soc_pct == 70.0
    assert result.pack_temperature_c == 25.096
    assert result.pack_current_a == 10.0
    assert result.contactor_state == "closed"
    assert result.operating_state == "normal"
    assert result.version == 2
    assert result.simulation_time_ms == 3_600_000
    assert len(result.cells) == 96
    events = [item for item in fake.added if isinstance(item, OutboxEvent)]
    assert events[0].event_type == "atep.electric_vehicle.battery.step.completed.v1"
    assert "cells" not in events[0].payload


@pytest.mark.asyncio
async def test_negative_current_charges_pack_deterministically() -> None:
    vehicle = reference_vehicle()
    pack = reference_pack(vehicle)
    result, duplicate = await simulate_battery_step(
        cast(AsyncSession, FakeSession(None, pack)),
        vehicle=vehicle,
        command=BatterySimulationCommand(
            command_id="charge-001",
            duration_ms=3_600_000,
            pack_current_a=-10.0,
            ambient_temperature_c=25.0,
            expected_version=1,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert duplicate is False
    assert result.soc_pct == 90.0
    assert result.pack_current_a == -10.0
    assert result.operating_state == "normal"
    assert result.contactor_state == "closed"


@pytest.mark.asyncio
async def test_low_soc_enters_warning_without_opening_contactors() -> None:
    vehicle = reference_vehicle()
    pack = reference_pack(vehicle)
    pack.soc_pct = 10.0
    result, _duplicate = await simulate_battery_step(
        cast(AsyncSession, FakeSession(None, pack)),
        vehicle=vehicle,
        command=BatterySimulationCommand(
            command_id="low-soc-001",
            duration_ms=1_000,
            pack_current_a=0.0,
            ambient_temperature_c=25.0,
            expected_version=1,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.soc_pct == 10.0
    assert result.operating_state == "warning"
    assert result.contactor_state == "closed"
    assert result.pack_current_a == 0.0


@pytest.mark.asyncio
async def test_bms_opens_contactors_at_overtemperature_boundary() -> None:
    vehicle = reference_vehicle()
    pack = reference_pack(vehicle, temperature_c=59.0)
    fake = FakeSession(None, pack)
    result, _duplicate = await simulate_battery_step(
        cast(AsyncSession, fake),
        vehicle=vehicle,
        command=BatterySimulationCommand(
            command_id="overtemperature-001",
            duration_ms=60_000,
            pack_current_a=1_000.0,
            ambient_temperature_c=40.0,
            expected_version=1,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.pack_temperature_c == 60.0
    assert result.pack_current_a == 0.0
    assert result.operating_state == "protection"
    assert result.contactor_state == "open"


@pytest.mark.asyncio
async def test_battery_step_exact_replay_uses_persisted_snapshot() -> None:
    vehicle = reference_vehicle()
    pack = reference_pack(vehicle)
    snapshot = battery_response(pack, vehicle).model_dump(mode="json")
    existing = BatterySimulationStep(
        id=uuid4(),
        vehicle_id=vehicle.id,
        command_id="step-replay",
        duration_ms=1_000,
        requested_current_a=5.0,
        ambient_temperature_c=25.0,
        previous_version=1,
        state_version=2,
        result=snapshot,
        requested_by_user_id=uuid4(),
    )
    fake = FakeSession(existing)
    result, duplicate = await simulate_battery_step(
        cast(AsyncSession, fake),
        vehicle=vehicle,
        command=BatterySimulationCommand(
            command_id="step-replay",
            duration_ms=1_000,
            pack_current_a=5.0,
            ambient_temperature_c=25.0,
            expected_version=1,
        ),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert duplicate is True
    assert result.duplicate is True
    assert result.soc_pct == 80.0
    assert fake.added == []


@pytest.mark.asyncio
async def test_changed_command_reuse_and_stale_versions_fail_stably() -> None:
    vehicle = reference_vehicle()
    pack = reference_pack(vehicle)
    existing = BatterySimulationStep(
        id=uuid4(),
        vehicle_id=vehicle.id,
        command_id="step-conflict",
        duration_ms=1_000,
        requested_current_a=5.0,
        ambient_temperature_c=25.0,
        previous_version=1,
        state_version=2,
        result=battery_response(pack, vehicle).model_dump(mode="json"),
        requested_by_user_id=uuid4(),
    )
    with pytest.raises(BatterySimulationCommandConflictError):
        await simulate_battery_step(
            cast(AsyncSession, FakeSession(existing)),
            vehicle=vehicle,
            command=BatterySimulationCommand(
                command_id="step-conflict",
                duration_ms=2_000,
                pack_current_a=5.0,
                expected_version=1,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )

    with pytest.raises(BatteryStateVersionConflictError) as exc:
        await simulate_battery_step(
            cast(AsyncSession, FakeSession(None, pack)),
            vehicle=vehicle,
            command=BatterySimulationCommand(
                command_id="step-stale",
                duration_ms=1_000,
                pack_current_a=5.0,
                expected_version=2,
            ),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert exc.value.details == {"current_version": 1}
