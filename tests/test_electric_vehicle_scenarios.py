from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from atep.audit.models import AuditRecord
from atep.can_network.models import CanFrameTransmission, CanNetwork
from atep.core.errors import (
    ElectricVehicleScenarioConflictError,
    ElectricVehicleScenarioVersionConflictError,
)
from atep.diagnostics.models import DiagnosticTroubleCode
from atep.ecus.models import ElectronicControlUnit
from atep.electric_vehicle.models import (
    BatteryPackState,
    ChargingSystemState,
    ElectricVehicleScenarioExecution,
    MotorInverterState,
    RangeEstimatorState,
    RegenerativeBrakeState,
    ThermalManagementState,
)
from atep.electric_vehicle.scenario_service import execute_electric_vehicle_scenario
from atep.electric_vehicle.schemas import ElectricVehicleScenarioCommand
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
        now = datetime(2026, 9, 4, tzinfo=UTC)
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()
            if getattr(value, "created_at", None) is None:
                value.created_at = now
                value.updated_at = now


def states() -> tuple[Any, ...]:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    vehicle = Vehicle(
        id=uuid4(),
        identifier="vehicle-001",
        display_name="Reference EV",
        model="EV",
        description="",
        status="active",
        created_at=now,
        updated_at=now,
    )
    pack = BatteryPackState(
        id=uuid4(),
        vehicle_id=vehicle.id,
        chemistry="lfp",
        series_cell_count=4,
        nominal_capacity_ah=100.0,
        nominal_cell_voltage_v=3.2,
        internal_resistance_ohm=0.08,
        soc_pct=80.0,
        soh_pct=100.0,
        pack_voltage_v=12.8,
        pack_current_a=0.0,
        pack_temperature_c=25.0,
        contactor_state="closed",
        operating_state="normal",
        cells=[
            {"index": index, "voltage_v": 3.2, "temperature_c": 25.0, "soc_pct": 80.0}
            for index in range(1, 5)
        ],
        version=2,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )
    motor = MotorInverterState(
        id=uuid4(),
        vehicle_id=vehicle.id,
        max_torque_nm=400.0,
        max_speed_rpm=16_000,
        max_inverter_power_kw=180.0,
        base_efficiency_pct=94.0,
        requested_torque_nm=100.0,
        delivered_torque_nm=100.0,
        motor_speed_rpm=4_000,
        mechanical_power_kw=40.0,
        electrical_power_kw=45.0,
        efficiency_pct=94.0,
        power_loss_kw=5.0,
        motor_temperature_c=60.0,
        inverter_temperature_c=55.0,
        drive_mode="normal",
        operating_state="ready",
        limiting_reason=None,
        version=3,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )
    brake = RegenerativeBrakeState(
        id=uuid4(),
        vehicle_id=vehicle.id,
        vehicle_mass_kg=2_000.0,
        wheel_radius_m=0.34,
        final_drive_ratio=9.0,
        drivetrain_efficiency_pct=90.0,
        max_regen_torque_nm=180.0,
        max_regen_power_kw=100.0,
        regen_efficiency_pct=85.0,
        max_friction_deceleration_mps2=9.0,
        requested_deceleration_mps2=2.0,
        delivered_deceleration_mps2=2.0,
        vehicle_speed_mps=20.0,
        regenerative_deceleration_mps2=1.5,
        friction_deceleration_mps2=0.5,
        regenerative_motor_torque_nm=100.0,
        recovered_power_kw=30.0,
        recovered_energy_kwh=0.1,
        cumulative_recovered_energy_kwh=1.0,
        battery_charge_acceptance_kw=80.0,
        operating_state="blended",
        limiting_reason=None,
        version=4,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )
    charging = ChargingSystemState(
        id=uuid4(),
        vehicle_id=vehicle.id,
        max_ac_power_kw=22.0,
        max_dc_power_kw=180.0,
        charging_efficiency_pct=92.0,
        session_id="charge-001",
        connector_type="dc_ccs",
        target_soc_pct=90.0,
        requested_power_kw=100.0,
        delivered_power_kw=80.0,
        charged_energy_kwh=1.0,
        session_energy_kwh=1.0,
        battery_charge_acceptance_kw=80.0,
        operating_state="charging",
        limiting_reason=None,
        fault_code=None,
        version=5,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )
    thermal = ThermalManagementState(
        id=uuid4(),
        vehicle_id=vehicle.id,
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
        auxiliary_power_kw=0.0,
        operating_state="standby",
        limiting_reason=None,
        fault_code=None,
        version=6,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )
    range_state = RangeEstimatorState(
        id=uuid4(),
        vehicle_id=vehicle.id,
        vehicle_mass_kg=2_100.0,
        drag_coefficient=0.27,
        frontal_area_m2=2.4,
        rolling_resistance_coefficient=0.011,
        drivetrain_efficiency_pct=92.0,
        regenerative_efficiency_pct=70.0,
        base_auxiliary_power_kw=0.5,
        reserve_soc_pct=5.0,
        last_cycle_id="cycle-001",
        distance_km=10.0,
        traction_energy_kwh=2.0,
        auxiliary_energy_kwh=0.1,
        recovered_energy_kwh=0.2,
        net_energy_kwh=1.9,
        consumption_kwh_per_100km=19.0,
        estimated_range_km=300.0,
        operating_state="completed",
        limiting_reason=None,
        version=7,
        simulation_time_ms=0,
        created_at=now,
        updated_at=now,
    )
    ecu_id = uuid4()
    ecu = ElectronicControlUnit(
        id=ecu_id,
        vehicle_id=vehicle.id,
        identifier="bms-ecu",
        display_name="BMS ECU",
        ecu_type="battery",
        operational_state="running",
        memory=[],
        memory_regions=[],
        faults=[],
        signals=[],
        cyclic_tasks=[],
        behavior_state={},
        profile_version="1.0.0",
        version=8,
        simulation_time_ms=0,
        boot_count=1,
        created_at=now,
        updated_at=now,
    )
    network = CanNetwork(
        id=uuid4(),
        vehicle_id=vehicle.id,
        identifier="powertrain-can",
        display_name="Powertrain CAN",
        bitrate_kbps=500,
        can_fd_enabled=False,
        data_bitrate_kbps=None,
        nodes=[{"ecu_id": str(ecu_id), "role": "participant"}],
        frame_contracts=[
            {
                "identifier": "bms_status",
                "frame_id": 0x351,
                "frame_format": "standard",
                "protocol": "classic",
                "dlc": 8,
                "bitrate_switch": False,
                "producer_node_id": str(ecu_id),
                "consumer_node_ids": [],
            }
        ],
        error_states={},
        lin_channels=[],
        ethernet_segments=[],
        gateway_routes=[],
        version=9,
        simulation_time_us=0,
        next_sequence=1,
        created_at=now,
        updated_at=now,
    )
    return vehicle, pack, motor, brake, charging, thermal, range_state, ecu, network


def command(**changes: Any) -> ElectricVehicleScenarioCommand:
    values: dict[str, Any] = {
        "execution_id": "ev-scenario-001",
        "bms_ecu_id": "bms-ecu",
        "can_contract_id": "bms_status",
        "expected_battery_version": 2,
        "expected_motor_version": 3,
        "expected_brake_version": 4,
        "expected_charging_version": 5,
        "expected_thermal_version": 6,
        "expected_range_version": 7,
        "expected_bms_ecu_version": 8,
        "expected_can_version": 9,
    }
    values.update(changes)
    return ElectricVehicleScenarioCommand(**values)


def test_scenario_contract_is_bounded() -> None:
    with pytest.raises(ValidationError):
        command(target_temperature_c=59.9)
    with pytest.raises(ValidationError):
        command(duration_ms=999)


@pytest.mark.asyncio
async def test_overtemperature_scenario_correlates_ev_can_uds_and_audit_evidence() -> None:
    vehicle, pack, motor, brake, charging, thermal, range_state, ecu, network = states()
    session = FakeSession(
        None, pack, motor, brake, charging, thermal, range_state, ecu, network, None
    )
    scenario, duplicate = await execute_electric_vehicle_scenario(
        cast(AsyncSession, session),
        vehicle=vehicle,
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=uuid4(),
    )
    assert duplicate is False
    assert scenario.status == "passed"
    assert pack.operating_state == "protection" and pack.contactor_state == "open"
    assert motor.operating_state == "protection" and motor.delivered_torque_nm == 0.0
    assert brake.operating_state == "friction" and brake.recovered_power_kw == 0.0
    assert charging.operating_state == "faulted"
    assert thermal.operating_state == "cooling" and thermal.battery_thermal_power_kw == -8.0
    assert range_state.operating_state == "limited" and range_state.estimated_range_km == 0.0
    assert ecu.operational_state == "fault"
    assert network.version == 10
    transmission = next(item for item in session.added if isinstance(item, CanFrameTransmission))
    dtc = next(item for item in session.added if isinstance(item, DiagnosticTroubleCode))
    event = next(item for item in session.added if isinstance(item, OutboxEvent))
    audit = next(item for item in session.added if isinstance(item, AuditRecord))
    assert transmission.payload[:3] == [2, 138, 1]
    assert dtc.code == "0A7E00" and dtc.status_mask == 0x0F
    assert event.event_type == "atep.electric_vehicle.scenario.completed.v1"
    assert audit.action == "electric_vehicle.scenario_completed"
    replay, replayed = await execute_electric_vehicle_scenario(
        cast(AsyncSession, FakeSession(scenario)),
        vehicle=vehicle,
        command=command(),
        actor_user_id=uuid4(),
        correlation_id=None,
    )
    assert replay is scenario and replayed is True


@pytest.mark.asyncio
async def test_scenario_replay_is_idempotent_and_conflicts_are_stable() -> None:
    vehicle = states()[0]
    existing = ElectricVehicleScenarioExecution(
        id=uuid4(),
        vehicle_id=vehicle.id,
        execution_id="ev-scenario-001",
        scenario_type="battery_overtemperature",
        request_hash="different",
        request={},
        result={},
        status="passed",
        requested_by_user_id=uuid4(),
    )
    with pytest.raises(ElectricVehicleScenarioConflictError):
        await execute_electric_vehicle_scenario(
            cast(AsyncSession, FakeSession(existing)),
            vehicle=vehicle,
            command=command(),
            actor_user_id=uuid4(),
            correlation_id=None,
        )


@pytest.mark.asyncio
async def test_scenario_rejects_stale_resource_version_before_mutation() -> None:
    vehicle, pack, motor, brake, charging, thermal, range_state, ecu, network = states()
    session = FakeSession(None, pack, motor, brake, charging, thermal, range_state, ecu, network)
    with pytest.raises(ElectricVehicleScenarioVersionConflictError) as captured:
        await execute_electric_vehicle_scenario(
            cast(AsyncSession, session),
            vehicle=vehicle,
            command=command(expected_thermal_version=99),
            actor_user_id=uuid4(),
            correlation_id=None,
        )
    assert captured.value.details == {"resource": "thermal", "current_version": 6}
    assert pack.operating_state == "normal"
