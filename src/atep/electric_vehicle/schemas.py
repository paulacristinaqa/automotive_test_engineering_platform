from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BatteryChemistry(StrEnum):
    LFP = "lfp"
    NMC = "nmc"


class BatteryContactorState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class BatteryOperatingState(StrEnum):
    NORMAL = "normal"
    WARNING = "warning"
    PROTECTION = "protection"


class BatteryCellState(BaseModel):
    index: int = Field(ge=1, le=192)
    voltage_v: float = Field(ge=2.0, le=5.0)
    temperature_c: float = Field(ge=-50.0, le=120.0)
    soc_pct: float = Field(ge=0.0, le=100.0)


class BatteryPackCreate(BaseModel):
    chemistry: BatteryChemistry = BatteryChemistry.LFP
    series_cell_count: int = Field(default=96, ge=4, le=192)
    nominal_capacity_ah: float = Field(default=100.0, gt=0.0, le=1000.0)
    nominal_cell_voltage_v: float = Field(default=3.2, ge=2.5, le=4.3)
    internal_resistance_ohm: float = Field(default=0.08, gt=0.0, le=2.0)
    initial_soc_pct: float = Field(default=80.0, ge=0.0, le=100.0)
    initial_soh_pct: float = Field(default=100.0, ge=1.0, le=100.0)
    initial_temperature_c: float = Field(default=25.0, ge=-40.0, le=80.0)


class BatterySimulationCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    command_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    duration_ms: int = Field(ge=1, le=3_600_000)
    pack_current_a: float = Field(ge=-1000.0, le=1000.0)
    ambient_temperature_c: float = Field(default=25.0, ge=-50.0, le=80.0)
    expected_version: int = Field(ge=1)


class BatteryPackResponse(BaseModel):
    vehicle_id: str
    chemistry: BatteryChemistry
    series_cell_count: int
    nominal_capacity_ah: float
    nominal_energy_kwh: float
    soc_pct: float
    soh_pct: float
    pack_voltage_v: float
    pack_current_a: float
    pack_power_kw: float
    pack_temperature_c: float
    minimum_cell_voltage_v: float
    maximum_cell_voltage_v: float
    minimum_cell_temperature_c: float
    maximum_cell_temperature_c: float
    contactor_state: BatteryContactorState
    operating_state: BatteryOperatingState
    cells: list[BatteryCellState]
    version: int
    simulation_time_ms: int
    duplicate: bool = False

    @model_validator(mode="after")
    def validate_cell_count(self) -> "BatteryPackResponse":
        if len(self.cells) != self.series_cell_count:
            raise ValueError("cells must match series_cell_count")
        return self


class DriveMode(StrEnum):
    ECO = "eco"
    NORMAL = "normal"
    SPORT = "sport"


class PowertrainOperatingState(StrEnum):
    STANDBY = "standby"
    READY = "ready"
    DERATED = "derated"
    PROTECTION = "protection"


class MotorInverterCreate(BaseModel):
    max_torque_nm: float = Field(default=400.0, gt=0.0, le=2_000.0)
    max_speed_rpm: int = Field(default=16_000, ge=1_000, le=30_000)
    max_inverter_power_kw: float = Field(default=180.0, gt=0.0, le=1_500.0)
    base_efficiency_pct: float = Field(default=94.0, ge=50.0, le=99.5)
    initial_motor_temperature_c: float = Field(default=25.0, ge=-40.0, le=140.0)
    initial_inverter_temperature_c: float = Field(default=25.0, ge=-40.0, le=100.0)


class MotorSimulationCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    command_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    duration_ms: int = Field(ge=1, le=3_600_000)
    requested_torque_nm: float = Field(ge=0.0, le=2_000.0)
    motor_speed_rpm: int = Field(ge=0, le=30_000)
    drive_mode: DriveMode = DriveMode.NORMAL
    ambient_temperature_c: float = Field(default=25.0, ge=-50.0, le=80.0)
    expected_version: int = Field(ge=1)


class MotorInverterResponse(BaseModel):
    vehicle_id: str
    max_torque_nm: float
    max_speed_rpm: int
    max_inverter_power_kw: float
    base_efficiency_pct: float
    requested_torque_nm: float
    delivered_torque_nm: float
    motor_speed_rpm: int
    mechanical_power_kw: float
    electrical_power_kw: float
    efficiency_pct: float
    power_loss_kw: float
    battery_power_limit_kw: float
    motor_temperature_c: float
    inverter_temperature_c: float
    drive_mode: DriveMode
    operating_state: PowertrainOperatingState
    limiting_reason: str | None
    version: int
    simulation_time_ms: int
    duplicate: bool = False


class BrakeOperatingState(StrEnum):
    STANDBY = "standby"
    REGENERATIVE = "regenerative"
    BLENDED = "blended"
    FRICTION = "friction"
    LIMITED = "limited"


class RegenerativeBrakeCreate(BaseModel):
    vehicle_mass_kg: float = Field(default=2_000.0, ge=500.0, le=10_000.0)
    wheel_radius_m: float = Field(default=0.34, ge=0.15, le=1.0)
    final_drive_ratio: float = Field(default=9.0, ge=1.0, le=25.0)
    drivetrain_efficiency_pct: float = Field(default=90.0, ge=50.0, le=99.5)
    max_regen_torque_nm: float = Field(default=180.0, gt=0.0, le=2_000.0)
    max_regen_power_kw: float = Field(default=100.0, gt=0.0, le=1_000.0)
    regen_efficiency_pct: float = Field(default=85.0, ge=50.0, le=99.5)
    max_friction_deceleration_mps2: float = Field(default=9.0, gt=0.0, le=15.0)


class BrakeSimulationCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    command_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    duration_ms: int = Field(ge=1, le=3_600_000)
    requested_deceleration_mps2: float = Field(ge=0.0, le=15.0)
    vehicle_speed_mps: float = Field(ge=0.0, le=100.0)
    expected_version: int = Field(ge=1)
    expected_battery_version: int = Field(ge=1)


class RegenerativeBrakeResponse(BaseModel):
    vehicle_id: str
    vehicle_mass_kg: float
    wheel_radius_m: float
    final_drive_ratio: float
    drivetrain_efficiency_pct: float
    max_regen_torque_nm: float
    max_regen_power_kw: float
    regen_efficiency_pct: float
    max_friction_deceleration_mps2: float
    requested_deceleration_mps2: float
    delivered_deceleration_mps2: float
    vehicle_speed_mps: float
    regenerative_deceleration_mps2: float
    friction_deceleration_mps2: float
    regenerative_motor_torque_nm: float
    recovered_power_kw: float
    recovered_energy_kwh: float
    cumulative_recovered_energy_kwh: float
    battery_charge_acceptance_kw: float
    battery_soc_pct: float
    battery_version: int
    operating_state: BrakeOperatingState
    limiting_reason: str | None
    version: int
    simulation_time_ms: int
    duplicate: bool = False


class ChargingConnectorType(StrEnum):
    AC_TYPE_2 = "ac_type_2"
    DC_CCS = "dc_ccs"


class ChargingAction(StrEnum):
    START = "start"
    CHARGE = "charge"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    INJECT_FAULT = "inject_fault"
    CLEAR_FAULT = "clear_fault"


class ChargingOperatingState(StrEnum):
    IDLE = "idle"
    CHARGING = "charging"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAULTED = "faulted"


class ChargingSystemCreate(BaseModel):
    max_ac_power_kw: float = Field(default=22.0, gt=0.0, le=50.0)
    max_dc_power_kw: float = Field(default=180.0, gt=0.0, le=1_000.0)
    charging_efficiency_pct: float = Field(default=92.0, ge=50.0, le=99.5)


class ChargingCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    command_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    action: ChargingAction
    session_id: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$"
    )
    connector_type: ChargingConnectorType | None = None
    duration_ms: int = Field(default=0, ge=0, le=3_600_000)
    requested_power_kw: float = Field(default=0.0, ge=0.0, le=1_000.0)
    target_soc_pct: float | None = Field(default=None, ge=1.0, le=100.0)
    fault_code: str | None = Field(
        default=None, min_length=1, max_length=32, pattern=r"^[A-Z0-9_:-]+$"
    )
    expected_version: int = Field(ge=1)
    expected_battery_version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_action_fields(self) -> "ChargingCommand":
        if self.action == ChargingAction.START:
            if (
                self.session_id is None
                or self.connector_type is None
                or self.target_soc_pct is None
            ):
                raise ValueError("start requires session_id, connector_type, and target_soc_pct")
        if self.action == ChargingAction.CHARGE and self.duration_ms == 0:
            raise ValueError("charge requires a positive duration_ms")
        if self.action == ChargingAction.INJECT_FAULT and self.fault_code is None:
            raise ValueError("inject_fault requires fault_code")
        return self


class ChargingSystemResponse(BaseModel):
    vehicle_id: str
    max_ac_power_kw: float
    max_dc_power_kw: float
    charging_efficiency_pct: float
    session_id: str | None
    connector_type: ChargingConnectorType | None
    target_soc_pct: float
    requested_power_kw: float
    delivered_power_kw: float
    charged_energy_kwh: float
    session_energy_kwh: float
    battery_charge_acceptance_kw: float
    battery_soc_pct: float
    battery_version: int
    operating_state: ChargingOperatingState
    limiting_reason: str | None
    fault_code: str | None
    version: int
    simulation_time_ms: int
    duplicate: bool = False


class ThermalOperatingState(StrEnum):
    STANDBY = "standby"
    HEATING = "heating"
    COOLING = "cooling"
    MIXED = "mixed"
    FAULTED = "faulted"


class ThermalManagementCreate(BaseModel):
    max_battery_thermal_power_kw: float = Field(default=8.0, gt=0.0, le=50.0)
    max_powertrain_thermal_power_kw: float = Field(default=12.0, gt=0.0, le=100.0)
    max_cabin_thermal_power_kw: float = Field(default=8.0, gt=0.0, le=30.0)
    battery_target_temperature_c: float = Field(default=25.0, ge=5.0, le=40.0)
    motor_target_temperature_c: float = Field(default=70.0, ge=30.0, le=120.0)
    inverter_target_temperature_c: float = Field(default=60.0, ge=30.0, le=90.0)
    cabin_target_temperature_c: float = Field(default=22.0, ge=16.0, le=30.0)
    initial_cabin_temperature_c: float = Field(default=25.0, ge=-40.0, le=80.0)


class ThermalManagementCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    command_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    duration_ms: int = Field(ge=1, le=3_600_000)
    ambient_temperature_c: float = Field(default=25.0, ge=-50.0, le=80.0)
    cabin_heat_load_kw: float = Field(default=0.0, ge=-10.0, le=20.0)
    enabled: bool = True
    fault_code: str | None = Field(
        default=None, min_length=1, max_length=32, pattern=r"^[A-Z0-9_:-]+$"
    )
    expected_version: int = Field(ge=1)
    expected_battery_version: int = Field(ge=1)
    expected_motor_version: int = Field(ge=1)


class ThermalManagementResponse(BaseModel):
    vehicle_id: str
    battery_target_temperature_c: float
    motor_target_temperature_c: float
    inverter_target_temperature_c: float
    cabin_target_temperature_c: float
    battery_temperature_c: float
    motor_temperature_c: float
    inverter_temperature_c: float
    cabin_temperature_c: float
    battery_thermal_power_kw: float
    motor_thermal_power_kw: float
    inverter_thermal_power_kw: float
    cabin_thermal_power_kw: float
    auxiliary_power_kw: float
    battery_version: int
    motor_version: int
    operating_state: ThermalOperatingState
    limiting_reason: str | None
    fault_code: str | None
    version: int
    simulation_time_ms: int
    duplicate: bool = False


class RangeEstimatorCreate(BaseModel):
    vehicle_mass_kg: float = Field(default=2100.0, ge=500.0, le=5000.0)
    drag_coefficient: float = Field(default=0.27, ge=0.15, le=0.7)
    frontal_area_m2: float = Field(default=2.4, ge=1.0, le=5.0)
    rolling_resistance_coefficient: float = Field(default=0.011, ge=0.005, le=0.04)
    drivetrain_efficiency_pct: float = Field(default=92.0, ge=50.0, le=100.0)
    regenerative_efficiency_pct: float = Field(default=70.0, ge=0.0, le=95.0)
    base_auxiliary_power_kw: float = Field(default=0.5, ge=0.0, le=20.0)
    reserve_soc_pct: float = Field(default=5.0, ge=0.0, le=30.0)


class DriveCycleSegment(BaseModel):
    duration_ms: int = Field(ge=1_000, le=3_600_000)
    speed_kph: float = Field(ge=0.0, le=250.0)
    acceleration_mps2: float = Field(default=0.0, ge=-10.0, le=10.0)
    road_grade_pct: float = Field(default=0.0, ge=-20.0, le=20.0)


class RangeEstimationCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    command_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    cycle_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    segments: list[DriveCycleSegment] = Field(min_length=1, max_length=120)
    expected_version: int = Field(ge=1)
    expected_battery_version: int = Field(ge=1)
    expected_thermal_version: int = Field(ge=1)


class RangeEstimatorResponse(BaseModel):
    vehicle_id: str
    cycle_id: str | None
    distance_km: float
    duration_ms: int
    traction_energy_kwh: float
    auxiliary_energy_kwh: float
    recovered_energy_kwh: float
    net_energy_kwh: float
    consumption_kwh_per_100km: float
    available_energy_kwh: float
    estimated_range_km: float
    battery_soc_pct: float
    battery_version: int
    thermal_version: int
    operating_state: str
    limiting_reason: str | None
    version: int
    duplicate: bool = False
