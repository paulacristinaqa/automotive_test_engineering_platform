from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
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
