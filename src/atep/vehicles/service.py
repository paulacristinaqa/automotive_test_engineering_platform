from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.core.errors import (
    DuplicateVehicleIdentifierError,
    InvalidCommandClaimError,
    ModuleCapabilityRequiredError,
    ResourceNotFoundError,
    TelemetryEventConflictError,
    VehicleCommandConflictError,
    VehicleCommandStateError,
    VehicleSimulationStateError,
    VehicleSimulationStepConflictError,
    VehicleSimulationTransitionConflictError,
    VehicleStateVersionConflictError,
)
from atep.core.security import generate_module_token, hash_module_token, verify_module_token
from atep.events.outbox import enqueue_event
from atep.registry.models import PlatformModule
from atep.vehicles.models import (
    Vehicle,
    VehicleCommand,
    VehicleDigitalState,
    VehicleSimulationStep,
    VehicleSimulationTransition,
    VehicleTelemetryEvent,
)
from atep.vehicles.schemas import (
    DigitalVehicleStatePayload,
    DigitalVehicleStateReplace,
    TelemetryIngest,
    VehicleCommandAcknowledge,
    VehicleCommandCreate,
    VehicleCommandStatus,
    VehicleCreate,
    VehicleOperationalMode,
    VehicleSensorReadings,
    VehicleSimulationStepCommand,
    VehicleSimulationTransitionCommand,
    VehicleStatus,
)

COMMAND_CONSUME_CAPABILITY = "vehicle.commands.consume"


async def create_vehicle(
    session: AsyncSession,
    *,
    command: VehicleCreate,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> Vehicle:
    existing = await session.scalar(select(Vehicle).where(Vehicle.identifier == command.identifier))
    if existing is not None:
        raise DuplicateVehicleIdentifierError()
    vehicle = Vehicle(
        identifier=command.identifier,
        display_name=command.display_name,
        model=command.model,
        description=command.description,
        status=VehicleStatus.REGISTERED.value,
    )
    baseline = DigitalVehicleStatePayload()
    vehicle.digital_state = VehicleDigitalState(
        operational_mode=baseline.operational_mode.value,
        battery_state=baseline.battery.model_dump(mode="json"),
        powertrain_state=baseline.powertrain.model_dump(mode="json"),
        brake_state=baseline.brakes.model_dump(mode="json"),
        steering_state=baseline.steering.model_dump(mode="json"),
        lighting_state=baseline.lighting.model_dump(mode="json"),
        suspension_state=baseline.suspension.model_dump(mode="json"),
        version=1,
        simulation_time_ms=0,
    )
    try:
        async with session.begin_nested():
            session.add(vehicle)
            await session.flush()
    except IntegrityError as exc:
        raise DuplicateVehicleIdentifierError() from exc
    payload = _vehicle_payload(vehicle)
    enqueue_event(
        session,
        event_type="atep.vehicle.registered.v1",
        aggregate_type="vehicle",
        aggregate_id=vehicle.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="vehicle.registered",
        resource_type="vehicle",
        resource_id=vehicle.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return vehicle


async def require_vehicle(session: AsyncSession, identifier: str) -> Vehicle:
    vehicle = await session.scalar(select(Vehicle).where(Vehicle.identifier == identifier))
    if vehicle is None:
        raise ResourceNotFoundError("vehicle")
    return vehicle


async def require_vehicle_digital_state(
    session: AsyncSession, *, vehicle: Vehicle, for_update: bool = False
) -> VehicleDigitalState:
    query = select(VehicleDigitalState).where(VehicleDigitalState.vehicle_id == vehicle.id)
    if for_update:
        query = query.with_for_update()
    state = await session.scalar(query)
    if state is None:
        raise ResourceNotFoundError("vehicle_state")
    return state


def digital_state_payload(state: VehicleDigitalState) -> DigitalVehicleStatePayload:
    return DigitalVehicleStatePayload.model_validate(
        {
            "operational_mode": state.operational_mode,
            "battery": state.battery_state,
            "powertrain": state.powertrain_state,
            "brakes": state.brake_state,
            "steering": state.steering_state,
            "lighting": state.lighting_state,
            "suspension": state.suspension_state,
        }
    )


async def replace_vehicle_digital_state(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: DigitalVehicleStateReplace,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[VehicleDigitalState, bool]:
    state = await require_vehicle_digital_state(session, vehicle=vehicle, for_update=True)
    requested = DigitalVehicleStatePayload.model_validate(
        command.model_dump(exclude={"expected_version"})
    )
    current = digital_state_payload(state)
    if command.expected_version != state.version:
        if command.expected_version == state.version - 1 and requested == current:
            return state, True
        raise VehicleStateVersionConflictError(current_version=state.version)
    if requested == current:
        return state, True

    previous_version = state.version
    state.operational_mode = requested.operational_mode.value
    state.battery_state = requested.battery.model_dump(mode="json")
    state.powertrain_state = requested.powertrain.model_dump(mode="json")
    state.brake_state = requested.brakes.model_dump(mode="json")
    state.steering_state = requested.steering.model_dump(mode="json")
    state.lighting_state = requested.lighting.model_dump(mode="json")
    state.suspension_state = requested.suspension.model_dump(mode="json")
    state.version += 1
    await session.flush()
    await session.refresh(state, attribute_names=["updated_at"])
    payload = {
        "vehicle_id": vehicle.identifier,
        "previous_version": previous_version,
        "version": state.version,
        "operational_mode": state.operational_mode,
        "state": requested.model_dump(mode="json"),
    }
    enqueue_event(
        session,
        event_type="atep.digital_vehicle.state.updated.v1",
        aggregate_type="digital_vehicle",
        aggregate_id=vehicle.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="digital_vehicle.state_updated",
        resource_type="vehicle",
        resource_id=vehicle.id,
        correlation_id=correlation_id,
        details={
            "vehicle_id": vehicle.identifier,
            "previous_version": previous_version,
            "version": state.version,
            "operational_mode": state.operational_mode,
        },
    )
    return state, False


_SIMULATION_TRANSITIONS = {
    VehicleOperationalMode.PARKED: VehicleOperationalMode.READY,
    VehicleOperationalMode.READY: VehicleOperationalMode.DRIVING,
    VehicleOperationalMode.DRIVING: VehicleOperationalMode.PARKED,
}


def _transition_matches(
    transition: VehicleSimulationTransition, command: VehicleSimulationTransitionCommand
) -> bool:
    return (
        transition.to_mode == command.target_mode.value
        and transition.duration_ms == command.duration_ms
        and transition.requested_speed_kph == command.speed_kph
        and transition.previous_state_version == command.expected_version
    )


def _apply_simulation_mode(
    current: DigitalVehicleStatePayload, command: VehicleSimulationTransitionCommand
) -> DigitalVehicleStatePayload:
    payload = current.model_dump(mode="json")
    if command.target_mode is VehicleOperationalMode.READY:
        payload["operational_mode"] = "ready"
        payload["battery"]["contactors_closed"] = True
        payload["powertrain"].update(
            motor_enabled=True,
            gear="park",
            speed_kph=0.0,
            requested_torque_nm=0.0,
            delivered_torque_nm=0.0,
        )
        payload["brakes"]["parking_brake_applied"] = True
    elif command.target_mode is VehicleOperationalMode.DRIVING:
        payload["operational_mode"] = "driving"
        payload["battery"]["contactors_closed"] = True
        payload["powertrain"].update(
            motor_enabled=True,
            gear="drive",
            speed_kph=command.speed_kph,
            requested_torque_nm=120.0,
            delivered_torque_nm=120.0,
        )
        payload["brakes"]["parking_brake_applied"] = False
    else:
        payload["operational_mode"] = "parked"
        payload["battery"].update(contactors_closed=False, pack_current_a=0.0)
        payload["powertrain"].update(
            motor_enabled=False,
            gear="park",
            speed_kph=0.0,
            requested_torque_nm=0.0,
            delivered_torque_nm=0.0,
        )
        payload["brakes"].update(
            pedal_pct=0.0,
            hydraulic_pressure_bar=0.0,
            parking_brake_applied=True,
            abs_active=False,
        )
    return DigitalVehicleStatePayload.model_validate(payload)


async def execute_vehicle_simulation_transition(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: VehicleSimulationTransitionCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[VehicleSimulationTransition, bool]:
    existing = await session.scalar(
        select(VehicleSimulationTransition).where(
            VehicleSimulationTransition.vehicle_id == vehicle.id,
            VehicleSimulationTransition.command_id == command.command_id,
        )
    )
    if existing is not None:
        if _transition_matches(existing, command):
            return existing, True
        raise VehicleSimulationTransitionConflictError()

    state = await require_vehicle_digital_state(session, vehicle=vehicle, for_update=True)
    if command.expected_version != state.version:
        raise VehicleStateVersionConflictError(current_version=state.version)
    current = digital_state_payload(state)
    expected_target = _SIMULATION_TRANSITIONS.get(current.operational_mode)
    if expected_target is not command.target_mode:
        raise VehicleSimulationStateError(
            current_mode=current.operational_mode.value,
            requested_mode=command.target_mode.value,
        )
    requested = _apply_simulation_mode(current, command)
    previous_version = state.version
    state.operational_mode = requested.operational_mode.value
    state.battery_state = requested.battery.model_dump(mode="json")
    state.powertrain_state = requested.powertrain.model_dump(mode="json")
    state.brake_state = requested.brakes.model_dump(mode="json")
    state.steering_state = requested.steering.model_dump(mode="json")
    state.lighting_state = requested.lighting.model_dump(mode="json")
    state.suspension_state = requested.suspension.model_dump(mode="json")
    state.version += 1
    state.simulation_time_ms += command.duration_ms
    transition = VehicleSimulationTransition(
        vehicle_id=vehicle.id,
        command_id=command.command_id,
        from_mode=current.operational_mode.value,
        to_mode=command.target_mode.value,
        duration_ms=command.duration_ms,
        requested_speed_kph=command.speed_kph,
        previous_state_version=previous_version,
        state_version=state.version,
        simulation_time_ms=state.simulation_time_ms,
        requested_by_user_id=actor_user_id,
    )
    session.add(transition)
    await session.flush()
    enqueue_event(
        session,
        event_type="atep.digital_vehicle.simulation.transitioned.v1",
        aggregate_type="digital_vehicle",
        aggregate_id=vehicle.id,
        payload={
            "command_id": command.command_id,
            "vehicle_id": vehicle.identifier,
            "from_mode": transition.from_mode,
            "to_mode": transition.to_mode,
            "duration_ms": transition.duration_ms,
            "state_version": transition.state_version,
            "simulation_time_ms": transition.simulation_time_ms,
        },
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="digital_vehicle.simulation_transitioned",
        resource_type="vehicle",
        resource_id=vehicle.id,
        correlation_id=correlation_id,
        details={
            "command_id": transition.command_id,
            "from_mode": transition.from_mode,
            "to_mode": transition.to_mode,
            "duration_ms": transition.duration_ms,
            "state_version": transition.state_version,
            "simulation_time_ms": transition.simulation_time_ms,
        },
    )
    return transition, False


def _step_matches(step: VehicleSimulationStep, command: VehicleSimulationStepCommand) -> bool:
    return (
        step.duration_ms == command.duration_ms
        and step.seed == command.seed
        and step.inputs == command.inputs.model_dump(mode="json")
        and step.sensor_configuration == command.sensors.model_dump(mode="json")
        and step.previous_state_version == command.expected_version
    )


def _seeded_noise(seed: int, sensor: str, amplitude: float) -> float:
    if amplitude == 0:
        return 0.0
    digest = sha256(f"{seed}:{sensor}".encode()).digest()
    fraction = int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)
    return (fraction * 2 - 1) * amplitude


def _sensor_value(value: float, *, seed: int, name: str, configuration: object) -> float:
    from atep.vehicles.schemas import SensorConfiguration, SensorFaultMode

    sensor = SensorConfiguration.model_validate(configuration)
    if sensor.fault_mode is SensorFaultMode.STUCK:
        assert sensor.fault_value is not None
        return sensor.fault_value
    measured = value + _seeded_noise(seed, name, sensor.noise_amplitude)
    if sensor.fault_mode is SensorFaultMode.OFFSET:
        assert sensor.fault_value is not None
        measured += sensor.fault_value
    return measured


def _apply_simulation_step(
    current: DigitalVehicleStatePayload, command: VehicleSimulationStepCommand
) -> tuple[DigitalVehicleStatePayload, VehicleSensorReadings]:
    payload = current.model_dump(mode="json")
    seconds = command.duration_ms / 1000
    inputs = command.inputs
    speed = current.powertrain.speed_kph
    energy_used_wh = 0.0
    energy_recovered_wh = 0.0
    if current.operational_mode is VehicleOperationalMode.DRIVING:
        grade_resistance = inputs.road_grade_pct * 0.025
        acceleration = inputs.accelerator_pct * 0.05 - grade_resistance
        deceleration = inputs.brake_pct * 0.08
        speed = min(250.0, max(0.0, speed + (acceleration - deceleration) * seconds))
        torque = min(3000.0, max(0.0, inputs.accelerator_pct * 12.0 + inputs.road_grade_pct * 8.0))
        regen_torque = min(600.0, inputs.brake_pct * 6.0)
        delivered_torque = torque - regen_torque
        payload["powertrain"].update(
            speed_kph=round(speed, 6),
            requested_torque_nm=round(torque, 6),
            delivered_torque_nm=round(delivered_torque, 6),
        )
        payload["brakes"].update(
            pedal_pct=inputs.brake_pct,
            hydraulic_pressure_bar=round(inputs.brake_pct * 2.5, 6),
        )
        payload["steering"].update(
            wheel_angle_deg=inputs.steering_angle_deg,
            assist_active=True,
        )
        payload["lighting"]["brake_lights"] = inputs.brake_pct > 0
        payload["lighting"]["exterior_mode"] = (
            "low_beam" if inputs.ambient_light_lux < 1000 else "auto"
        )
        traction_power_w = max(0.0, inputs.accelerator_pct * 1000 + inputs.road_grade_pct * 250)
        auxiliary_power_w = 500.0
        energy_used_wh = (traction_power_w + auxiliary_power_w) * seconds / 3600
        regen_power_w = inputs.brake_pct * max(current.powertrain.speed_kph, speed) * 45
        energy_recovered_wh = min(energy_used_wh * 0.8, regen_power_w * seconds / 3600)
        net_energy_wh = round(max(0.0, round(energy_used_wh, 6) - round(energy_recovered_wh, 6)), 6)
        usable_energy_wh = max(0.0, current.battery.usable_energy_wh - net_energy_wh)
        payload["battery"]["usable_energy_wh"] = round(usable_energy_wh, 6)
        capacity_wh = 75000.0
        payload["battery"]["state_of_charge_pct"] = round(
            min(100.0, usable_energy_wh / capacity_wh * 100), 6
        )
        thermal_generation = (abs(delivered_torque) * 0.0008 + inputs.brake_pct * 0.002) * seconds
        thermal_cooling = (
            (current.battery.temperature_c - inputs.ambient_temperature_c) * 0.002 * seconds
        )
        payload["battery"]["temperature_c"] = round(
            min(
                120.0,
                max(-50.0, current.battery.temperature_c + thermal_generation - thermal_cooling),
            ),
            6,
        )
        payload["battery"]["pack_current_a"] = round(
            inputs.accelerator_pct * 4.0 - inputs.brake_pct * 1.5, 6
        )
        speed_mps = speed / 3.6
        lateral_acceleration = min(
            20.0, max(-20.0, speed_mps * speed_mps * inputs.steering_angle_deg / 12000)
        )
        roughness_travel = inputs.road_roughness_pct * 0.6
        payload["suspension"].update(
            front_travel_mm=round(
                min(120.0, max(-120.0, roughness_travel + inputs.brake_pct * 0.35)), 6
            ),
            rear_travel_mm=round(
                min(120.0, max(-120.0, roughness_travel + inputs.accelerator_pct * 0.2)), 6
            ),
            lateral_acceleration_mps2=round(lateral_acceleration, 6),
        )
    elif inputs.accelerator_pct > 0 or inputs.brake_pct > 0 or inputs.steering_angle_deg != 0:
        raise VehicleSimulationStateError(
            current_mode=current.operational_mode.value, requested_mode="actuated"
        )

    requested = DigitalVehicleStatePayload.model_validate(payload)
    readings = VehicleSensorReadings(
        speed_kph=round(
            min(
                400.0,
                max(
                    0.0,
                    _sensor_value(
                        requested.powertrain.speed_kph,
                        seed=command.seed,
                        name="speed",
                        configuration=command.sensors.speed,
                    ),
                ),
            ),
            6,
        ),
        battery_soc_pct=round(
            min(
                100.0,
                max(
                    0.0,
                    _sensor_value(
                        requested.battery.state_of_charge_pct,
                        seed=command.seed,
                        name="battery_soc",
                        configuration=command.sensors.battery_soc,
                    ),
                ),
            ),
            6,
        ),
        battery_temperature_c=round(
            min(
                120.0,
                max(
                    -50.0,
                    _sensor_value(
                        requested.battery.temperature_c,
                        seed=command.seed,
                        name="battery_temperature",
                        configuration=command.sensors.battery_temperature,
                    ),
                ),
            ),
            6,
        ),
        energy_used_wh=round(energy_used_wh, 6),
        energy_recovered_wh=round(energy_recovered_wh, 6),
        net_energy_wh=(
            net_energy_wh if current.operational_mode is VehicleOperationalMode.DRIVING else 0.0
        ),
    )
    return requested, readings


async def execute_vehicle_simulation_step(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: VehicleSimulationStepCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[VehicleSimulationStep, bool]:
    existing = await session.scalar(
        select(VehicleSimulationStep).where(
            VehicleSimulationStep.vehicle_id == vehicle.id,
            VehicleSimulationStep.command_id == command.command_id,
        )
    )
    if existing is not None:
        if _step_matches(existing, command):
            return existing, True
        raise VehicleSimulationStepConflictError()

    state = await require_vehicle_digital_state(session, vehicle=vehicle, for_update=True)
    if command.expected_version != state.version:
        raise VehicleStateVersionConflictError(current_version=state.version)
    requested, readings = _apply_simulation_step(digital_state_payload(state), command)
    previous_version = state.version
    state.battery_state = requested.battery.model_dump(mode="json")
    state.powertrain_state = requested.powertrain.model_dump(mode="json")
    state.brake_state = requested.brakes.model_dump(mode="json")
    state.steering_state = requested.steering.model_dump(mode="json")
    state.lighting_state = requested.lighting.model_dump(mode="json")
    state.suspension_state = requested.suspension.model_dump(mode="json")
    state.version += 1
    state.simulation_time_ms += command.duration_ms
    step = VehicleSimulationStep(
        vehicle_id=vehicle.id,
        command_id=command.command_id,
        duration_ms=command.duration_ms,
        seed=command.seed,
        inputs=command.inputs.model_dump(mode="json"),
        sensor_configuration=command.sensors.model_dump(mode="json"),
        sensor_readings=readings.model_dump(mode="json"),
        previous_state_version=previous_version,
        state_version=state.version,
        simulation_time_ms=state.simulation_time_ms,
        requested_by_user_id=actor_user_id,
    )
    session.add(step)
    await session.flush()
    evidence = {
        "command_id": command.command_id,
        "vehicle_id": vehicle.identifier,
        "duration_ms": command.duration_ms,
        "seed": command.seed,
        "state_version": step.state_version,
        "simulation_time_ms": step.simulation_time_ms,
        "readings": step.sensor_readings,
    }
    enqueue_event(
        session,
        event_type="atep.digital_vehicle.simulation.stepped.v1",
        aggregate_type="digital_vehicle",
        aggregate_id=vehicle.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="digital_vehicle.simulation_stepped",
        resource_type="vehicle",
        resource_id=vehicle.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return step, False


async def list_vehicles(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    status: VehicleStatus | None = None,
) -> tuple[list[Vehicle], int]:
    query = select(Vehicle)
    if status is not None:
        query = query.where(Vehicle.status == status.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(Vehicle.identifier, Vehicle.id).limit(limit).offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def update_vehicle_status(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    status: VehicleStatus,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> Vehicle:
    previous_status = vehicle.status
    vehicle.status = status.value
    await session.flush()
    await session.refresh(vehicle, attribute_names=["updated_at"])
    payload = {
        "vehicle_id": vehicle.identifier,
        "previous_status": previous_status,
        "status": vehicle.status,
    }
    enqueue_event(
        session,
        event_type="atep.vehicle.status-changed.v1",
        aggregate_type="vehicle",
        aggregate_id=vehicle.id,
        payload=payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="vehicle.status_changed",
        resource_type="vehicle",
        resource_id=vehicle.id,
        correlation_id=correlation_id,
        details=payload,
    )
    return vehicle


async def ingest_telemetry(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    module: PlatformModule,
    command: TelemetryIngest,
    correlation_id: UUID | None,
    received_at: datetime | None = None,
) -> tuple[VehicleTelemetryEvent, bool]:
    existing = await session.scalar(
        select(VehicleTelemetryEvent).where(VehicleTelemetryEvent.event_id == command.event_id)
    )
    if existing is not None:
        if not _same_telemetry(existing, vehicle, module, command):
            raise TelemetryEventConflictError()
        return existing, True

    event = VehicleTelemetryEvent(
        event_id=command.event_id,
        vehicle_id=vehicle.id,
        source_module_id=module.id,
        source=command.source,
        property_name=command.property,
        value=command.value,
        unit=command.unit,
        observed_at=command.timestamp,
        created_at=received_at or datetime.now(UTC),
    )
    try:
        async with session.begin_nested():
            session.add(event)
            await session.flush()
    except IntegrityError:
        concurrent = await session.scalar(
            select(VehicleTelemetryEvent).where(VehicleTelemetryEvent.event_id == command.event_id)
        )
        if concurrent is None or not _same_telemetry(concurrent, vehicle, module, command):
            raise TelemetryEventConflictError() from None
        return concurrent, True

    enqueue_event(
        session,
        event_type="atep.vehicle.telemetry.received.v1",
        aggregate_type="vehicle",
        aggregate_id=vehicle.id,
        payload={
            "telemetry_id": str(event.id),
            "event_id": event.event_id,
            "vehicle_id": vehicle.identifier,
            "source_module_id": str(module.id),
            "source": command.source,
            "property": event.property_name,
            "value": event.value,
            "unit": event.unit,
            "timestamp": event.observed_at.isoformat(),
            "received_at": event.created_at.isoformat(),
        },
        correlation_id=correlation_id,
    )
    return event, False


async def list_telemetry(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    limit: int,
    offset: int,
    property_name: str | None = None,
) -> tuple[list[VehicleTelemetryEvent], int]:
    query = select(VehicleTelemetryEvent).where(VehicleTelemetryEvent.vehicle_id == vehicle.id)
    if property_name is not None:
        query = query.where(VehicleTelemetryEvent.property_name == property_name)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(VehicleTelemetryEvent.observed_at.desc(), VehicleTelemetryEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


def _same_telemetry(
    event: VehicleTelemetryEvent,
    vehicle: Vehicle,
    module: PlatformModule,
    command: TelemetryIngest,
) -> bool:
    return (
        event.vehicle_id == vehicle.id
        and event.source_module_id == module.id
        and event.source == command.source
        and event.property_name == command.property
        and event.value == command.value
        and event.unit == command.unit
        and event.observed_at == command.timestamp
    )


def _vehicle_payload(vehicle: Vehicle) -> dict[str, str]:
    return {
        "vehicle_id": vehicle.identifier,
        "display_name": vehicle.display_name,
        "model": vehicle.model,
        "description": vehicle.description,
        "status": vehicle.status,
    }


async def create_vehicle_command(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    actor_user_id: UUID,
    command: VehicleCommandCreate,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[VehicleCommand, bool]:
    existing = await session.scalar(
        select(VehicleCommand).where(VehicleCommand.command_id == command.command_id)
    )
    requested_at = now or datetime.now(UTC)
    available_at = command.available_at or (
        existing.available_at if existing is not None else requested_at
    )
    if existing is not None:
        if not _same_vehicle_command(existing, vehicle, actor_user_id, command, available_at):
            raise VehicleCommandConflictError()
        return existing, True

    target = await session.get(PlatformModule, command.target_module_id)
    if target is None:
        raise ResourceNotFoundError("module")
    if COMMAND_CONSUME_CAPABILITY not in {item.name for item in target.capabilities}:
        raise ModuleCapabilityRequiredError(COMMAND_CONSUME_CAPABILITY)

    queued = VehicleCommand(
        command_id=command.command_id,
        vehicle_id=vehicle.id,
        target_module_id=target.id,
        requested_by_user_id=actor_user_id,
        test_run_id=command.test_run_id,
        kind=command.kind.value,
        payload=command.parameters.model_dump(),
        status=VehicleCommandStatus.PENDING.value,
        attempt_count=0,
        available_at=available_at,
        leased_until=None,
        lease_token_hash=None,
        completed_at=None,
        result=None,
        error_code=None,
        error_message=None,
        created_at=requested_at,
        updated_at=requested_at,
    )
    try:
        async with session.begin_nested():
            session.add(queued)
            await session.flush()
    except IntegrityError as exc:
        raise VehicleCommandConflictError() from exc

    event_payload = _command_event_payload(queued, vehicle)
    enqueue_event(
        session,
        event_type="atep.vehicle.command.requested.v1",
        aggregate_type="vehicle_command",
        aggregate_id=queued.id,
        payload=event_payload,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="vehicle.command_requested",
        resource_type="vehicle_command",
        resource_id=queued.id,
        correlation_id=correlation_id,
        details=event_payload,
    )
    return queued, False


async def list_vehicle_commands(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    limit: int,
    offset: int,
    status: VehicleCommandStatus | None = None,
) -> tuple[list[VehicleCommand], int]:
    query = select(VehicleCommand).where(VehicleCommand.vehicle_id == vehicle.id)
    if status is not None:
        query = query.where(VehicleCommand.status == status.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    result = await session.execute(
        query.order_by(VehicleCommand.created_at.desc(), VehicleCommand.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total or 0)


async def claim_next_vehicle_command(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    module: PlatformModule,
    lease_seconds: int,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[VehicleCommand | None, str | None]:
    claimed_at = now or datetime.now(UTC)
    query = (
        select(VehicleCommand)
        .where(
            VehicleCommand.vehicle_id == vehicle.id,
            VehicleCommand.target_module_id == module.id,
            VehicleCommand.available_at <= claimed_at,
            or_(
                VehicleCommand.status == VehicleCommandStatus.PENDING.value,
                (
                    (VehicleCommand.status == VehicleCommandStatus.CLAIMED.value)
                    & (VehicleCommand.leased_until <= claimed_at)
                ),
            ),
        )
        .order_by(VehicleCommand.available_at, VehicleCommand.created_at, VehicleCommand.id)
        .with_for_update(skip_locked=True)
    )
    command = await session.scalar(query)
    if command is None:
        return None, None

    claim_token = generate_module_token()
    command.status = VehicleCommandStatus.CLAIMED.value
    command.attempt_count += 1
    command.leased_until = claimed_at + timedelta(seconds=lease_seconds)
    command.lease_token_hash = hash_module_token(claim_token)
    command.updated_at = claimed_at
    await session.flush()
    enqueue_event(
        session,
        event_type="atep.vehicle.command.claimed.v1",
        aggregate_type="vehicle_command",
        aggregate_id=command.id,
        payload={
            **_command_event_payload(command, vehicle),
            "attempt_count": command.attempt_count,
            "leased_until": command.leased_until.isoformat(),
        },
        correlation_id=correlation_id,
    )
    return command, claim_token


async def acknowledge_vehicle_command(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    module: PlatformModule,
    command_id: str,
    acknowledgement: VehicleCommandAcknowledge,
    correlation_id: UUID | None,
    now: datetime | None = None,
) -> tuple[VehicleCommand, bool]:
    command = await session.scalar(
        select(VehicleCommand).where(
            VehicleCommand.command_id == command_id,
            VehicleCommand.vehicle_id == vehicle.id,
            VehicleCommand.target_module_id == module.id,
        )
    )
    if command is None:
        raise ResourceNotFoundError("vehicle_command")
    if command.lease_token_hash is None or not verify_module_token(
        acknowledgement.claim_token, command.lease_token_hash
    ):
        raise InvalidCommandClaimError()

    terminal_statuses = {
        VehicleCommandStatus.SUCCEEDED.value,
        VehicleCommandStatus.FAILED.value,
        VehicleCommandStatus.REJECTED.value,
    }
    if command.status in terminal_statuses:
        if not _same_acknowledgement(command, acknowledgement):
            raise VehicleCommandStateError()
        return command, True
    if command.status != VehicleCommandStatus.CLAIMED.value:
        raise VehicleCommandStateError()

    completed_at = now or datetime.now(UTC)
    if command.leased_until is None or command.leased_until < completed_at:
        raise InvalidCommandClaimError()
    command.status = acknowledgement.outcome.value
    command.result = acknowledgement.result
    command.error_code = acknowledgement.error_code
    command.error_message = acknowledgement.error_message
    command.completed_at = completed_at
    command.leased_until = None
    command.updated_at = completed_at
    await session.flush()
    enqueue_event(
        session,
        event_type="atep.vehicle.command.completed.v1",
        aggregate_type="vehicle_command",
        aggregate_id=command.id,
        payload={
            **_command_event_payload(command, vehicle),
            "result": command.result,
            "error_code": command.error_code,
            "error_message": command.error_message,
            "completed_at": completed_at.isoformat(),
        },
        correlation_id=correlation_id,
    )
    return command, False


def _same_vehicle_command(
    existing: VehicleCommand,
    vehicle: Vehicle,
    actor_user_id: UUID,
    command: VehicleCommandCreate,
    available_at: datetime,
) -> bool:
    return (
        existing.vehicle_id == vehicle.id
        and existing.target_module_id == command.target_module_id
        and existing.requested_by_user_id == actor_user_id
        and existing.test_run_id == command.test_run_id
        and existing.kind == command.kind.value
        and existing.payload == command.parameters.model_dump()
        and existing.available_at == available_at
    )


def _same_acknowledgement(
    command: VehicleCommand, acknowledgement: VehicleCommandAcknowledge
) -> bool:
    return (
        command.status == acknowledgement.outcome.value
        and command.result == acknowledgement.result
        and command.error_code == acknowledgement.error_code
        and command.error_message == acknowledgement.error_message
    )


def _command_event_payload(command: VehicleCommand, vehicle: Vehicle) -> dict[str, object]:
    return {
        "command_id": command.command_id,
        "vehicle_id": vehicle.identifier,
        "target_module_id": str(command.target_module_id),
        "requested_by_user_id": str(command.requested_by_user_id),
        "test_run_id": command.test_run_id,
        "kind": command.kind,
        "parameters": command.payload,
        "status": command.status,
    }
