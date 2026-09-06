import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.service import record_audit
from atep.can_network.models import CanFrameTransmission, CanNetwork
from atep.can_network.schemas import CanFrameContract
from atep.core.errors import (
    ElectricVehicleScenarioConflictError,
    ElectricVehicleScenarioContractError,
    ElectricVehicleScenarioVersionConflictError,
    ResourceNotFoundError,
)
from atep.diagnostics.models import DiagnosticTroubleCode
from atep.ecus.models import ElectronicControlUnit
from atep.ecus.schemas import EcuFault, EcuSignalContract
from atep.electric_vehicle.models import (
    BatteryPackState,
    ChargingSystemState,
    ElectricVehicleScenarioExecution,
    MotorInverterState,
    RangeEstimatorState,
    RegenerativeBrakeState,
    ThermalManagementState,
)
from atep.electric_vehicle.schemas import (
    ElectricVehicleScenarioCommand,
    ElectricVehicleScenarioResponse,
)
from atep.events.outbox import enqueue_event
from atep.vehicles.models import Vehicle


def _request_hash(command: ElectricVehicleScenarioCommand) -> str:
    payload = command.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


async def _locked_state(
    session: AsyncSession, model: type[Any], *, vehicle: Vehicle, resource: str
) -> Any:
    state = await session.scalar(
        select(model).where(model.vehicle_id == vehicle.id).with_for_update()
    )
    if state is None:
        raise ResourceNotFoundError(resource)
    return state


def _require_version(resource: str, current: int, expected: int) -> None:
    if current != expected:
        raise ElectricVehicleScenarioVersionConflictError(
            resource=resource, current_version=current
        )


def _upsert_signal(ecu: ElectronicControlUnit, signal: EcuSignalContract) -> None:
    signals = [EcuSignalContract.model_validate(item) for item in ecu.signals]
    signals = [item for item in signals if item.name != signal.name]
    signals.append(signal)
    ecu.signals = [item.model_dump(mode="json") for item in signals]


def _upsert_fault(ecu: ElectronicControlUnit, fault: EcuFault) -> None:
    faults = [EcuFault.model_validate(item) for item in ecu.faults]
    faults = [item for item in faults if item.code != fault.code]
    faults.append(fault)
    ecu.faults = [item.model_dump(mode="json") for item in faults]


def _can_contract(network: CanNetwork, identifier: str) -> CanFrameContract:
    for item in network.frame_contracts:
        contract = CanFrameContract.model_validate(item)
        if contract.identifier == identifier:
            return contract
    raise ElectricVehicleScenarioContractError(
        reason="the requested CAN frame contract does not exist"
    )


def _scenario_response(
    scenario: ElectricVehicleScenarioExecution,
    *,
    vehicle: Vehicle,
    duplicate: bool = False,
) -> ElectricVehicleScenarioResponse:
    return ElectricVehicleScenarioResponse(
        id=scenario.id,
        execution_id=scenario.execution_id,
        vehicle_id=vehicle.identifier,
        scenario_type=scenario.scenario_type,
        status=scenario.status,
        duplicate=duplicate,
        created_at=scenario.created_at,
        **scenario.result,
    )


async def execute_electric_vehicle_scenario(
    session: AsyncSession,
    *,
    vehicle: Vehicle,
    command: ElectricVehicleScenarioCommand,
    actor_user_id: UUID,
    correlation_id: UUID | None,
) -> tuple[ElectricVehicleScenarioExecution, bool]:
    request_hash = _request_hash(command)
    existing = await session.scalar(
        select(ElectricVehicleScenarioExecution).where(
            ElectricVehicleScenarioExecution.vehicle_id == vehicle.id,
            ElectricVehicleScenarioExecution.execution_id == command.execution_id,
        )
    )
    if existing is not None:
        if existing.request_hash == request_hash:
            return existing, True
        raise ElectricVehicleScenarioConflictError()

    pack = await _locked_state(session, BatteryPackState, vehicle=vehicle, resource="battery_pack")
    motor = await _locked_state(
        session, MotorInverterState, vehicle=vehicle, resource="motor_inverter"
    )
    brake = await _locked_state(
        session, RegenerativeBrakeState, vehicle=vehicle, resource="regenerative_brake"
    )
    charging = await _locked_state(
        session, ChargingSystemState, vehicle=vehicle, resource="charging_system"
    )
    thermal = await _locked_state(
        session, ThermalManagementState, vehicle=vehicle, resource="thermal_management"
    )
    range_state = await _locked_state(
        session, RangeEstimatorState, vehicle=vehicle, resource="range_estimator"
    )
    bms_ecu = await session.scalar(
        select(ElectronicControlUnit)
        .where(
            ElectronicControlUnit.vehicle_id == vehicle.id,
            ElectronicControlUnit.identifier == command.bms_ecu_id,
        )
        .with_for_update()
    )
    if bms_ecu is None:
        raise ResourceNotFoundError("ecu")
    if bms_ecu.ecu_type != "battery":
        raise ElectricVehicleScenarioContractError(
            reason="the selected ECU must have the battery ECU type"
        )
    network = await _locked_state(session, CanNetwork, vehicle=vehicle, resource="can_network")

    resources = {
        "battery": (pack.version, command.expected_battery_version),
        "motor": (motor.version, command.expected_motor_version),
        "brake": (brake.version, command.expected_brake_version),
        "charging": (charging.version, command.expected_charging_version),
        "thermal": (thermal.version, command.expected_thermal_version),
        "range": (range_state.version, command.expected_range_version),
        "bms_ecu": (bms_ecu.version, command.expected_bms_ecu_version),
        "can_network": (network.version, command.expected_can_version),
    }
    for resource, (current, expected) in resources.items():
        _require_version(resource, current, expected)
    versions_before = {name: current for name, (current, _expected) in resources.items()}

    contract = _can_contract(network, command.can_contract_id)
    if contract.producer_node_id != bms_ecu.id:
        raise ElectricVehicleScenarioContractError(
            reason="the CAN frame contract must be produced by the selected BMS ECU"
        )
    temperature_raw = round(command.target_temperature_c * 10)
    payload = [temperature_raw >> 8, temperature_raw & 0xFF, 1]
    if contract.dlc < len(payload):
        raise ElectricVehicleScenarioContractError(
            reason="the CAN frame contract requires at least three payload bytes"
        )
    payload.extend([0] * (contract.dlc - len(payload)))

    pack.pack_temperature_c = command.target_temperature_c
    pack.pack_current_a = 0.0
    pack.operating_state = "protection"
    pack.contactor_state = "open"
    pack.cells = [{**cell, "temperature_c": command.target_temperature_c} for cell in pack.cells]
    pack.version += 1
    pack.simulation_time_ms += command.duration_ms

    motor.requested_torque_nm = 0.0
    motor.delivered_torque_nm = 0.0
    motor.mechanical_power_kw = 0.0
    motor.electrical_power_kw = 0.0
    motor.operating_state = "protection"
    motor.limiting_reason = "bms_protection"
    motor.version += 1
    motor.simulation_time_ms += command.duration_ms

    brake.regenerative_deceleration_mps2 = 0.0
    brake.regenerative_motor_torque_nm = 0.0
    brake.recovered_power_kw = 0.0
    brake.recovered_energy_kwh = 0.0
    brake.battery_charge_acceptance_kw = 0.0
    brake.operating_state = "friction"
    brake.limiting_reason = "bms_protection"
    brake.version += 1
    brake.simulation_time_ms += command.duration_ms

    charging.requested_power_kw = 0.0
    charging.delivered_power_kw = 0.0
    charging.battery_charge_acceptance_kw = 0.0
    charging.operating_state = "faulted"
    charging.limiting_reason = "bms_protection"
    charging.fault_code = "BATTERY_OVERTEMPERATURE"
    charging.version += 1
    charging.simulation_time_ms += command.duration_ms

    thermal.battery_thermal_power_kw = -thermal.max_battery_thermal_power_kw
    thermal.auxiliary_power_kw = round(
        abs(thermal.battery_thermal_power_kw)
        + abs(thermal.motor_thermal_power_kw)
        + abs(thermal.inverter_thermal_power_kw)
        + abs(thermal.cabin_thermal_power_kw),
        4,
    )
    thermal.operating_state = "cooling"
    thermal.limiting_reason = "battery_overtemperature"
    thermal.version += 1
    thermal.simulation_time_ms += command.duration_ms

    range_state.estimated_range_km = 0.0
    range_state.operating_state = "limited"
    range_state.limiting_reason = "bms_protection"
    range_state.version += 1
    range_state.simulation_time_ms += command.duration_ms

    bms_ecu.operational_state = "fault"
    bms_ecu.simulation_time_ms += command.duration_ms
    _upsert_signal(
        bms_ecu,
        EcuSignalContract(
            name="battery_temperature",
            direction="produced",
            data_type="decimal",
            unit="celsius",
            minimum=-50.0,
            maximum=120.0,
            cycle_time_ms=100,
            value=command.target_temperature_c,
            updated_at_ms=bms_ecu.simulation_time_ms,
        ),
    )
    _upsert_fault(
        bms_ecu,
        EcuFault(
            code="BATTERY_OVERTEMPERATURE",
            severity="critical",
            status="confirmed",
            description="Battery temperature exceeded the protection threshold.",
            active=True,
            latched=True,
            occurrence_count=2,
            confirmation_threshold=2,
            first_seen_ms=bms_ecu.simulation_time_ms,
            last_seen_ms=bms_ecu.simulation_time_ms,
            confirmed_at_ms=bms_ecu.simulation_time_ms,
        ),
    )
    bms_ecu.version += 1

    previous_can_version = network.version
    transmission = CanFrameTransmission(
        network_id=network.id,
        command_id=f"{command.execution_id}:can",
        contract_id=contract.identifier,
        producer_node_id=contract.producer_node_id,
        frame_id=contract.frame_id,
        frame_format=contract.frame_format.value,
        protocol=contract.protocol.value,
        bitrate_switch=contract.bitrate_switch,
        request={"scenario_execution_id": command.execution_id},
        payload=payload,
        sequence=network.next_sequence,
        transmission_time_us=network.simulation_time_us + command.duration_ms * 1000,
        previous_version=previous_can_version,
        network_version=previous_can_version + 1,
        requested_by_user_id=actor_user_id,
    )
    network.simulation_time_us = transmission.transmission_time_us
    network.next_sequence += 1
    network.version += 1
    session.add(transmission)

    dtc = await session.scalar(
        select(DiagnosticTroubleCode)
        .where(DiagnosticTroubleCode.ecu_id == bms_ecu.id, DiagnosticTroubleCode.code == "0A7E00")
        .with_for_update()
    )
    if dtc is None:
        dtc = DiagnosticTroubleCode(
            ecu_id=bms_ecu.id,
            code="0A7E00",
            status_mask=0x0F,
            severity="critical",
            description="Battery pack overtemperature protection active.",
            occurrence_count=1,
            first_seen_ms=bms_ecu.simulation_time_ms,
            last_seen_ms=bms_ecu.simulation_time_ms,
            snapshot={
                "temperature_c": command.target_temperature_c,
                "contactor_state": "open",
            },
            version=1,
        )
        session.add(dtc)
    else:
        dtc.status_mask = 0x0F
        dtc.severity = "critical"
        dtc.occurrence_count += 1
        dtc.last_seen_ms = bms_ecu.simulation_time_ms
        dtc.snapshot = {
            "temperature_c": command.target_temperature_c,
            "contactor_state": "open",
        }
        dtc.version += 1

    versions_after = {
        "battery": pack.version,
        "motor": motor.version,
        "brake": brake.version,
        "charging": charging.version,
        "thermal": thermal.version,
        "range": range_state.version,
        "bms_ecu": bms_ecu.version,
        "can_network": network.version,
    }
    assertions = [
        {
            "name": "battery_protection",
            "passed": pack.operating_state == "protection",
            "observed": pack.operating_state,
            "expected": "protection",
        },
        {
            "name": "contactors_open",
            "passed": pack.contactor_state == "open",
            "observed": pack.contactor_state,
            "expected": "open",
        },
        {
            "name": "torque_inhibited",
            "passed": motor.delivered_torque_nm == 0.0,
            "observed": motor.delivered_torque_nm,
            "expected": 0.0,
        },
        {
            "name": "regen_inhibited",
            "passed": brake.recovered_power_kw == 0.0,
            "observed": brake.recovered_power_kw,
            "expected": 0.0,
        },
        {
            "name": "charging_faulted",
            "passed": charging.operating_state == "faulted",
            "observed": charging.operating_state,
            "expected": "faulted",
        },
        {
            "name": "active_cooling",
            "passed": thermal.operating_state == "cooling",
            "observed": thermal.operating_state,
            "expected": "cooling",
        },
        {
            "name": "range_limited",
            "passed": range_state.operating_state == "limited",
            "observed": range_state.operating_state,
            "expected": "limited",
        },
    ]
    result = {
        "versions_before": versions_before,
        "versions_after": versions_after,
        "state_evidence": {
            "temperature_c": pack.pack_temperature_c,
            "battery_state": pack.operating_state,
            "contactor_state": pack.contactor_state,
            "motor_state": motor.operating_state,
            "brake_state": brake.operating_state,
            "charging_state": charging.operating_state,
            "thermal_state": thermal.operating_state,
            "range_state": range_state.operating_state,
            "bms_ecu_state": bms_ecu.operational_state,
        },
        "can_evidence": {
            "contract_id": transmission.contract_id,
            "frame_id": transmission.frame_id,
            "sequence": transmission.sequence,
            "payload": payload,
            "network_version": network.version,
        },
        "uds_evidence": {
            "service": "read_dtc_information",
            "dtc_code": dtc.code,
            "status_mask": dtc.status_mask,
            "severity": dtc.severity,
            "occurrence_count": dtc.occurrence_count,
        },
        "assertions": assertions,
    }
    scenario = ElectricVehicleScenarioExecution(
        vehicle_id=vehicle.id,
        execution_id=command.execution_id,
        scenario_type=command.scenario_type.value,
        request_hash=request_hash,
        request=command.model_dump(mode="json"),
        result=result,
        status="passed" if all(item["passed"] for item in assertions) else "failed",
        requested_by_user_id=actor_user_id,
    )
    session.add(scenario)
    await session.flush()
    evidence = {
        "vehicle_id": vehicle.identifier,
        "execution_id": command.execution_id,
        "scenario_type": command.scenario_type.value,
        "status": scenario.status,
        "bms_ecu_id": bms_ecu.identifier,
        "can_contract_id": contract.identifier,
        "dtc_code": dtc.code,
    }
    enqueue_event(
        session,
        event_type="atep.electric_vehicle.scenario.completed.v1",
        aggregate_type="electric_vehicle_scenario",
        aggregate_id=scenario.id,
        payload=evidence,
        correlation_id=correlation_id,
    )
    record_audit(
        session,
        actor_user_id=actor_user_id,
        action="electric_vehicle.scenario_completed",
        resource_type="electric_vehicle_scenario",
        resource_id=scenario.id,
        correlation_id=correlation_id,
        details=evidence,
    )
    return scenario, False


async def require_electric_vehicle_scenario(
    session: AsyncSession, *, vehicle: Vehicle, execution_id: str
) -> ElectricVehicleScenarioExecution:
    scenario = await session.scalar(
        select(ElectricVehicleScenarioExecution).where(
            ElectricVehicleScenarioExecution.vehicle_id == vehicle.id,
            ElectricVehicleScenarioExecution.execution_id == execution_id,
        )
    )
    if scenario is None:
        raise ResourceNotFoundError("electric_vehicle_scenario")
    return scenario


async def list_electric_vehicle_scenarios(
    session: AsyncSession, *, vehicle: Vehicle, limit: int, offset: int
) -> tuple[list[ElectricVehicleScenarioExecution], int]:
    query = select(ElectricVehicleScenarioExecution).where(
        ElectricVehicleScenarioExecution.vehicle_id == vehicle.id
    )
    total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
    result = await session.execute(
        query.order_by(
            ElectricVehicleScenarioExecution.created_at.desc(),
            ElectricVehicleScenarioExecution.id,
        )
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


def electric_vehicle_scenario_response(
    scenario: ElectricVehicleScenarioExecution,
    *,
    vehicle: Vehicle,
    duplicate: bool = False,
) -> ElectricVehicleScenarioResponse:
    return _scenario_response(scenario, vehicle=vehicle, duplicate=duplicate)
