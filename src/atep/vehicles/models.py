from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
    version: Mapped[int] = mapped_column(Integer, default=1)
    vehicle: Mapped[Vehicle] = relationship(back_populates="digital_state", lazy="raise")


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
