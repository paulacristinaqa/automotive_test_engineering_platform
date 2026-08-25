from typing import Any
from uuid import UUID

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CanNetwork(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "can_networks"

    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), unique=True, index=True
    )
    identifier: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(120))
    bitrate_kbps: Mapped[int] = mapped_column(Integer)
    can_fd_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    data_bitrate_kbps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nodes: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    frame_contracts: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    error_states: Mapped[dict[str, dict[str, Any]]] = mapped_column(JSON, default=dict)
    lin_channels: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    ethernet_segments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    gateway_routes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    simulation_time_us: Mapped[int] = mapped_column(BigInteger, default=0)
    next_sequence: Mapped[int] = mapped_column(BigInteger, default=1)


class CanFrameTransmission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "can_frame_transmissions"
    __table_args__ = (
        UniqueConstraint("network_id", "command_id", name="uq_can_frame_transmission_command"),
    )

    network_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("can_networks.id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[str] = mapped_column(String(64))
    contract_id: Mapped[str] = mapped_column(String(80), index=True)
    producer_node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    frame_id: Mapped[int] = mapped_column(Integer)
    frame_format: Mapped[str] = mapped_column(String(20))
    protocol: Mapped[str] = mapped_column(String(16), default="classic")
    bitrate_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload: Mapped[list[int]] = mapped_column(JSON)
    sequence: Mapped[int] = mapped_column(BigInteger)
    transmission_time_us: Mapped[int] = mapped_column(BigInteger)
    previous_version: Mapped[int] = mapped_column(Integer)
    network_version: Mapped[int] = mapped_column(Integer)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class CanFaultExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "can_fault_executions"
    __table_args__ = (UniqueConstraint("network_id", "command_id", name="uq_can_fault_command"),)

    network_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("can_networks.id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(16))
    target_node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    previous_version: Mapped[int] = mapped_column(Integer)
    network_version: Mapped[int] = mapped_column(Integer)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class MultiBusGatewayExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "multibus_gateway_executions"
    __table_args__ = (
        UniqueConstraint("network_id", "command_id", name="uq_multibus_gateway_command"),
    )

    network_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("can_networks.id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(16))
    route_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    previous_version: Mapped[int] = mapped_column(Integer)
    network_version: Mapped[int] = mapped_column(Integer)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class CanArbitrationExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "can_arbitration_executions"
    __table_args__ = (
        UniqueConstraint("network_id", "command_id", name="uq_can_arbitration_command"),
    )

    network_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("can_networks.id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    contender_count: Mapped[int] = mapped_column(Integer)
    previous_version: Mapped[int] = mapped_column(Integer)
    network_version: Mapped[int] = mapped_column(Integer)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class CanDbcCatalogue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "can_dbc_catalogues"

    network_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("can_networks.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    identifier: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(120))
    revision: Mapped[str] = mapped_column(String(40))
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    network_version: Mapped[int] = mapped_column(Integer)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class CanSignalCodecExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "can_signal_codec_executions"
    __table_args__ = (
        UniqueConstraint("network_id", "command_id", name="uq_can_signal_codec_command"),
    )

    network_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("can_networks.id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(16))
    contract_id: Mapped[str] = mapped_column(String(80), index=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
