from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Vehicle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"

    identifier: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="registered", index=True)
    telemetry_events: Mapped[list["VehicleTelemetryEvent"]] = relationship(
        back_populates="vehicle",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    commands: Mapped[list["VehicleCommand"]] = relationship(
        back_populates="vehicle",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    digital_state: Mapped["VehicleDigitalState"] = relationship(
        back_populates="vehicle",
        cascade="all, delete-orphan",
        lazy="raise",
        uselist=False,
    )
    simulation_transitions: Mapped[list["VehicleSimulationTransition"]] = relationship(
        back_populates="vehicle", cascade="all, delete-orphan", lazy="raise"
    )
    simulation_steps: Mapped[list["VehicleSimulationStep"]] = relationship(
        back_populates="vehicle", cascade="all, delete-orphan", lazy="raise"
    )


class VehicleDigitalState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_digital_states"

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    operational_mode: Mapped[str] = mapped_column(String(20), default="parked")
    battery_state: Mapped[dict[str, Any]] = mapped_column(JSON)
    powertrain_state: Mapped[dict[str, Any]] = mapped_column(JSON)
    brake_state: Mapped[dict[str, Any]] = mapped_column(JSON)
    steering_state: Mapped[dict[str, Any]] = mapped_column(JSON)
    lighting_state: Mapped[dict[str, Any]] = mapped_column(JSON)
    suspension_state: Mapped[dict[str, Any]] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    vehicle: Mapped[Vehicle] = relationship(back_populates="digital_state", lazy="raise")


class VehicleSimulationTransition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_simulation_transitions"
    __table_args__ = (
        UniqueConstraint(
            "vehicle_id", "command_id", name="uq_vehicle_simulation_transition_command"
        ),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[str] = mapped_column(String(64))
    from_mode: Mapped[str] = mapped_column(String(20))
    to_mode: Mapped[str] = mapped_column(String(20))
    duration_ms: Mapped[int] = mapped_column(Integer)
    requested_speed_kph: Mapped[float | None] = mapped_column()
    previous_state_version: Mapped[int] = mapped_column(Integer)
    state_version: Mapped[int] = mapped_column(Integer)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    vehicle: Mapped[Vehicle] = relationship(back_populates="simulation_transitions", lazy="raise")


class VehicleSimulationStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_simulation_steps"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "command_id", name="uq_vehicle_simulation_step_command"),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[int] = mapped_column(Integer)
    seed: Mapped[int] = mapped_column(Integer)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON)
    sensor_configuration: Mapped[dict[str, Any]] = mapped_column(JSON)
    sensor_readings: Mapped[dict[str, Any]] = mapped_column(JSON)
    previous_state_version: Mapped[int] = mapped_column(Integer)
    state_version: Mapped[int] = mapped_column(Integer)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    vehicle: Mapped[Vehicle] = relationship(back_populates="simulation_steps", lazy="raise")


class VehicleSimulationSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_simulation_sessions"

    name: Mapped[str] = mapped_column(String(120))
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    members: Mapped[list["VehicleSimulationSessionMember"]] = relationship(
        back_populates="simulation_session", cascade="all, delete-orphan", lazy="selectin"
    )
    snapshots: Mapped[list["VehicleSimulationSnapshot"]] = relationship(
        back_populates="simulation_session", cascade="all, delete-orphan", lazy="raise"
    )


class VehicleSimulationSessionMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "vehicle_simulation_session_members"
    __table_args__ = (
        UniqueConstraint("session_id", "vehicle_id", name="uq_simulation_session_vehicle"),
    )

    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vehicle_simulation_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), index=True
    )
    simulation_session: Mapped[VehicleSimulationSession] = relationship(
        back_populates="members", lazy="raise"
    )


class VehicleSimulationSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_simulation_snapshots"
    __table_args__ = (
        UniqueConstraint("session_id", "snapshot_id", name="uq_simulation_session_snapshot"),
    )

    session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("vehicle_simulation_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    snapshot_id: Mapped[str] = mapped_column(String(64))
    states: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    simulation_session: Mapped[VehicleSimulationSession] = relationship(
        back_populates="snapshots", lazy="raise"
    )


class VehicleTelemetryEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "vehicle_telemetry_events"
    __table_args__ = (UniqueConstraint("event_id", name="uq_vehicle_telemetry_events_event_id"),)

    event_id: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    source_module_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("platform_modules.id", ondelete="RESTRICT"), index=True
    )
    source: Mapped[str] = mapped_column(String(80))
    property_name: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[Any] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(40))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    vehicle: Mapped[Vehicle] = relationship(back_populates="telemetry_events", lazy="raise")


class VehicleCommand(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "vehicle_commands"
    __table_args__ = (UniqueConstraint("command_id", name="uq_vehicle_commands_command_id"),)

    command_id: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    target_module_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("platform_modules.id", ondelete="RESTRICT"), index=True
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    test_run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    lease_token_hash: Mapped[str | None] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    vehicle: Mapped[Vehicle] = relationship(back_populates="commands", lazy="raise")
