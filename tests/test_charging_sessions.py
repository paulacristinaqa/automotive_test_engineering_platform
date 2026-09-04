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
    ChargingBatteryVersionConflictError,
    ChargingCommandConflictError,
    ChargingStateVersionConflictError,
    ChargingTransitionError,
)
from atep.electric_vehicle.models import (
    BatteryPackState,
    ChargingCommandStep,
    ChargingSystemState,
)
from atep.electric_vehicle.schemas import ChargingCommand, ChargingSystemCreate
from atep.electric_vehicle.service import (
    _charging_acceptance_kw,
    create_charging_system,
    execute_charging_command,
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
    now = datetime(2026, 9, 4, 15, 0, tzinfo=UTC)
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
    soc_pct: float = 50.0,
    temperature_c: float = 25.0,
    version: int = 2,
) -> BatteryPackState:
    now = datetime(2026, 9, 4, 15, 0, tzinfo=UTC)
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
        pack_voltage_v=307.2,
        pack_current_a=0.0,
        pack_temperature_c=temperature_c,
        contactor_state="open",
        operating_state="normal",
        cells=[
            {
                "index": index + 1,
                "voltage_v": 3.2,
                "temperature_c": temperature_c,
                "soc_pct": soc_pct,
            }
            for index in range(96)
        ],
        version=version,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )


def charging(current_vehicle: Vehicle, *, operating_state: str = "idle") -> ChargingSystemState:
    now = datetime(2026, 9, 4, 15, 0, tzinfo=UTC)
    return ChargingSystemState(
        id=uuid4(),
        vehicle_id=current_vehicle.id,
        max_ac_power_kw=22.0,
        max_dc_power_kw=180.0,
        charging_efficiency_pct=92.0,
        session_id=None,
        connector_type=None,
        target_soc_pct=80.0,
        requested_power_kw=0.0,
        delivered_power_kw=0.0,
        charged_energy_kwh=0.0,
        session_energy_kwh=0.0,
        battery_charge_acceptance_kw=0.0,
        operating_state=operating_state,
        limiting_reason=None,
        fault_code=None,
        version=1,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )


def command(action: str, **changes: Any) -> ChargingCommand:
    values: dict[str, Any] = {
        "command_id": f"charge-{action}-001",
        "action": action,
        "expected_version": 1,
        "expected_battery_version": 2,
    }
    if action == "start":
        values.update(
            session_id="session-001",
            connector_type="ac_type_2",
            target_soc_pct=80.0,
            requested_power_kw=22.0,
        )
    if action == "charge":
        values.update(duration_ms=3_600_000, requested_power_kw=22.0)
    if action == "inject_fault":
        values["fault_code"] = "EVSE_COMMUNICATION_LOST"
    values.update(changes)
    return ChargingCommand(**values)


def test_charging_contracts_are_bounded_and_action_specific() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 50"):
        ChargingSystemCreate(max_ac_power_kw=51.0)
    with pytest.raises(ValidationError, match="start requires"):
        command("start", session_id=None)
    with pytest.raises(ValidationError, match="positive duration"):
        command("charge", duration_ms=0)


@pytest.mark.asyncio
async def test_create_charging_system_records_atomic_evidence() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    session = FakeSession(None)

    state = await create_charging_system(
        cast(AsyncSession, session),
        vehicle=current_vehicle,
        pack=pack,
        command=ChargingSystemCreate(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )

    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    audits = [item for item in session.added if isinstance(item, AuditRecord)]
    assert state.operating_state == "idle"
    assert events[0].event_type == "atep.electric_vehicle.charging_system.created.v1"
    assert audits[0].action == "electric_vehicle.charging_system_created"


@pytest.mark.asyncio
async def test_start_session_closes_contactors_and_is_auditable() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    state = charging(current_vehicle)
    session = FakeSession(None, pack, state)

    result, duplicate = await execute_charging_command(
        cast(AsyncSession, session),
        vehicle=current_vehicle,
        command=command("start"),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )

    events = [item for item in session.added if isinstance(item, OutboxEvent)]
    assert duplicate is False
    assert result.session_id == "session-001"
    assert result.operating_state == "charging"
    assert pack.contactor_state == "closed"
    assert pack.version == 3
    assert events[0].event_type == "atep.electric_vehicle.charging.command.completed.v1"
    assert "cells" not in events[0].payload


@pytest.mark.asyncio
async def test_ac_charge_updates_energy_soc_and_versions() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    pack.contactor_state = "closed"
    state = charging(current_vehicle, operating_state="charging")
    state.session_id = "session-001"
    state.connector_type = "ac_type_2"
    state.requested_power_kw = 22.0
    session = FakeSession(None, pack, state)

    result, _ = await execute_charging_command(
        cast(AsyncSession, session),
        vehicle=current_vehicle,
        command=command("charge", duration_ms=600_000),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.charged_energy_kwh == pytest.approx(3.373333)
    assert result.delivered_power_kw == pytest.approx(22.0)
    assert result.battery_soc_pct > 50.0
    assert result.battery_version == 3
    assert result.version == 2
    assert result.simulation_time_ms == 600_000


@pytest.mark.asyncio
async def test_dc_charge_respects_battery_and_connector_power_limits() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    pack.contactor_state = "closed"
    state = charging(current_vehicle, operating_state="charging")
    state.session_id = "session-001"
    state.connector_type = "dc_ccs"
    state.target_soc_pct = 100.0
    state.requested_power_kw = 500.0

    result, _ = await execute_charging_command(
        cast(AsyncSession, FakeSession(None, pack, state)),
        vehicle=current_vehicle,
        command=command("charge", duration_ms=60_000, requested_power_kw=500.0),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.delivered_power_kw < 180.0
    assert result.limiting_reason == "charge_power_limited"


def test_dc_charge_curve_tapers_above_eighty_percent() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle, soc_pct=90.0)
    pack.contactor_state = "closed"
    state = charging(current_vehicle, operating_state="charging")
    state.connector_type = "dc_ccs"
    state.target_soc_pct = 100.0

    acceptance = _charging_acceptance_kw(pack, state, "dc_ccs")

    assert acceptance == pytest.approx(46.08)


@pytest.mark.asyncio
async def test_charge_stops_exactly_at_target_soc() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle, soc_pct=79.9)
    pack.contactor_state = "closed"
    state = charging(current_vehicle, operating_state="charging")
    state.session_id = "session-001"
    state.connector_type = "dc_ccs"
    state.target_soc_pct = 80.0
    state.requested_power_kw = 180.0
    session = FakeSession(None, pack, state)

    result, _ = await execute_charging_command(
        cast(AsyncSession, session),
        vehicle=current_vehicle,
        command=command("charge", requested_power_kw=180.0),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.battery_soc_pct == 80.0
    assert result.operating_state == "completed"
    assert result.limiting_reason == "target_soc_reached"
    assert pack.contactor_state == "open"


@pytest.mark.asyncio
async def test_unsafe_temperature_blocks_energy_transfer() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle, temperature_c=-1.0)
    pack.contactor_state = "closed"
    state = charging(current_vehicle, operating_state="charging")
    state.session_id = "session-001"
    state.connector_type = "dc_ccs"
    session = FakeSession(None, pack, state)

    result, _ = await execute_charging_command(
        cast(AsyncSession, session),
        vehicle=current_vehicle,
        command=command("charge", requested_power_kw=100.0),
        actor_user_id=uuid4(),
        correlation_id=None,
    )

    assert result.charged_energy_kwh == 0.0
    assert result.delivered_power_kw == 0.0
    assert result.limiting_reason == "battery_temperature_limit"


@pytest.mark.asyncio
async def test_pause_resume_stop_and_fault_lifecycle() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    pack.contactor_state = "closed"
    state = charging(current_vehicle, operating_state="charging")
    state.session_id = "session-001"
    state.connector_type = "ac_type_2"

    paused, _ = await execute_charging_command(
        cast(AsyncSession, FakeSession(None, pack, state)),
        vehicle=current_vehicle,
        command=command("pause"),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert paused.operating_state == "paused"
    assert pack.contactor_state == "open"

    resumed, _ = await execute_charging_command(
        cast(AsyncSession, FakeSession(None, pack, state)),
        vehicle=current_vehicle,
        command=command("resume", expected_version=2, expected_battery_version=3),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert resumed.operating_state == "charging"

    faulted, _ = await execute_charging_command(
        cast(AsyncSession, FakeSession(None, pack, state)),
        vehicle=current_vehicle,
        command=command("inject_fault", expected_version=3, expected_battery_version=4),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert faulted.operating_state == "faulted"
    assert faulted.fault_code == "EVSE_COMMUNICATION_LOST"

    cleared, _ = await execute_charging_command(
        cast(AsyncSession, FakeSession(None, pack, state)),
        vehicle=current_vehicle,
        command=command("clear_fault", expected_version=4, expected_battery_version=5),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert cleared.operating_state == "idle"
    assert cleared.fault_code is None


@pytest.mark.asyncio
async def test_invalid_transition_is_stable() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    state = charging(current_vehicle)

    with pytest.raises(ChargingTransitionError):
        await execute_charging_command(
            cast(AsyncSession, FakeSession(None, pack, state)),
            vehicle=current_vehicle,
            command=command("charge"),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_exact_replay_and_changed_reuse() -> None:
    current_vehicle = vehicle()
    original = command("start")
    step = ChargingCommandStep(
        id=uuid4(),
        vehicle_id=current_vehicle.id,
        command_id=original.command_id,
        action="start",
        session_id="session-001",
        connector_type="ac_type_2",
        duration_ms=0,
        requested_power_kw=22.0,
        target_soc_pct=80.0,
        fault_code=None,
        previous_version=1,
        state_version=2,
        previous_battery_version=2,
        battery_state_version=3,
        result={
            "vehicle_id": current_vehicle.identifier,
            "max_ac_power_kw": 22.0,
            "max_dc_power_kw": 180.0,
            "charging_efficiency_pct": 92.0,
            "session_id": "session-001",
            "connector_type": "ac_type_2",
            "target_soc_pct": 80.0,
            "requested_power_kw": 22.0,
            "delivered_power_kw": 0.0,
            "charged_energy_kwh": 0.0,
            "session_energy_kwh": 0.0,
            "battery_charge_acceptance_kw": 22.0,
            "battery_soc_pct": 50.0,
            "battery_version": 3,
            "operating_state": "charging",
            "limiting_reason": None,
            "fault_code": None,
            "version": 2,
            "simulation_time_ms": 0,
            "duplicate": False,
        },
        requested_by_user_id=uuid4(),
    )

    replay, duplicate = await execute_charging_command(
        cast(AsyncSession, FakeSession(step)),
        vehicle=current_vehicle,
        command=original,
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert duplicate is True
    assert replay.duplicate is True

    with pytest.raises(ChargingCommandConflictError):
        await execute_charging_command(
            cast(AsyncSession, FakeSession(step)),
            vehicle=current_vehicle,
            command=command("start", target_soc_pct=90.0),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_charging_and_battery_version_conflicts_are_distinct() -> None:
    current_vehicle = vehicle()
    pack = battery(current_vehicle)
    state = charging(current_vehicle)
    state.version = 2

    with pytest.raises(ChargingStateVersionConflictError):
        await execute_charging_command(
            cast(AsyncSession, FakeSession(None, pack, state)),
            vehicle=current_vehicle,
            command=command("start"),
            actor_user_id=uuid4(),
            correlation_id=None,
        )

    state.version = 1
    pack.version = 3
    with pytest.raises(ChargingBatteryVersionConflictError):
        await execute_charging_command(
            cast(AsyncSession, FakeSession(None, pack, state)),
            vehicle=current_vehicle,
            command=command("start"),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
