from math import isclose, pi
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
    MotorInverterAlreadyExistsError,
    MotorSimulationCommandConflictError,
    MotorStateVersionConflictError,
    ResourceNotFoundError,
)
from atep.electric_vehicle.models import (
    BatteryPackState,
    BatterySimulationStep,
    MotorInverterState,
    MotorSimulationStep,
)
from atep.electric_vehicle.schemas import (
    BatteryContactorState,
    BatteryOperatingState,
    BatteryPackCreate,
    BatteryPackResponse,
    BatterySimulationCommand,
    DriveMode,
    MotorInverterCreate,
    MotorInverterResponse,
    MotorSimulationCommand,
    PowertrainOperatingState,
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


_DRIVE_MODE_FACTOR = {
    DriveMode.ECO.value: 0.60,
    DriveMode.NORMAL.value: 0.85,
    DriveMode.SPORT.value: 1.00,
}


def _battery_power_limit(pack: BatteryPackState, inverter_limit_kw: float) -> float:
    if pack.contactor_state != BatteryContactorState.CLOSED.value:
        return 0.0
    if pack.operating_state == BatteryOperatingState.PROTECTION.value:
        return 0.0
    current_limit_a = (
        600.0 if pack.operating_state == BatteryOperatingState.WARNING.value else 1000.0
    )
    return round(min(inverter_limit_kw, pack.pack_voltage_v * current_limit_a / 1000.0), 3)


def motor_inverter_response(
    state: MotorInverterState,
    vehicle: Vehicle,
    pack: BatteryPackState,
    *,
    duplicate: bool = False,
) -> MotorInverterResponse:
    return MotorInverterResponse(
        vehicle_id=vehicle.identifier,
        max_torque_nm=state.max_torque_nm,
        max_speed_rpm=state.max_speed_rpm,
        max_inverter_power_kw=state.max_inverter_power_kw,
        base_efficiency_pct=state.base_efficiency_pct,
        requested_torque_nm=state.requested_torque_nm,
        delivered_torque_nm=state.delivered_torque_nm,
        motor_speed_rpm=state.motor_speed_rpm,
        mechanical_power_kw=state.mechanical_power_kw,
        electrical_power_kw=state.electrical_power_kw,
        efficiency_pct=state.efficiency_pct,
        power_loss_kw=state.power_loss_kw,
        battery_power_limit_kw=_battery_power_limit(pack, state.max_inverter_power_kw),
        motor_temperature_c=state.motor_temperature_c,
        inverter_temperature_c=state.inverter_temperature_c,
        drive_mode=state.drive_mode,
        operating_state=state.operating_state,
        limiting_reason=state.limiting_reason,
        version=state.version,
        simulation_time_ms=state.simulation_time_ms,
        duplicate=duplicate,
    )


async def create_motor_inverter(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    pack: BatteryPackState,
    command: MotorInverterCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> MotorInverterState:
    existing = await session.scalar(
        select(MotorInverterState).where(MotorInverterState.vehicle_id == vehicle.id)
    )
    if existing is not None:
        raise MotorInverterAlreadyExistsError()
    state = MotorInverterState(
        vehicle_id=vehicle.id,
        max_torque_nm=command.max_torque_nm,
        max_speed_rpm=command.max_speed_rpm,
        max_inverter_power_kw=command.max_inverter_power_kw,
        base_efficiency_pct=command.base_efficiency_pct,
        requested_torque_nm=0.0,
        delivered_torque_nm=0.0,
        motor_speed_rpm=0,
        mechanical_power_kw=0.0,
        electrical_power_kw=0.0,
        efficiency_pct=command.base_efficiency_pct,
        power_loss_kw=0.0,
        motor_temperature_c=command.initial_motor_temperature_c,
        inverter_temperature_c=command.initial_inverter_temperature_c,
        drive_mode=DriveMode.NORMAL.value,
        operating_state=PowertrainOperatingState.STANDBY.value,
        limiting_reason="battery_unavailable"
        if _battery_power_limit(pack, command.max_inverter_power_kw) == 0.0
        else None,
        version=1,
        simulation_time_ms=0,
    )
    try:
        async with session.begin_nested():
            session.add(state)
            await session.flush()
    except IntegrityError as exc:
        raise MotorInverterAlreadyExistsError() from exc
    payload = {
        "vehicle_id": vehicle.identifier,
        "max_torque_nm": state.max_torque_nm,
        "max_speed_rpm": state.max_speed_rpm,
        "max_inverter_power_kw": state.max_inverter_power_kw,
        "version": state.version,
    }
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.motor_inverter.created.v1",
        aggregate_type="motor_inverter",
        aggregate_id=state.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.motor_inverter_created",
        resource_type="motor_inverter",
        resource_id=state.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return state


async def require_motor_inverter(
    session: AsyncSession, *, vehicle: Vehicle, for_update: bool = False
) -> MotorInverterState:
    query = select(MotorInverterState).where(MotorInverterState.vehicle_id == vehicle.id)
    if for_update:
        query = query.with_for_update()
    state = await session.scalar(query)
    if state is None:
        raise ResourceNotFoundError("motor_inverter")
    return state


def _same_motor_step(step: MotorSimulationStep, command: MotorSimulationCommand) -> bool:
    return (
        step.duration_ms == command.duration_ms
        and isclose(step.requested_torque_nm, command.requested_torque_nm)
        and step.motor_speed_rpm == command.motor_speed_rpm
        and step.drive_mode == command.drive_mode.value
        and isclose(step.ambient_temperature_c, command.ambient_temperature_c)
        and step.previous_version == command.expected_version
    )


def _efficiency_pct(state: MotorInverterState, torque_nm: float, speed_rpm: int) -> float:
    load_ratio = min(1.0, torque_nm / state.max_torque_nm)
    speed_ratio = min(1.0, speed_rpm / state.max_speed_rpm)
    efficiency = state.base_efficiency_pct - 6.0 * (1.0 - load_ratio) ** 2 - 4.0 * speed_ratio**2
    return round(max(80.0, min(state.base_efficiency_pct, efficiency)), 3)


async def simulate_motor_step(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: MotorSimulationCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[MotorInverterResponse, bool]:
    existing = await session.scalar(
        select(MotorSimulationStep).where(
            MotorSimulationStep.vehicle_id == vehicle.id,
            MotorSimulationStep.command_id == command.command_id,
        )
    )
    if existing is not None:
        if not _same_motor_step(existing, command):
            raise MotorSimulationCommandConflictError()
        return MotorInverterResponse.model_validate({**existing.result, "duplicate": True}), True

    state = await require_motor_inverter(session, vehicle=vehicle, for_update=True)
    pack = await require_battery_pack(session, vehicle=vehicle, for_update=True)
    if state.version != command.expected_version:
        raise MotorStateVersionConflictError(current_version=state.version)

    mode_factor = _DRIVE_MODE_FACTOR[command.drive_mode.value]
    battery_limit_kw = _battery_power_limit(pack, state.max_inverter_power_kw)
    efficiency_pct = _efficiency_pct(state, command.requested_torque_nm, command.motor_speed_rpm)
    efficiency_ratio = efficiency_pct / 100.0
    torque_limit_nm = state.max_torque_nm * mode_factor
    limiting_reason: str | None = None
    if command.motor_speed_rpm > state.max_speed_rpm:
        torque_limit_nm = 0.0
        limiting_reason = "speed_limit"
    elif battery_limit_kw == 0.0:
        torque_limit_nm = 0.0
        limiting_reason = "battery_unavailable"
    elif command.motor_speed_rpm > 0:
        angular_speed = 2.0 * pi * command.motor_speed_rpm / 60.0
        power_torque_limit = battery_limit_kw * efficiency_ratio * 1000.0 / angular_speed
        if power_torque_limit < torque_limit_nm:
            torque_limit_nm = power_torque_limit
            limiting_reason = "battery_power_limit"
    if torque_limit_nm < command.requested_torque_nm and limiting_reason is None:
        limiting_reason = "drive_mode_limit"
    delivered_torque_nm = min(command.requested_torque_nm, max(0.0, torque_limit_nm))
    angular_speed = 2.0 * pi * command.motor_speed_rpm / 60.0
    mechanical_power_kw = delivered_torque_nm * angular_speed / 1000.0
    electrical_power_kw = mechanical_power_kw / efficiency_ratio if mechanical_power_kw else 0.0
    power_loss_kw = max(0.0, electrical_power_kw - mechanical_power_kw)

    seconds = command.duration_ms / 1000.0
    motor_temperature_c = (
        state.motor_temperature_c
        + (
            power_loss_kw * 600.0
            - 45.0 * (state.motor_temperature_c - command.ambient_temperature_c)
        )
        * seconds
        / 60_000.0
    )
    inverter_temperature_c = (
        state.inverter_temperature_c
        + (
            power_loss_kw * 400.0
            - 30.0 * (state.inverter_temperature_c - command.ambient_temperature_c)
        )
        * seconds
        / 30_000.0
    )
    thermal_protection = motor_temperature_c >= 150.0 or inverter_temperature_c >= 110.0
    if thermal_protection:
        delivered_torque_nm = 0.0
        mechanical_power_kw = 0.0
        electrical_power_kw = 0.0
        power_loss_kw = 0.0
        limiting_reason = "thermal_protection"
        operating_state = PowertrainOperatingState.PROTECTION.value
    elif limiting_reason is not None:
        operating_state = PowertrainOperatingState.DERATED.value
    else:
        operating_state = PowertrainOperatingState.READY.value

    previous_version = state.version
    state.requested_torque_nm = command.requested_torque_nm
    state.delivered_torque_nm = round(delivered_torque_nm, 3)
    state.motor_speed_rpm = command.motor_speed_rpm
    state.mechanical_power_kw = round(mechanical_power_kw, 3)
    state.electrical_power_kw = round(electrical_power_kw, 3)
    state.efficiency_pct = efficiency_pct
    state.power_loss_kw = round(power_loss_kw, 3)
    state.motor_temperature_c = round(min(150.0, motor_temperature_c), 3)
    state.inverter_temperature_c = round(min(110.0, inverter_temperature_c), 3)
    state.drive_mode = command.drive_mode.value
    state.operating_state = operating_state
    state.limiting_reason = limiting_reason
    state.version += 1
    state.simulation_time_ms += command.duration_ms
    rendered = motor_inverter_response(state, vehicle, pack)
    result = rendered.model_dump(mode="json")
    step = MotorSimulationStep(
        vehicle_id=vehicle.id,
        command_id=command.command_id,
        duration_ms=command.duration_ms,
        requested_torque_nm=command.requested_torque_nm,
        motor_speed_rpm=command.motor_speed_rpm,
        drive_mode=command.drive_mode.value,
        ambient_temperature_c=command.ambient_temperature_c,
        previous_version=previous_version,
        state_version=state.version,
        result=result,
        requested_by_user_id=actor_user_id,
    )
    session.add(step)
    await session.flush()
    payload = {
        "vehicle_id": vehicle.identifier,
        "command_id": command.command_id,
        "requested_torque_nm": state.requested_torque_nm,
        "delivered_torque_nm": state.delivered_torque_nm,
        "motor_speed_rpm": state.motor_speed_rpm,
        "electrical_power_kw": state.electrical_power_kw,
        "efficiency_pct": state.efficiency_pct,
        "operating_state": state.operating_state,
        "limiting_reason": state.limiting_reason,
        "version": state.version,
        "simulation_time_ms": state.simulation_time_ms,
    }
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.motor.step.completed.v1",
        aggregate_type="motor_inverter",
        aggregate_id=state.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.motor_step_completed",
        resource_type="motor_inverter",
        resource_id=state.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return rendered, False
