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
