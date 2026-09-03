from math import isclose
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    BatteryPackAlreadyExistsError,
    BatterySimulationCommandConflictError,
    BatteryStateVersionConflictError,
    ResourceNotFoundError,
)
from atep.electric_vehicle.models import BatteryPackState, BatterySimulationStep
from atep.electric_vehicle.schemas import (
    BatteryContactorState,
    BatteryOperatingState,
    BatteryPackCreate,
    BatteryPackResponse,
    BatterySimulationCommand,
)
from atep.events.outbox import enqueue_event
from atep.vehicles.models import Vehicle


def _cell_voltage(soc_pct: float, nominal_voltage: float) -> float:
    return max(2.5, min(4.3, nominal_voltage - 0.2 + (soc_pct / 100.0) * 0.4))


def _cells(
    *, count: int, soc_pct: float, temperature_c: float, nominal_voltage: float
) -> list[dict[str, Any]]:
    centre = (count - 1) / 2
    return [
        {
            "index": index + 1,
            "voltage_v": round(
                _cell_voltage(soc_pct, nominal_voltage) + (index - centre) * 0.0002, 4
            ),
            "temperature_c": round(temperature_c + (index - centre) * 0.002, 3),
            "soc_pct": round(soc_pct, 4),
        }
        for index in range(count)
    ]


def battery_response(
    pack: BatteryPackState, vehicle: Vehicle, *, duplicate: bool = False
) -> BatteryPackResponse:
    cells = pack.cells
    voltages = [float(cell["voltage_v"]) for cell in cells]
    temperatures = [float(cell["temperature_c"]) for cell in cells]
    nominal_energy = (
        pack.series_cell_count * pack.nominal_cell_voltage_v * pack.nominal_capacity_ah / 1000.0
    )
    return BatteryPackResponse(
        vehicle_id=vehicle.identifier,
        chemistry=pack.chemistry,
        series_cell_count=pack.series_cell_count,
        nominal_capacity_ah=pack.nominal_capacity_ah,
        nominal_energy_kwh=round(nominal_energy, 3),
        soc_pct=pack.soc_pct,
        soh_pct=pack.soh_pct,
        pack_voltage_v=pack.pack_voltage_v,
        pack_current_a=pack.pack_current_a,
        pack_power_kw=round(pack.pack_voltage_v * pack.pack_current_a / 1000.0, 3),
        pack_temperature_c=pack.pack_temperature_c,
        minimum_cell_voltage_v=min(voltages),
        maximum_cell_voltage_v=max(voltages),
        minimum_cell_temperature_c=min(temperatures),
        maximum_cell_temperature_c=max(temperatures),
        contactor_state=pack.contactor_state,
        operating_state=pack.operating_state,
        cells=cells,
        version=pack.version,
        simulation_time_ms=pack.simulation_time_ms,
        duplicate=duplicate,
    )


async def create_battery_pack(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: BatteryPackCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> BatteryPackState:
    existing = await session.scalar(
        select(BatteryPackState).where(BatteryPackState.vehicle_id == vehicle.id)
    )
    if existing is not None:
        raise BatteryPackAlreadyExistsError()
    cells = _cells(
        count=command.series_cell_count,
        soc_pct=command.initial_soc_pct,
        temperature_c=command.initial_temperature_c,
        nominal_voltage=command.nominal_cell_voltage_v,
    )
    pack = BatteryPackState(
        vehicle_id=vehicle.id,
        chemistry=command.chemistry.value,
        series_cell_count=command.series_cell_count,
        nominal_capacity_ah=command.nominal_capacity_ah,
        nominal_cell_voltage_v=command.nominal_cell_voltage_v,
        internal_resistance_ohm=command.internal_resistance_ohm,
        soc_pct=command.initial_soc_pct,
        soh_pct=command.initial_soh_pct,
        pack_voltage_v=round(sum(float(cell["voltage_v"]) for cell in cells), 3),
        pack_current_a=0.0,
        pack_temperature_c=command.initial_temperature_c,
        contactor_state=BatteryContactorState.OPEN.value,
        operating_state=BatteryOperatingState.NORMAL.value,
        cells=cells,
        version=1,
        simulation_time_ms=0,
    )
    try:
        async with session.begin_nested():
            session.add(pack)
            await session.flush()
    except IntegrityError as exc:
        raise BatteryPackAlreadyExistsError() from exc
    payload = {
        "vehicle_id": vehicle.identifier,
        "chemistry": pack.chemistry,
        "series_cell_count": pack.series_cell_count,
        "nominal_capacity_ah": pack.nominal_capacity_ah,
        "version": pack.version,
    }
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.battery.created.v1",
        aggregate_type="battery_pack",
        aggregate_id=pack.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.battery_created",
        resource_type="battery_pack",
        resource_id=pack.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return pack


async def require_battery_pack(
    session: AsyncSession, *, vehicle: Vehicle, for_update: bool = False
) -> BatteryPackState:
    query = select(BatteryPackState).where(BatteryPackState.vehicle_id == vehicle.id)
    if for_update:
        query = query.with_for_update()
    pack = await session.scalar(query)
    if pack is None:
        raise ResourceNotFoundError("battery_pack")
    return pack


def _same_step(step: BatterySimulationStep, command: BatterySimulationCommand) -> bool:
    return (
        step.duration_ms == command.duration_ms
        and isclose(step.requested_current_a, command.pack_current_a)
        and isclose(step.ambient_temperature_c, command.ambient_temperature_c)
        and step.previous_version == command.expected_version
    )


def _operating_state(soc_pct: float, temperature_c: float, current_a: float) -> tuple[str, str]:
    protection = temperature_c >= 60.0 or temperature_c <= -30.0
    protection = protection or (soc_pct <= 0.0 and current_a > 0.0)
    protection = protection or (soc_pct >= 100.0 and current_a < 0.0)
    if protection:
        return BatteryOperatingState.PROTECTION.value, BatteryContactorState.OPEN.value
    warning = temperature_c >= 50.0 or temperature_c <= -20.0 or soc_pct <= 10.0
    state = BatteryOperatingState.WARNING.value if warning else BatteryOperatingState.NORMAL.value
    return state, BatteryContactorState.CLOSED.value


async def simulate_battery_step(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: BatterySimulationCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[BatteryPackResponse, bool]:
    existing = await session.scalar(
        select(BatterySimulationStep).where(
            BatterySimulationStep.vehicle_id == vehicle.id,
            BatterySimulationStep.command_id == command.command_id,
        )
    )
    if existing is not None:
        if not _same_step(existing, command):
            raise BatterySimulationCommandConflictError()
        return BatteryPackResponse.model_validate({**existing.result, "duplicate": True}), True

    pack = await require_battery_pack(session, vehicle=vehicle, for_update=True)
    if pack.version != command.expected_version:
        raise BatteryStateVersionConflictError(current_version=pack.version)

    hours = command.duration_ms / 3_600_000.0
    usable_capacity = pack.nominal_capacity_ah * pack.soh_pct / 100.0
    soc_pct = max(
        0.0, min(100.0, pack.soc_pct - command.pack_current_a * hours / usable_capacity * 100.0)
    )
    seconds = command.duration_ms / 1000.0
    heat_w = command.pack_current_a**2 * pack.internal_resistance_ohm
    thermal_mass_j_per_c = 300_000.0
    passive_cooling_w_per_c = 35.0
    predicted_temperature_c = (
        pack.pack_temperature_c
        + (
            heat_w
            - passive_cooling_w_per_c * (pack.pack_temperature_c - command.ambient_temperature_c)
        )
        * seconds
        / thermal_mass_j_per_c
    )
    temperature_c = max(-30.0, min(60.0, predicted_temperature_c))
    operating_state, contactor_state = _operating_state(
        soc_pct, temperature_c, command.pack_current_a
    )
    applied_current = (
        0.0 if contactor_state == BatteryContactorState.OPEN.value else command.pack_current_a
    )
    cells = _cells(
        count=pack.series_cell_count,
        soc_pct=soc_pct,
        temperature_c=temperature_c,
        nominal_voltage=pack.nominal_cell_voltage_v,
    )
    previous_version = pack.version
    pack.soc_pct = round(soc_pct, 4)
    pack.pack_temperature_c = round(temperature_c, 3)
    pack.pack_current_a = applied_current
    pack.pack_voltage_v = round(sum(float(cell["voltage_v"]) for cell in cells), 3)
    pack.operating_state = operating_state
    pack.contactor_state = contactor_state
    pack.cells = cells
    pack.version += 1
    pack.simulation_time_ms += command.duration_ms
    rendered = battery_response(pack, vehicle)
    result = rendered.model_dump(mode="json")
    evidence = {
        "soc_pct": pack.soc_pct,
        "soh_pct": pack.soh_pct,
        "pack_voltage_v": pack.pack_voltage_v,
        "pack_current_a": pack.pack_current_a,
        "pack_temperature_c": pack.pack_temperature_c,
        "operating_state": pack.operating_state,
        "contactor_state": pack.contactor_state,
        "version": pack.version,
        "simulation_time_ms": pack.simulation_time_ms,
    }
    step = BatterySimulationStep(
        vehicle_id=vehicle.id,
        command_id=command.command_id,
        duration_ms=command.duration_ms,
        requested_current_a=command.pack_current_a,
        ambient_temperature_c=command.ambient_temperature_c,
        previous_version=previous_version,
        state_version=pack.version,
        result=result,
        requested_by_user_id=actor_user_id,
    )
    session.add(step)
    await session.flush()
    payload = {"vehicle_id": vehicle.identifier, "command_id": command.command_id, **evidence}
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.battery.step.completed.v1",
        aggregate_type="battery_pack",
        aggregate_id=pack.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.battery_step_completed",
        resource_type="battery_pack",
        resource_id=pack.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return rendered, False
