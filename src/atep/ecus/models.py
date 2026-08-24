from typing import Any
from uuid import UUID

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, String, UniqueConstraint
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
    memory_regions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    faults: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    signals: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    cyclic_tasks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    profile_version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    behavior_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger, default=0)
    boot_count: Mapped[int] = mapped_column(Integer, default=0)
    vehicle: Mapped["Vehicle"] = relationship(back_populates="ecus", lazy="raise")
    simulation_commands: Mapped[list["EcuSimulationCommand"]] = relationship(
        back_populates="ecu", cascade="all, delete-orphan", lazy="raise"
    )
    memory_snapshots: Mapped[list["EcuMemorySnapshot"]] = relationship(
        back_populates="ecu", cascade="all, delete-orphan", lazy="raise"
    )
    owned_signal_routes: Mapped[list["EcuSignalRoute"]] = relationship(
        foreign_keys="EcuSignalRoute.gateway_ecu_id",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class EcuSimulationCommand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ecu_simulation_commands"
    __table_args__ = (UniqueConstraint("ecu_id", "command_id", name="uq_ecu_sim_command"),)

    ecu_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("electronic_control_units.id", ondelete="CASCADE"),
        index=True,
    )
    command_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20), index=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    previous_version: Mapped[int] = mapped_column(Integer)
    state_version: Mapped[int] = mapped_column(Integer)
    previous_time_ms: Mapped[int] = mapped_column(BigInteger)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    ecu: Mapped[ElectronicControlUnit] = relationship(
        back_populates="simulation_commands", lazy="raise"
    )


class EcuMemorySnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ecu_memory_snapshots"

    ecu_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("electronic_control_units.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(80))
    memory: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    state_version: Mapped[int] = mapped_column(Integer)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    ecu: Mapped[ElectronicControlUnit] = relationship(
        back_populates="memory_snapshots", lazy="raise"
    )


class EcuSignalRoute(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ecu_signal_routes"
    __table_args__ = (
        UniqueConstraint("gateway_ecu_id", "identifier", name="uq_ecu_signal_route_identifier"),
    )

    gateway_ecu_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("electronic_control_units.id", ondelete="CASCADE"),
        index=True,
    )
    identifier: Mapped[str] = mapped_column(String(80))
    source_ecu_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("electronic_control_units.id", ondelete="CASCADE"),
        index=True,
    )
    source_signal: Mapped[str] = mapped_column(String(40))
    target_ecu_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("electronic_control_units.id", ondelete="CASCADE"),
        index=True,
    )
    target_signal: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(default=True)


class EcuScenarioExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ecu_scenario_executions"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "execution_id", name="uq_ecu_scenario_execution"),
    )

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), index=True
    )
    execution_id: Mapped[str] = mapped_column(String(40))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    iteration_count: Mapped[int] = mapped_column(Integer)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


from atep.vehicles.models import Vehicle  # noqa: E402
