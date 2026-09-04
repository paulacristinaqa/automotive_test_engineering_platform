from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BatteryPackState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "battery_pack_states"
    __table_args__ = (
        UniqueConstraint("vehicle_id", name="uq_battery_pack_vehicle"),
        CheckConstraint(
            "series_cell_count >= 4 AND series_cell_count <= 192", name="ck_battery_pack_cells"
        ),
        CheckConstraint("nominal_capacity_ah > 0", name="ck_battery_pack_capacity"),
        CheckConstraint("soc_pct >= 0 AND soc_pct <= 100", name="ck_battery_pack_soc"),
        CheckConstraint("soh_pct >= 0 AND soh_pct <= 100", name="ck_battery_pack_soh"),
        CheckConstraint("version >= 1", name="ck_battery_pack_version"),
        CheckConstraint("contactor_state IN ('open', 'closed')", name="ck_battery_pack_contactor"),
        CheckConstraint(
            "operating_state IN ('normal', 'warning', 'protection')",
            name="ck_battery_pack_operating_state",
        ),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    chemistry: Mapped[str] = mapped_column(String(16), index=True)
    series_cell_count: Mapped[int] = mapped_column(Integer)
    nominal_capacity_ah: Mapped[float] = mapped_column(Float)
    nominal_cell_voltage_v: Mapped[float] = mapped_column(Float)
    internal_resistance_ohm: Mapped[float] = mapped_column(Float)
    soc_pct: Mapped[float] = mapped_column(Float)
    soh_pct: Mapped[float] = mapped_column(Float)
    pack_voltage_v: Mapped[float] = mapped_column(Float)
    pack_current_a: Mapped[float] = mapped_column(Float, default=0.0)
    pack_temperature_c: Mapped[float] = mapped_column(Float)
    contactor_state: Mapped[str] = mapped_column(String(16), index=True)
    operating_state: Mapped[str] = mapped_column(String(16), index=True)
    cells: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger, default=0)


class BatterySimulationStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "battery_simulation_steps"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "command_id", name="uq_battery_step_command"),
        CheckConstraint(
            "duration_ms >= 1 AND duration_ms <= 3600000", name="ck_battery_step_duration"
        ),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[int] = mapped_column(Integer)
    requested_current_a: Mapped[float] = mapped_column(Float)
    ambient_temperature_c: Mapped[float] = mapped_column(Float)
    previous_version: Mapped[int] = mapped_column(Integer)
    state_version: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class MotorInverterState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "motor_inverter_states"
    __table_args__ = (
        UniqueConstraint("vehicle_id", name="uq_motor_inverter_vehicle"),
        CheckConstraint("max_torque_nm > 0", name="ck_motor_inverter_torque"),
        CheckConstraint("max_speed_rpm > 0", name="ck_motor_inverter_speed"),
        CheckConstraint("max_inverter_power_kw > 0", name="ck_motor_inverter_power"),
        CheckConstraint(
            "base_efficiency_pct >= 50 AND base_efficiency_pct <= 100",
            name="ck_motor_inverter_efficiency",
        ),
        CheckConstraint("version >= 1", name="ck_motor_inverter_version"),
        CheckConstraint(
            "operating_state IN ('standby', 'ready', 'derated', 'protection')",
            name="ck_motor_inverter_operating_state",
        ),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    max_torque_nm: Mapped[float] = mapped_column(Float)
    max_speed_rpm: Mapped[int] = mapped_column(Integer)
    max_inverter_power_kw: Mapped[float] = mapped_column(Float)
    base_efficiency_pct: Mapped[float] = mapped_column(Float)
    requested_torque_nm: Mapped[float] = mapped_column(Float, default=0.0)
    delivered_torque_nm: Mapped[float] = mapped_column(Float, default=0.0)
    motor_speed_rpm: Mapped[int] = mapped_column(Integer, default=0)
    mechanical_power_kw: Mapped[float] = mapped_column(Float, default=0.0)
    electrical_power_kw: Mapped[float] = mapped_column(Float, default=0.0)
    efficiency_pct: Mapped[float] = mapped_column(Float)
    power_loss_kw: Mapped[float] = mapped_column(Float, default=0.0)
    motor_temperature_c: Mapped[float] = mapped_column(Float)
    inverter_temperature_c: Mapped[float] = mapped_column(Float)
    drive_mode: Mapped[str] = mapped_column(String(16), default="normal")
    operating_state: Mapped[str] = mapped_column(String(16), index=True)
    limiting_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger, default=0)


class MotorSimulationStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "motor_simulation_steps"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "command_id", name="uq_motor_step_command"),
        CheckConstraint(
            "duration_ms >= 1 AND duration_ms <= 3600000", name="ck_motor_step_duration"
        ),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[int] = mapped_column(Integer)
    requested_torque_nm: Mapped[float] = mapped_column(Float)
    motor_speed_rpm: Mapped[int] = mapped_column(Integer)
    drive_mode: Mapped[str] = mapped_column(String(16))
    ambient_temperature_c: Mapped[float] = mapped_column(Float)
    previous_version: Mapped[int] = mapped_column(Integer)
    state_version: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class RegenerativeBrakeState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "regenerative_brake_states"
    __table_args__ = (
        UniqueConstraint("vehicle_id", name="uq_regenerative_brake_vehicle"),
        CheckConstraint("vehicle_mass_kg > 0", name="ck_regenerative_brake_mass"),
        CheckConstraint("wheel_radius_m > 0", name="ck_regenerative_brake_wheel_radius"),
        CheckConstraint("final_drive_ratio > 0", name="ck_regenerative_brake_drive_ratio"),
        CheckConstraint(
            "drivetrain_efficiency_pct > 0 AND drivetrain_efficiency_pct <= 100",
            name="ck_regenerative_brake_drivetrain_efficiency",
        ),
        CheckConstraint("max_regen_torque_nm > 0", name="ck_regenerative_brake_torque"),
        CheckConstraint("max_regen_power_kw > 0", name="ck_regenerative_brake_power"),
        CheckConstraint(
            "regen_efficiency_pct > 0 AND regen_efficiency_pct <= 100",
            name="ck_regenerative_brake_efficiency",
        ),
        CheckConstraint(
            "max_friction_deceleration_mps2 > 0",
            name="ck_regenerative_brake_friction",
        ),
        CheckConstraint("version >= 1", name="ck_regenerative_brake_version"),
        CheckConstraint(
            "operating_state IN ('standby', 'regenerative', 'blended', 'friction', 'limited')",
            name="ck_regenerative_brake_operating_state",
        ),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    vehicle_mass_kg: Mapped[float] = mapped_column(Float)
    wheel_radius_m: Mapped[float] = mapped_column(Float)
    final_drive_ratio: Mapped[float] = mapped_column(Float)
    drivetrain_efficiency_pct: Mapped[float] = mapped_column(Float)
    max_regen_torque_nm: Mapped[float] = mapped_column(Float)
    max_regen_power_kw: Mapped[float] = mapped_column(Float)
    regen_efficiency_pct: Mapped[float] = mapped_column(Float)
    max_friction_deceleration_mps2: Mapped[float] = mapped_column(Float)
    requested_deceleration_mps2: Mapped[float] = mapped_column(Float, default=0.0)
    delivered_deceleration_mps2: Mapped[float] = mapped_column(Float, default=0.0)
    vehicle_speed_mps: Mapped[float] = mapped_column(Float, default=0.0)
    regenerative_deceleration_mps2: Mapped[float] = mapped_column(Float, default=0.0)
    friction_deceleration_mps2: Mapped[float] = mapped_column(Float, default=0.0)
    regenerative_motor_torque_nm: Mapped[float] = mapped_column(Float, default=0.0)
    recovered_power_kw: Mapped[float] = mapped_column(Float, default=0.0)
    recovered_energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    cumulative_recovered_energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    battery_charge_acceptance_kw: Mapped[float] = mapped_column(Float, default=0.0)
    operating_state: Mapped[str] = mapped_column(String(16), index=True)
    limiting_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger, default=0)


class BrakeSimulationStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "brake_simulation_steps"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "command_id", name="uq_brake_step_command"),
        CheckConstraint(
            "duration_ms >= 1 AND duration_ms <= 3600000", name="ck_brake_step_duration"
        ),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[int] = mapped_column(Integer)
    requested_deceleration_mps2: Mapped[float] = mapped_column(Float)
    vehicle_speed_mps: Mapped[float] = mapped_column(Float)
    previous_version: Mapped[int] = mapped_column(Integer)
    state_version: Mapped[int] = mapped_column(Integer)
    previous_battery_version: Mapped[int] = mapped_column(Integer)
    battery_state_version: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class ChargingSystemState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "charging_system_states"
    __table_args__ = (
        UniqueConstraint("vehicle_id", name="uq_charging_system_vehicle"),
        CheckConstraint("max_ac_power_kw > 0", name="ck_charging_system_ac_power"),
        CheckConstraint("max_dc_power_kw > 0", name="ck_charging_system_dc_power"),
        CheckConstraint(
            "charging_efficiency_pct > 0 AND charging_efficiency_pct <= 100",
            name="ck_charging_system_efficiency",
        ),
        CheckConstraint(
            "target_soc_pct >= 1 AND target_soc_pct <= 100", name="ck_charging_target_soc"
        ),
        CheckConstraint("version >= 1", name="ck_charging_system_version"),
        CheckConstraint(
            "operating_state IN ('idle', 'charging', 'paused', 'completed', 'faulted')",
            name="ck_charging_system_operating_state",
        ),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    max_ac_power_kw: Mapped[float] = mapped_column(Float)
    max_dc_power_kw: Mapped[float] = mapped_column(Float)
    charging_efficiency_pct: Mapped[float] = mapped_column(Float)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connector_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_soc_pct: Mapped[float] = mapped_column(Float, default=80.0)
    requested_power_kw: Mapped[float] = mapped_column(Float, default=0.0)
    delivered_power_kw: Mapped[float] = mapped_column(Float, default=0.0)
    charged_energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    session_energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    battery_charge_acceptance_kw: Mapped[float] = mapped_column(Float, default=0.0)
    operating_state: Mapped[str] = mapped_column(String(16), index=True)
    limiting_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fault_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger, default=0)


class ChargingCommandStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "charging_command_steps"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "command_id", name="uq_charging_step_command"),
        CheckConstraint(
            "duration_ms >= 0 AND duration_ms <= 3600000", name="ck_charging_step_duration"
        ),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(16))
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connector_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    requested_power_kw: Mapped[float] = mapped_column(Float)
    target_soc_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    fault_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    previous_version: Mapped[int] = mapped_column(Integer)
    state_version: Mapped[int] = mapped_column(Integer)
    previous_battery_version: Mapped[int] = mapped_column(Integer)
    battery_state_version: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
