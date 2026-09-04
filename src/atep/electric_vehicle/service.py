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
    BrakeBatteryVersionConflictError,
    BrakeSimulationCommandConflictError,
    BrakeStateVersionConflictError,
    ChargingBatteryVersionConflictError,
    ChargingCommandConflictError,
    ChargingStateVersionConflictError,
    ChargingSystemAlreadyExistsError,
    ChargingTransitionError,
    MotorInverterAlreadyExistsError,
    MotorSimulationCommandConflictError,
    MotorStateVersionConflictError,
    RangeBatteryVersionConflictError,
    RangeEstimationCommandConflictError,
    RangeEstimatorAlreadyExistsError,
    RangeStateVersionConflictError,
    RangeThermalVersionConflictError,
    RegenerativeBrakeAlreadyExistsError,
    ResourceNotFoundError,
    ThermalBatteryVersionConflictError,
    ThermalCommandConflictError,
    ThermalManagementAlreadyExistsError,
    ThermalMotorVersionConflictError,
    ThermalStateVersionConflictError,
)
from atep.electric_vehicle.models import (
    BatteryPackState,
    BatterySimulationStep,
    BrakeSimulationStep,
    ChargingCommandStep,
    ChargingSystemState,
    MotorInverterState,
    MotorSimulationStep,
    RangeEstimationStep,
    RangeEstimatorState,
    RegenerativeBrakeState,
    ThermalManagementState,
    ThermalManagementStep,
)
from atep.electric_vehicle.schemas import (
    BatteryContactorState,
    BatteryOperatingState,
    BatteryPackCreate,
    BatteryPackResponse,
    BatterySimulationCommand,
    BrakeOperatingState,
    BrakeSimulationCommand,
    ChargingAction,
    ChargingCommand,
    ChargingConnectorType,
    ChargingOperatingState,
    ChargingSystemCreate,
    ChargingSystemResponse,
    DriveMode,
    MotorInverterCreate,
    MotorInverterResponse,
    MotorSimulationCommand,
    PowertrainOperatingState,
    RangeEstimationCommand,
    RangeEstimatorCreate,
    RangeEstimatorResponse,
    RegenerativeBrakeCreate,
    RegenerativeBrakeResponse,
    ThermalManagementCommand,
    ThermalManagementCreate,
    ThermalManagementResponse,
    ThermalOperatingState,
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


def range_estimator_response(
    state: RangeEstimatorState,
    vehicle: Vehicle,
    pack: BatteryPackState,
    thermal: ThermalManagementState,
) -> RangeEstimatorResponse:
    nominal_energy_kwh = (
        pack.series_cell_count * pack.nominal_cell_voltage_v * pack.nominal_capacity_ah / 1000.0
    )
    available_energy_kwh = (
        nominal_energy_kwh
        * (pack.soh_pct / 100.0)
        * max(0.0, pack.soc_pct - state.reserve_soc_pct)
        / 100.0
    )
    return RangeEstimatorResponse(
        vehicle_id=vehicle.identifier,
        cycle_id=state.last_cycle_id,
        distance_km=state.distance_km,
        duration_ms=state.simulation_time_ms,
        traction_energy_kwh=state.traction_energy_kwh,
        auxiliary_energy_kwh=state.auxiliary_energy_kwh,
        recovered_energy_kwh=state.recovered_energy_kwh,
        net_energy_kwh=state.net_energy_kwh,
        consumption_kwh_per_100km=state.consumption_kwh_per_100km,
        available_energy_kwh=round(available_energy_kwh, 4),
        estimated_range_km=state.estimated_range_km,
        battery_soc_pct=pack.soc_pct,
        battery_version=pack.version,
        thermal_version=thermal.version,
        operating_state=state.operating_state,
        limiting_reason=state.limiting_reason,
        version=state.version,
    )


async def create_range_estimator(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    pack: BatteryPackState,
    thermal: ThermalManagementState,
    command: RangeEstimatorCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> RangeEstimatorState:
    existing = await session.scalar(
        select(RangeEstimatorState).where(RangeEstimatorState.vehicle_id == vehicle.id)
    )
    if existing is not None:
        raise RangeEstimatorAlreadyExistsError()
    state = RangeEstimatorState(
        vehicle_id=vehicle.id,
        **command.model_dump(),
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
    try:
        async with session.begin_nested():
            session.add(state)
            await session.flush()
    except IntegrityError as exc:
        raise RangeEstimatorAlreadyExistsError() from exc
    payload = {
        "vehicle_id": vehicle.identifier,
        "reserve_soc_pct": state.reserve_soc_pct,
        "version": 1,
    }
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.range_estimator.created.v1",
        aggregate_type="range_estimator",
        aggregate_id=state.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.range_estimator_created",
        resource_type="range_estimator",
        resource_id=state.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return state


async def require_range_estimator(
    session: AsyncSession, *, vehicle: Vehicle, for_update: bool = False
) -> RangeEstimatorState:
    query = select(RangeEstimatorState).where(RangeEstimatorState.vehicle_id == vehicle.id)
    if for_update:
        query = query.with_for_update()
    state = await session.scalar(query)
    if state is None:
        raise ResourceNotFoundError("range_estimator")
    return state


def _same_range_command(step: RangeEstimationStep, command: RangeEstimationCommand) -> bool:
    return (
        step.cycle_id == command.cycle_id
        and step.segments == [item.model_dump(mode="json") for item in command.segments]
        and step.previous_version == command.expected_version
        and step.previous_battery_version == command.expected_battery_version
        and step.previous_thermal_version == command.expected_thermal_version
    )


async def simulate_range_cycle(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: RangeEstimationCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[RangeEstimatorResponse, bool]:
    existing = await session.scalar(
        select(RangeEstimationStep).where(
            RangeEstimationStep.vehicle_id == vehicle.id,
            RangeEstimationStep.command_id == command.command_id,
        )
    )
    if existing is not None:
        if not _same_range_command(existing, command):
            raise RangeEstimationCommandConflictError()
        return RangeEstimatorResponse.model_validate({**existing.result, "duplicate": True}), True

    pack = await require_battery_pack(session, vehicle=vehicle, for_update=True)
    thermal = await require_thermal_management(session, vehicle=vehicle, for_update=True)
    state = await require_range_estimator(session, vehicle=vehicle, for_update=True)
    if state.version != command.expected_version:
        raise RangeStateVersionConflictError(current_version=state.version)
    if pack.version != command.expected_battery_version:
        raise RangeBatteryVersionConflictError(current_version=pack.version)
    if thermal.version != command.expected_thermal_version:
        raise RangeThermalVersionConflictError(current_version=thermal.version)

    previous_version = state.version
    distance_km = traction = recovered = auxiliary = 0.0
    duration_ms = sum(segment.duration_ms for segment in command.segments)
    air_density = 1.225
    gravity = 9.80665
    for segment in command.segments:
        duration_h = segment.duration_ms / 3_600_000.0
        speed_mps = segment.speed_kph / 3.6
        distance_km += segment.speed_kph * duration_h
        force_n = (
            state.vehicle_mass_kg * gravity * state.rolling_resistance_coefficient
            + 0.5 * air_density * state.drag_coefficient * state.frontal_area_m2 * speed_mps**2
            + state.vehicle_mass_kg * gravity * segment.road_grade_pct / 100.0
            + state.vehicle_mass_kg * segment.acceleration_mps2
        )
        mechanical_kwh = force_n * speed_mps * (segment.duration_ms / 1000.0) / 3_600_000.0
        if mechanical_kwh >= 0.0:
            traction += mechanical_kwh / (state.drivetrain_efficiency_pct / 100.0)
        else:
            recovered += -mechanical_kwh * (state.regenerative_efficiency_pct / 100.0)
        auxiliary += (state.base_auxiliary_power_kw + thermal.auxiliary_power_kw) * duration_h

    net = max(0.0, traction + auxiliary - recovered)
    consumption = net / distance_km * 100.0 if distance_km >= 0.01 else 0.0
    nominal = (
        pack.series_cell_count * pack.nominal_cell_voltage_v * pack.nominal_capacity_ah / 1000.0
    )
    available = (
        nominal * pack.soh_pct / 100.0 * max(0.0, pack.soc_pct - state.reserve_soc_pct) / 100.0
    )
    state.last_cycle_id = command.cycle_id
    state.distance_km = round(distance_km, 4)
    state.traction_energy_kwh = round(traction, 4)
    state.auxiliary_energy_kwh = round(auxiliary, 4)
    state.recovered_energy_kwh = round(recovered, 4)
    state.net_energy_kwh = round(net, 4)
    state.consumption_kwh_per_100km = round(consumption, 4)
    state.estimated_range_km = round(available / consumption * 100.0, 2) if consumption > 0 else 0.0
    state.operating_state = "completed" if consumption > 0 and available > 0 else "limited"
    state.limiting_reason = (
        None
        if state.operating_state == "completed"
        else ("reserve_reached" if available <= 0 else "insufficient_distance")
    )
    state.version += 1
    state.simulation_time_ms = duration_ms
    rendered = range_estimator_response(state, vehicle, pack, thermal)
    result = rendered.model_dump(mode="json")
    session.add(
        RangeEstimationStep(
            vehicle_id=vehicle.id,
            command_id=command.command_id,
            cycle_id=command.cycle_id,
            segments=[item.model_dump(mode="json") for item in command.segments],
            duration_ms=duration_ms,
            previous_version=previous_version,
            state_version=state.version,
            previous_battery_version=pack.version,
            previous_thermal_version=thermal.version,
            result=result,
            requested_by_user_id=actor_user_id,
        )
    )
    await session.flush()
    payload = {
        "vehicle_id": vehicle.identifier,
        "command_id": command.command_id,
        "cycle_id": command.cycle_id,
        "consumption_kwh_per_100km": state.consumption_kwh_per_100km,
        "estimated_range_km": state.estimated_range_km,
        "version": state.version,
    }
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.range.cycle.completed.v1",
        aggregate_type="range_estimator",
        aggregate_id=state.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.range_cycle_completed",
        resource_type="range_estimator",
        resource_id=state.id,
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


def _battery_charge_acceptance_kw(pack: BatteryPackState, maximum_regen_power_kw: float) -> float:
    if pack.contactor_state != BatteryContactorState.CLOSED.value:
        return 0.0
    if pack.operating_state == BatteryOperatingState.PROTECTION.value:
        return 0.0
    if pack.soc_pct >= 95.0 or not 0.0 <= pack.pack_temperature_c <= 50.0:
        return 0.0
    current_limit_a = (
        150.0 if pack.operating_state == BatteryOperatingState.WARNING.value else 300.0
    )
    soc_factor = 1.0 if pack.soc_pct <= 80.0 else (95.0 - pack.soc_pct) / 15.0
    temperature_factor = 0.5 if pack.pack_temperature_c < 10.0 else 1.0
    if pack.pack_temperature_c > 45.0:
        temperature_factor = 0.5
    electrical_limit_kw = pack.pack_voltage_v * current_limit_a / 1000.0
    tapered_limit_kw = electrical_limit_kw * soc_factor * temperature_factor
    return round(
        max(0.0, min(maximum_regen_power_kw, tapered_limit_kw)),
        3,
    )


def regenerative_brake_response(
    state: RegenerativeBrakeState,
    vehicle: Vehicle,
    pack: BatteryPackState,
    *,
    duplicate: bool = False,
) -> RegenerativeBrakeResponse:
    return RegenerativeBrakeResponse(
        vehicle_id=vehicle.identifier,
        vehicle_mass_kg=state.vehicle_mass_kg,
        wheel_radius_m=state.wheel_radius_m,
        final_drive_ratio=state.final_drive_ratio,
        drivetrain_efficiency_pct=state.drivetrain_efficiency_pct,
        max_regen_torque_nm=state.max_regen_torque_nm,
        max_regen_power_kw=state.max_regen_power_kw,
        regen_efficiency_pct=state.regen_efficiency_pct,
        max_friction_deceleration_mps2=state.max_friction_deceleration_mps2,
        requested_deceleration_mps2=state.requested_deceleration_mps2,
        delivered_deceleration_mps2=state.delivered_deceleration_mps2,
        vehicle_speed_mps=state.vehicle_speed_mps,
        regenerative_deceleration_mps2=state.regenerative_deceleration_mps2,
        friction_deceleration_mps2=state.friction_deceleration_mps2,
        regenerative_motor_torque_nm=state.regenerative_motor_torque_nm,
        recovered_power_kw=state.recovered_power_kw,
        recovered_energy_kwh=state.recovered_energy_kwh,
        cumulative_recovered_energy_kwh=state.cumulative_recovered_energy_kwh,
        battery_charge_acceptance_kw=state.battery_charge_acceptance_kw,
        battery_soc_pct=pack.soc_pct,
        battery_version=pack.version,
        operating_state=state.operating_state,
        limiting_reason=state.limiting_reason,
        version=state.version,
        simulation_time_ms=state.simulation_time_ms,
        duplicate=duplicate,
    )


async def create_regenerative_brake(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    pack: BatteryPackState,
    motor: MotorInverterState,
    command: RegenerativeBrakeCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> RegenerativeBrakeState:
    existing = await session.scalar(
        select(RegenerativeBrakeState).where(RegenerativeBrakeState.vehicle_id == vehicle.id)
    )
    if existing is not None:
        raise RegenerativeBrakeAlreadyExistsError()
    state = RegenerativeBrakeState(
        vehicle_id=vehicle.id,
        vehicle_mass_kg=command.vehicle_mass_kg,
        wheel_radius_m=command.wheel_radius_m,
        final_drive_ratio=command.final_drive_ratio,
        drivetrain_efficiency_pct=command.drivetrain_efficiency_pct,
        max_regen_torque_nm=min(command.max_regen_torque_nm, motor.max_torque_nm),
        max_regen_power_kw=min(command.max_regen_power_kw, motor.max_inverter_power_kw),
        regen_efficiency_pct=command.regen_efficiency_pct,
        max_friction_deceleration_mps2=command.max_friction_deceleration_mps2,
        requested_deceleration_mps2=0.0,
        delivered_deceleration_mps2=0.0,
        vehicle_speed_mps=0.0,
        regenerative_deceleration_mps2=0.0,
        friction_deceleration_mps2=0.0,
        regenerative_motor_torque_nm=0.0,
        recovered_power_kw=0.0,
        recovered_energy_kwh=0.0,
        cumulative_recovered_energy_kwh=0.0,
        battery_charge_acceptance_kw=_battery_charge_acceptance_kw(
            pack, min(command.max_regen_power_kw, motor.max_inverter_power_kw)
        ),
        operating_state=BrakeOperatingState.STANDBY.value,
        limiting_reason=None,
        version=1,
        simulation_time_ms=0,
    )
    try:
        async with session.begin_nested():
            session.add(state)
            await session.flush()
    except IntegrityError as exc:
        raise RegenerativeBrakeAlreadyExistsError() from exc
    payload = {
        "vehicle_id": vehicle.identifier,
        "max_regen_torque_nm": state.max_regen_torque_nm,
        "max_regen_power_kw": state.max_regen_power_kw,
        "version": state.version,
    }
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.regenerative_brake.created.v1",
        aggregate_type="regenerative_brake",
        aggregate_id=state.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.regenerative_brake_created",
        resource_type="regenerative_brake",
        resource_id=state.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return state


async def require_regenerative_brake(
    session: AsyncSession, *, vehicle: Vehicle, for_update: bool = False
) -> RegenerativeBrakeState:
    query = select(RegenerativeBrakeState).where(RegenerativeBrakeState.vehicle_id == vehicle.id)
    if for_update:
        query = query.with_for_update()
    state = await session.scalar(query)
    if state is None:
        raise ResourceNotFoundError("regenerative_brake")
    return state


def _same_brake_step(step: BrakeSimulationStep, command: BrakeSimulationCommand) -> bool:
    return (
        step.duration_ms == command.duration_ms
        and isclose(step.requested_deceleration_mps2, command.requested_deceleration_mps2)
        and isclose(step.vehicle_speed_mps, command.vehicle_speed_mps)
        and step.previous_version == command.expected_version
        and step.previous_battery_version == command.expected_battery_version
    )


async def simulate_brake_step(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: BrakeSimulationCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[RegenerativeBrakeResponse, bool]:
    existing = await session.scalar(
        select(BrakeSimulationStep).where(
            BrakeSimulationStep.vehicle_id == vehicle.id,
            BrakeSimulationStep.command_id == command.command_id,
        )
    )
    if existing is not None:
        if not _same_brake_step(existing, command):
            raise BrakeSimulationCommandConflictError()
        return RegenerativeBrakeResponse.model_validate(
            {**existing.result, "duplicate": True}
        ), True

    motor = await require_motor_inverter(session, vehicle=vehicle, for_update=True)
    pack = await require_battery_pack(session, vehicle=vehicle, for_update=True)
    state = await require_regenerative_brake(session, vehicle=vehicle, for_update=True)
    if state.version != command.expected_version:
        raise BrakeStateVersionConflictError(current_version=state.version)
    if pack.version != command.expected_battery_version:
        raise BrakeBatteryVersionConflictError(current_version=pack.version)

    requested_force_n = state.vehicle_mass_kg * command.requested_deceleration_mps2
    drivetrain_efficiency = state.drivetrain_efficiency_pct / 100.0
    regen_efficiency = state.regen_efficiency_pct / 100.0
    charge_acceptance_kw = _battery_charge_acceptance_kw(pack, state.max_regen_power_kw)
    nominal_energy_kwh = (
        pack.series_cell_count * pack.nominal_cell_voltage_v * pack.nominal_capacity_ah / 1000.0
    )
    usable_energy_kwh = nominal_energy_kwh * pack.soh_pct / 100.0
    duration_hours = command.duration_ms / 3_600_000.0
    energy_room_kwh = max(0.0, (95.0 - pack.soc_pct) / 100.0 * usable_energy_kwh)
    charge_acceptance_kw = min(charge_acceptance_kw, energy_room_kwh / duration_hours)
    torque_cap_nm = min(state.max_regen_torque_nm, motor.max_torque_nm)
    torque_force_cap_n = (
        torque_cap_nm * state.final_drive_ratio * drivetrain_efficiency / state.wheel_radius_m
    )
    limiting_reason: str | None = None
    if command.vehicle_speed_mps < 0.5:
        regen_force_n = 0.0
        limiting_reason = "vehicle_speed_too_low"
    elif charge_acceptance_kw == 0.0:
        regen_force_n = 0.0
        limiting_reason = "battery_charge_unavailable"
    else:
        power_force_cap_n = (
            charge_acceptance_kw * 1000.0 / (command.vehicle_speed_mps * regen_efficiency)
        )
        regen_force_n = min(requested_force_n, torque_force_cap_n, power_force_cap_n)
        if regen_force_n < requested_force_n:
            limiting_reason = (
                "battery_charge_limit"
                if power_force_cap_n <= torque_force_cap_n
                else "regenerative_torque_limit"
            )

    friction_request_n = max(0.0, requested_force_n - regen_force_n)
    friction_force_cap_n = state.vehicle_mass_kg * state.max_friction_deceleration_mps2
    friction_force_n = min(friction_request_n, friction_force_cap_n)
    delivered_force_n = regen_force_n + friction_force_n
    if delivered_force_n + 1e-6 < requested_force_n:
        limiting_reason = "brake_capacity_limit"

    regenerative_deceleration = regen_force_n / state.vehicle_mass_kg
    friction_deceleration = friction_force_n / state.vehicle_mass_kg
    delivered_deceleration = delivered_force_n / state.vehicle_mass_kg
    regenerative_motor_torque = (
        regen_force_n * state.wheel_radius_m / (state.final_drive_ratio * drivetrain_efficiency)
    )
    recovered_power_kw = regen_force_n * command.vehicle_speed_mps * regen_efficiency / 1000.0
    recovered_energy_kwh = recovered_power_kw * command.duration_ms / 3_600_000.0

    previous_battery_version = pack.version
    if recovered_energy_kwh > 0.0:
        pack.soc_pct = round(
            min(95.0, pack.soc_pct + recovered_energy_kwh / usable_energy_kwh * 100.0), 4
        )
        cells = _cells(
            count=pack.series_cell_count,
            soc_pct=pack.soc_pct,
            temperature_c=pack.pack_temperature_c,
            nominal_voltage=pack.nominal_cell_voltage_v,
        )
        pack.cells = cells
        pack.pack_voltage_v = round(sum(float(cell["voltage_v"]) for cell in cells), 3)
        pack.pack_current_a = round(-recovered_power_kw * 1000.0 / pack.pack_voltage_v, 3)
        pack.version += 1
        pack.simulation_time_ms += command.duration_ms

    if command.requested_deceleration_mps2 == 0.0:
        operating_state = BrakeOperatingState.STANDBY.value
        limiting_reason = None
    elif delivered_deceleration + 1e-6 < command.requested_deceleration_mps2:
        operating_state = BrakeOperatingState.LIMITED.value
    elif regenerative_deceleration > 0.0 and friction_deceleration > 0.0:
        operating_state = BrakeOperatingState.BLENDED.value
    elif regenerative_deceleration > 0.0:
        operating_state = BrakeOperatingState.REGENERATIVE.value
    else:
        operating_state = BrakeOperatingState.FRICTION.value

    previous_version = state.version
    state.requested_deceleration_mps2 = command.requested_deceleration_mps2
    state.delivered_deceleration_mps2 = round(delivered_deceleration, 4)
    state.vehicle_speed_mps = command.vehicle_speed_mps
    state.regenerative_deceleration_mps2 = round(regenerative_deceleration, 4)
    state.friction_deceleration_mps2 = round(friction_deceleration, 4)
    state.regenerative_motor_torque_nm = round(regenerative_motor_torque, 3)
    state.recovered_power_kw = round(recovered_power_kw, 3)
    state.recovered_energy_kwh = round(recovered_energy_kwh, 6)
    state.cumulative_recovered_energy_kwh = round(
        state.cumulative_recovered_energy_kwh + recovered_energy_kwh, 6
    )
    state.battery_charge_acceptance_kw = charge_acceptance_kw
    state.operating_state = operating_state
    state.limiting_reason = limiting_reason
    state.version += 1
    state.simulation_time_ms += command.duration_ms
    rendered = regenerative_brake_response(state, vehicle, pack)
    result = rendered.model_dump(mode="json")
    step = BrakeSimulationStep(
        vehicle_id=vehicle.id,
        command_id=command.command_id,
        duration_ms=command.duration_ms,
        requested_deceleration_mps2=command.requested_deceleration_mps2,
        vehicle_speed_mps=command.vehicle_speed_mps,
        previous_version=previous_version,
        state_version=state.version,
        previous_battery_version=previous_battery_version,
        battery_state_version=pack.version,
        result=result,
        requested_by_user_id=actor_user_id,
    )
    session.add(step)
    await session.flush()
    payload = {
        "vehicle_id": vehicle.identifier,
        "command_id": command.command_id,
        "requested_deceleration_mps2": state.requested_deceleration_mps2,
        "delivered_deceleration_mps2": state.delivered_deceleration_mps2,
        "regenerative_deceleration_mps2": state.regenerative_deceleration_mps2,
        "friction_deceleration_mps2": state.friction_deceleration_mps2,
        "recovered_energy_kwh": state.recovered_energy_kwh,
        "battery_soc_pct": pack.soc_pct,
        "battery_version": pack.version,
        "operating_state": state.operating_state,
        "limiting_reason": state.limiting_reason,
        "version": state.version,
        "simulation_time_ms": state.simulation_time_ms,
    }
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.brake.step.completed.v1",
        aggregate_type="regenerative_brake",
        aggregate_id=state.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.brake_step_completed",
        resource_type="regenerative_brake",
        resource_id=state.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return rendered, False


def charging_system_response(
    state: ChargingSystemState,
    vehicle: Vehicle,
    pack: BatteryPackState,
    *,
    duplicate: bool = False,
) -> ChargingSystemResponse:
    return ChargingSystemResponse(
        vehicle_id=vehicle.identifier,
        max_ac_power_kw=state.max_ac_power_kw,
        max_dc_power_kw=state.max_dc_power_kw,
        charging_efficiency_pct=state.charging_efficiency_pct,
        session_id=state.session_id,
        connector_type=state.connector_type,
        target_soc_pct=state.target_soc_pct,
        requested_power_kw=state.requested_power_kw,
        delivered_power_kw=state.delivered_power_kw,
        charged_energy_kwh=state.charged_energy_kwh,
        session_energy_kwh=state.session_energy_kwh,
        battery_charge_acceptance_kw=state.battery_charge_acceptance_kw,
        battery_soc_pct=pack.soc_pct,
        battery_version=pack.version,
        operating_state=state.operating_state,
        limiting_reason=state.limiting_reason,
        fault_code=state.fault_code,
        version=state.version,
        simulation_time_ms=state.simulation_time_ms,
        duplicate=duplicate,
    )


async def create_charging_system(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    pack: BatteryPackState,
    command: ChargingSystemCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> ChargingSystemState:
    existing = await session.scalar(
        select(ChargingSystemState).where(ChargingSystemState.vehicle_id == vehicle.id)
    )
    if existing is not None:
        raise ChargingSystemAlreadyExistsError()
    state = ChargingSystemState(
        vehicle_id=vehicle.id,
        max_ac_power_kw=command.max_ac_power_kw,
        max_dc_power_kw=command.max_dc_power_kw,
        charging_efficiency_pct=command.charging_efficiency_pct,
        session_id=None,
        connector_type=None,
        target_soc_pct=80.0,
        requested_power_kw=0.0,
        delivered_power_kw=0.0,
        charged_energy_kwh=0.0,
        session_energy_kwh=0.0,
        battery_charge_acceptance_kw=0.0,
        operating_state=ChargingOperatingState.IDLE.value,
        limiting_reason=None,
        fault_code=None,
        version=1,
        simulation_time_ms=0,
    )
    try:
        async with session.begin_nested():
            session.add(state)
            await session.flush()
    except IntegrityError as exc:
        raise ChargingSystemAlreadyExistsError() from exc
    payload = {
        "vehicle_id": vehicle.identifier,
        "max_ac_power_kw": state.max_ac_power_kw,
        "max_dc_power_kw": state.max_dc_power_kw,
        "version": state.version,
    }
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.charging_system.created.v1",
        aggregate_type="charging_system",
        aggregate_id=state.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.charging_system_created",
        resource_type="charging_system",
        resource_id=state.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return state


async def require_charging_system(
    session: AsyncSession, *, vehicle: Vehicle, for_update: bool = False
) -> ChargingSystemState:
    query = select(ChargingSystemState).where(ChargingSystemState.vehicle_id == vehicle.id)
    if for_update:
        query = query.with_for_update()
    state = await session.scalar(query)
    if state is None:
        raise ResourceNotFoundError("charging_system")
    return state


def _charging_acceptance_kw(
    pack: BatteryPackState,
    state: ChargingSystemState,
    connector_type: str,
) -> float:
    if pack.contactor_state != BatteryContactorState.CLOSED.value:
        return 0.0
    if pack.operating_state == BatteryOperatingState.PROTECTION.value:
        return 0.0
    if pack.soc_pct >= state.target_soc_pct or not 0.0 <= pack.pack_temperature_c <= 50.0:
        return 0.0
    connector_limit = (
        state.max_ac_power_kw
        if connector_type == ChargingConnectorType.AC_TYPE_2.value
        else state.max_dc_power_kw
    )
    current_limit_a = (
        150.0 if pack.operating_state == BatteryOperatingState.WARNING.value else 300.0
    )
    electrical_limit_kw = pack.pack_voltage_v * current_limit_a / 1000.0
    if pack.soc_pct <= 80.0 or state.target_soc_pct <= 80.0:
        soc_factor = 1.0
    else:
        soc_factor = max(0.0, (state.target_soc_pct - pack.soc_pct) / (state.target_soc_pct - 80.0))
    temperature_factor = 0.5 if pack.pack_temperature_c < 10.0 else 1.0
    if pack.pack_temperature_c > 45.0:
        temperature_factor = 0.5
    return round(
        max(0.0, min(connector_limit, electrical_limit_kw * soc_factor * temperature_factor)), 3
    )


def _same_charging_command(step: ChargingCommandStep, command: ChargingCommand) -> bool:
    return (
        step.action == command.action.value
        and step.session_id == command.session_id
        and step.connector_type
        == (command.connector_type.value if command.connector_type else None)
        and step.duration_ms == command.duration_ms
        and isclose(step.requested_power_kw, command.requested_power_kw)
        and step.target_soc_pct == command.target_soc_pct
        and step.fault_code == command.fault_code
        and step.previous_version == command.expected_version
        and step.previous_battery_version == command.expected_battery_version
    )


def _validate_charging_transition(state: ChargingSystemState, command: ChargingCommand) -> None:
    allowed = {
        ChargingAction.START: {
            ChargingOperatingState.IDLE.value,
            ChargingOperatingState.COMPLETED.value,
        },
        ChargingAction.CHARGE: {ChargingOperatingState.CHARGING.value},
        ChargingAction.PAUSE: {ChargingOperatingState.CHARGING.value},
        ChargingAction.RESUME: {ChargingOperatingState.PAUSED.value},
        ChargingAction.STOP: {
            ChargingOperatingState.CHARGING.value,
            ChargingOperatingState.PAUSED.value,
        },
        ChargingAction.INJECT_FAULT: {
            ChargingOperatingState.CHARGING.value,
            ChargingOperatingState.PAUSED.value,
        },
        ChargingAction.CLEAR_FAULT: {ChargingOperatingState.FAULTED.value},
    }
    if state.operating_state not in allowed[command.action]:
        raise ChargingTransitionError(
            current_state=state.operating_state, action=command.action.value
        )


async def execute_charging_command(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: ChargingCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[ChargingSystemResponse, bool]:
    existing = await session.scalar(
        select(ChargingCommandStep).where(
            ChargingCommandStep.vehicle_id == vehicle.id,
            ChargingCommandStep.command_id == command.command_id,
        )
    )
    if existing is not None:
        if not _same_charging_command(existing, command):
            raise ChargingCommandConflictError()
        return ChargingSystemResponse.model_validate({**existing.result, "duplicate": True}), True

    pack = await require_battery_pack(session, vehicle=vehicle, for_update=True)
    state = await require_charging_system(session, vehicle=vehicle, for_update=True)
    if state.version != command.expected_version:
        raise ChargingStateVersionConflictError(current_version=state.version)
    if pack.version != command.expected_battery_version:
        raise ChargingBatteryVersionConflictError(current_version=pack.version)
    _validate_charging_transition(state, command)

    previous_version = state.version
    previous_battery_version = pack.version
    pack_changed = False
    charged_energy_kwh = 0.0
    limiting_reason: str | None = None

    if command.action == ChargingAction.START:
        assert command.target_soc_pct is not None
        state.session_id = command.session_id
        state.connector_type = command.connector_type.value if command.connector_type else None
        state.target_soc_pct = float(command.target_soc_pct)
        state.requested_power_kw = command.requested_power_kw
        state.delivered_power_kw = 0.0
        state.charged_energy_kwh = 0.0
        state.session_energy_kwh = 0.0
        state.fault_code = None
        state.operating_state = ChargingOperatingState.CHARGING.value
        if pack.contactor_state != BatteryContactorState.CLOSED.value:
            pack.contactor_state = BatteryContactorState.CLOSED.value
            pack_changed = True
    elif command.action == ChargingAction.CHARGE:
        connector = state.connector_type or ChargingConnectorType.AC_TYPE_2.value
        acceptance_kw = _charging_acceptance_kw(pack, state, connector)
        requested_power_kw = command.requested_power_kw or state.requested_power_kw
        if requested_power_kw == 0.0:
            requested_power_kw = (
                state.max_ac_power_kw
                if connector == ChargingConnectorType.AC_TYPE_2.value
                else state.max_dc_power_kw
            )
        state.requested_power_kw = requested_power_kw
        duration_hours = command.duration_ms / 3_600_000.0
        nominal_energy_kwh = (
            pack.series_cell_count * pack.nominal_cell_voltage_v * pack.nominal_capacity_ah / 1000.0
        )
        usable_energy_kwh = nominal_energy_kwh * pack.soh_pct / 100.0
        energy_room_kwh = max(
            0.0, (state.target_soc_pct - pack.soc_pct) / 100.0 * usable_energy_kwh
        )
        efficiency = state.charging_efficiency_pct / 100.0
        battery_power_kw = min(
            requested_power_kw * efficiency,
            acceptance_kw,
            energy_room_kwh / duration_hours,
        )
        state.delivered_power_kw = (
            round(battery_power_kw / efficiency, 3) if battery_power_kw else 0.0
        )
        charged_energy_kwh = battery_power_kw * duration_hours
        if pack.pack_temperature_c < 0.0 or pack.pack_temperature_c > 50.0:
            limiting_reason = "battery_temperature_limit"
        elif pack.operating_state == BatteryOperatingState.PROTECTION.value:
            limiting_reason = "battery_protection"
        elif pack.soc_pct >= state.target_soc_pct:
            limiting_reason = "target_soc_reached"
        elif state.delivered_power_kw + 1e-6 < requested_power_kw:
            limiting_reason = "charge_power_limited"
        if charged_energy_kwh > 0.0:
            pack.soc_pct = round(
                min(
                    state.target_soc_pct,
                    pack.soc_pct + charged_energy_kwh / usable_energy_kwh * 100.0,
                ),
                4,
            )
            pack.cells = _cells(
                count=pack.series_cell_count,
                soc_pct=pack.soc_pct,
                temperature_c=pack.pack_temperature_c,
                nominal_voltage=pack.nominal_cell_voltage_v,
            )
            pack.pack_voltage_v = round(sum(float(cell["voltage_v"]) for cell in pack.cells), 3)
            pack.pack_current_a = round(-battery_power_kw * 1000.0 / pack.pack_voltage_v, 3)
        else:
            pack.pack_current_a = 0.0
        pack.simulation_time_ms += command.duration_ms
        pack_changed = True
        state.charged_energy_kwh = round(charged_energy_kwh, 6)
        state.session_energy_kwh = round(state.session_energy_kwh + charged_energy_kwh, 6)
        state.simulation_time_ms += command.duration_ms
        if pack.soc_pct >= state.target_soc_pct:
            state.operating_state = ChargingOperatingState.COMPLETED.value
            limiting_reason = "target_soc_reached"
            pack.contactor_state = BatteryContactorState.OPEN.value
    elif command.action == ChargingAction.PAUSE:
        state.operating_state = ChargingOperatingState.PAUSED.value
        state.delivered_power_kw = 0.0
        pack.pack_current_a = 0.0
        pack.contactor_state = BatteryContactorState.OPEN.value
        pack_changed = True
    elif command.action == ChargingAction.RESUME:
        state.operating_state = ChargingOperatingState.CHARGING.value
        state.delivered_power_kw = 0.0
        pack.contactor_state = BatteryContactorState.CLOSED.value
        pack_changed = True
    elif command.action == ChargingAction.STOP:
        state.operating_state = ChargingOperatingState.COMPLETED.value
        state.delivered_power_kw = 0.0
        pack.pack_current_a = 0.0
        pack.contactor_state = BatteryContactorState.OPEN.value
        pack_changed = True
    elif command.action == ChargingAction.INJECT_FAULT:
        state.operating_state = ChargingOperatingState.FAULTED.value
        state.fault_code = command.fault_code
        state.delivered_power_kw = 0.0
        pack.pack_current_a = 0.0
        pack.contactor_state = BatteryContactorState.OPEN.value
        pack_changed = True
    else:
        state.operating_state = ChargingOperatingState.IDLE.value
        state.fault_code = None
        state.delivered_power_kw = 0.0

    state.battery_charge_acceptance_kw = (
        _charging_acceptance_kw(pack, state, state.connector_type)
        if state.connector_type is not None
        and state.operating_state == ChargingOperatingState.CHARGING.value
        else 0.0
    )
    if command.action == ChargingAction.CHARGE:
        state.limiting_reason = limiting_reason
    elif command.action != ChargingAction.CLEAR_FAULT:
        state.limiting_reason = None
    if pack_changed:
        pack.version += 1
    state.version += 1

    rendered = charging_system_response(state, vehicle, pack)
    result = rendered.model_dump(mode="json")
    step = ChargingCommandStep(
        vehicle_id=vehicle.id,
        command_id=command.command_id,
        action=command.action.value,
        session_id=command.session_id,
        connector_type=command.connector_type.value if command.connector_type else None,
        duration_ms=command.duration_ms,
        requested_power_kw=command.requested_power_kw,
        target_soc_pct=command.target_soc_pct,
        fault_code=command.fault_code,
        previous_version=previous_version,
        state_version=state.version,
        previous_battery_version=previous_battery_version,
        battery_state_version=pack.version,
        result=result,
        requested_by_user_id=actor_user_id,
    )
    session.add(step)
    await session.flush()
    payload = {
        "vehicle_id": vehicle.identifier,
        "command_id": command.command_id,
        "action": command.action.value,
        "session_id": state.session_id,
        "connector_type": state.connector_type,
        "charged_energy_kwh": state.charged_energy_kwh,
        "session_energy_kwh": state.session_energy_kwh,
        "battery_soc_pct": pack.soc_pct,
        "battery_version": pack.version,
        "operating_state": state.operating_state,
        "limiting_reason": state.limiting_reason,
        "fault_code": state.fault_code,
        "version": state.version,
        "simulation_time_ms": state.simulation_time_ms,
    }
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.charging.command.completed.v1",
        aggregate_type="charging_system",
        aggregate_id=state.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.charging_command_completed",
        resource_type="charging_system",
        resource_id=state.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return rendered, False


def thermal_management_response(
    state: ThermalManagementState,
    vehicle: Vehicle,
    pack: BatteryPackState,
    motor: MotorInverterState,
) -> ThermalManagementResponse:
    return ThermalManagementResponse(
        vehicle_id=vehicle.identifier,
        battery_target_temperature_c=state.battery_target_temperature_c,
        motor_target_temperature_c=state.motor_target_temperature_c,
        inverter_target_temperature_c=state.inverter_target_temperature_c,
        cabin_target_temperature_c=state.cabin_target_temperature_c,
        battery_temperature_c=pack.pack_temperature_c,
        motor_temperature_c=motor.motor_temperature_c,
        inverter_temperature_c=motor.inverter_temperature_c,
        cabin_temperature_c=state.cabin_temperature_c,
        battery_thermal_power_kw=state.battery_thermal_power_kw,
        motor_thermal_power_kw=state.motor_thermal_power_kw,
        inverter_thermal_power_kw=state.inverter_thermal_power_kw,
        cabin_thermal_power_kw=state.cabin_thermal_power_kw,
        auxiliary_power_kw=state.auxiliary_power_kw,
        battery_version=pack.version,
        motor_version=motor.version,
        operating_state=state.operating_state,
        limiting_reason=state.limiting_reason,
        fault_code=state.fault_code,
        version=state.version,
        simulation_time_ms=state.simulation_time_ms,
    )


async def create_thermal_management(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    pack: BatteryPackState,
    motor: MotorInverterState,
    command: ThermalManagementCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> ThermalManagementState:
    existing = await session.scalar(
        select(ThermalManagementState).where(ThermalManagementState.vehicle_id == vehicle.id)
    )
    if existing is not None:
        raise ThermalManagementAlreadyExistsError()
    state = ThermalManagementState(
        vehicle_id=vehicle.id,
        max_battery_thermal_power_kw=command.max_battery_thermal_power_kw,
        max_powertrain_thermal_power_kw=command.max_powertrain_thermal_power_kw,
        max_cabin_thermal_power_kw=command.max_cabin_thermal_power_kw,
        battery_target_temperature_c=command.battery_target_temperature_c,
        motor_target_temperature_c=command.motor_target_temperature_c,
        inverter_target_temperature_c=command.inverter_target_temperature_c,
        cabin_target_temperature_c=command.cabin_target_temperature_c,
        cabin_temperature_c=command.initial_cabin_temperature_c,
        battery_thermal_power_kw=0.0,
        motor_thermal_power_kw=0.0,
        inverter_thermal_power_kw=0.0,
        cabin_thermal_power_kw=0.0,
        auxiliary_power_kw=0.0,
        operating_state=ThermalOperatingState.STANDBY.value,
        limiting_reason=None,
        fault_code=None,
        version=1,
        simulation_time_ms=0,
    )
    try:
        async with session.begin_nested():
            session.add(state)
            await session.flush()
    except IntegrityError as exc:
        raise ThermalManagementAlreadyExistsError() from exc
    payload = {
        "vehicle_id": vehicle.identifier,
        "battery_target_temperature_c": state.battery_target_temperature_c,
        "cabin_target_temperature_c": state.cabin_target_temperature_c,
        "version": state.version,
    }
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.thermal_management.created.v1",
        aggregate_type="thermal_management",
        aggregate_id=state.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.thermal_management_created",
        resource_type="thermal_management",
        resource_id=state.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return state


async def require_thermal_management(
    session: AsyncSession, *, vehicle: Vehicle, for_update: bool = False
) -> ThermalManagementState:
    query = select(ThermalManagementState).where(ThermalManagementState.vehicle_id == vehicle.id)
    if for_update:
        query = query.with_for_update()
    state = await session.scalar(query)
    if state is None:
        raise ResourceNotFoundError("thermal_management")
    return state


def _same_thermal_command(step: ThermalManagementStep, command: ThermalManagementCommand) -> bool:
    return (
        step.duration_ms == command.duration_ms
        and isclose(step.ambient_temperature_c, command.ambient_temperature_c)
        and isclose(step.cabin_heat_load_kw, command.cabin_heat_load_kw)
        and step.enabled == command.enabled
        and step.fault_code == command.fault_code
        and step.previous_version == command.expected_version
        and step.previous_battery_version == command.expected_battery_version
        and step.previous_motor_version == command.expected_motor_version
    )


def _thermal_power(target_c: float, actual_c: float, maximum_kw: float) -> float:
    return max(-maximum_kw, min(maximum_kw, (target_c - actual_c) * 0.5))


async def simulate_thermal_step(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: ThermalManagementCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[ThermalManagementResponse, bool]:
    existing = await session.scalar(
        select(ThermalManagementStep).where(
            ThermalManagementStep.vehicle_id == vehicle.id,
            ThermalManagementStep.command_id == command.command_id,
        )
    )
    if existing is not None:
        if not _same_thermal_command(existing, command):
            raise ThermalCommandConflictError()
        return ThermalManagementResponse.model_validate(
            {**existing.result, "duplicate": True}
        ), True

    pack = await require_battery_pack(session, vehicle=vehicle, for_update=True)
    motor = await require_motor_inverter(session, vehicle=vehicle, for_update=True)
    state = await require_thermal_management(session, vehicle=vehicle, for_update=True)
    if state.version != command.expected_version:
        raise ThermalStateVersionConflictError(current_version=state.version)
    if pack.version != command.expected_battery_version:
        raise ThermalBatteryVersionConflictError(current_version=pack.version)
    if motor.version != command.expected_motor_version:
        raise ThermalMotorVersionConflictError(current_version=motor.version)

    previous_version = state.version
    previous_battery_version = pack.version
    previous_motor_version = motor.version
    active = command.enabled and command.fault_code is None
    if active:
        battery_power = _thermal_power(
            state.battery_target_temperature_c,
            pack.pack_temperature_c,
            state.max_battery_thermal_power_kw,
        )
        motor_budget = state.max_powertrain_thermal_power_kw
        motor_power = _thermal_power(
            state.motor_target_temperature_c, motor.motor_temperature_c, motor_budget * 0.6
        )
        inverter_power = _thermal_power(
            state.inverter_target_temperature_c,
            motor.inverter_temperature_c,
            motor_budget - abs(motor_power),
        )
        cabin_power = _thermal_power(
            state.cabin_target_temperature_c,
            state.cabin_temperature_c,
            state.max_cabin_thermal_power_kw,
        )
    else:
        battery_power = motor_power = inverter_power = cabin_power = 0.0

    duration_s = command.duration_ms / 1000.0
    pack.pack_temperature_c = round(
        max(
            -30.0,
            min(
                60.0,
                pack.pack_temperature_c
                + (
                    battery_power * 1000.0
                    - 25.0 * (pack.pack_temperature_c - command.ambient_temperature_c)
                )
                * duration_s
                / 300_000.0,
            ),
        ),
        3,
    )
    motor.motor_temperature_c = round(
        max(
            -40.0,
            min(
                150.0,
                motor.motor_temperature_c
                + (
                    motor_power * 1000.0
                    - 45.0 * (motor.motor_temperature_c - command.ambient_temperature_c)
                )
                * duration_s
                / 80_000.0,
            ),
        ),
        3,
    )
    motor.inverter_temperature_c = round(
        max(
            -40.0,
            min(
                110.0,
                motor.inverter_temperature_c
                + (
                    inverter_power * 1000.0
                    - 30.0 * (motor.inverter_temperature_c - command.ambient_temperature_c)
                )
                * duration_s
                / 50_000.0,
            ),
        ),
        3,
    )
    state.cabin_temperature_c = round(
        max(
            -40.0,
            min(
                80.0,
                state.cabin_temperature_c
                + (
                    cabin_power * 1000.0
                    + command.cabin_heat_load_kw * 1000.0
                    - 80.0 * (state.cabin_temperature_c - command.ambient_temperature_c)
                )
                * duration_s
                / 150_000.0,
            ),
        ),
        3,
    )
    pack.cells = _cells(
        count=pack.series_cell_count,
        soc_pct=pack.soc_pct,
        temperature_c=pack.pack_temperature_c,
        nominal_voltage=pack.nominal_cell_voltage_v,
    )
    state.battery_thermal_power_kw = round(battery_power, 3)
    state.motor_thermal_power_kw = round(motor_power, 3)
    state.inverter_thermal_power_kw = round(inverter_power, 3)
    state.cabin_thermal_power_kw = round(cabin_power, 3)
    state.auxiliary_power_kw = round(
        abs(battery_power) + abs(motor_power) + abs(inverter_power) + abs(cabin_power), 3
    )
    state.fault_code = command.fault_code
    powers = (battery_power, motor_power, inverter_power, cabin_power)
    if command.fault_code is not None:
        state.operating_state = ThermalOperatingState.FAULTED.value
        state.limiting_reason = "thermal_system_fault"
    elif not command.enabled:
        state.operating_state = ThermalOperatingState.STANDBY.value
        state.limiting_reason = "thermal_management_disabled"
    elif any(power > 0.0 for power in powers) and any(power < 0.0 for power in powers):
        state.operating_state = ThermalOperatingState.MIXED.value
        state.limiting_reason = None
    elif any(power > 0.0 for power in powers):
        state.operating_state = ThermalOperatingState.HEATING.value
        state.limiting_reason = None
    elif any(power < 0.0 for power in powers):
        state.operating_state = ThermalOperatingState.COOLING.value
        state.limiting_reason = None
    else:
        state.operating_state = ThermalOperatingState.STANDBY.value
        state.limiting_reason = None

    pack.version += 1
    motor.version += 1
    state.version += 1
    pack.simulation_time_ms += command.duration_ms
    motor.simulation_time_ms += command.duration_ms
    state.simulation_time_ms += command.duration_ms
    rendered = thermal_management_response(state, vehicle, pack, motor)
    result = rendered.model_dump(mode="json")
    session.add(
        ThermalManagementStep(
            vehicle_id=vehicle.id,
            command_id=command.command_id,
            duration_ms=command.duration_ms,
            ambient_temperature_c=command.ambient_temperature_c,
            cabin_heat_load_kw=command.cabin_heat_load_kw,
            enabled=command.enabled,
            fault_code=command.fault_code,
            previous_version=previous_version,
            state_version=state.version,
            previous_battery_version=previous_battery_version,
            battery_state_version=pack.version,
            previous_motor_version=previous_motor_version,
            motor_state_version=motor.version,
            result=result,
            requested_by_user_id=actor_user_id,
        )
    )
    await session.flush()
    payload = {
        "vehicle_id": vehicle.identifier,
        "command_id": command.command_id,
        "operating_state": state.operating_state,
        "auxiliary_power_kw": state.auxiliary_power_kw,
        "battery_temperature_c": pack.pack_temperature_c,
        "motor_temperature_c": motor.motor_temperature_c,
        "inverter_temperature_c": motor.inverter_temperature_c,
        "cabin_temperature_c": state.cabin_temperature_c,
        "battery_version": pack.version,
        "motor_version": motor.version,
        "version": state.version,
        "simulation_time_ms": state.simulation_time_ms,
        "fault_code": state.fault_code,
    }
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.thermal.step.completed.v1",
        aggregate_type="thermal_management",
        aggregate_id=state.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.thermal_step_completed",
        resource_type="thermal_management",
        resource_id=state.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return rendered, False
