from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ElectronicControlUnit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "electronic_control_units"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "identifier", name="uq_ecu_vehicle_identifier"),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    identifier: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(120))
    ecu_type: Mapped[str] = mapped_column(String(30), index=True)
    operational_state: Mapped[str] = mapped_column(String(20), default="offline", index=True)
    memory: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    faults: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    vehicle: Mapped["Vehicle"] = relationship(back_populates="ecus", lazy="raise")


from atep.vehicles.models import Vehicle  # noqa: E402
