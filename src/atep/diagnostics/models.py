from typing import Any
from uuid import UUID

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DiagnosticSessionState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "diagnostic_session_states"
    __table_args__ = (UniqueConstraint("ecu_id", name="uq_diagnostic_session_ecu"),)

    ecu_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("electronic_control_units.id", ondelete="CASCADE"),
        index=True,
    )
    session_type: Mapped[str] = mapped_column(String(24), default="default", index=True)
    security_level: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    simulation_time_ms: Mapped[int] = mapped_column(BigInteger, default=0)


class DiagnosticCommand(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "diagnostic_commands"
    __table_args__ = (
        UniqueConstraint("ecu_id", "command_id", name="uq_diagnostic_command"),
    )

    ecu_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("electronic_control_units.id", ondelete="CASCADE"),
        index=True,
    )
    command_id: Mapped[str] = mapped_column(String(64))
    service_id: Mapped[int] = mapped_column(Integer, index=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    previous_version: Mapped[int] = mapped_column(Integer)
    session_version: Mapped[int] = mapped_column(Integer)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class DiagnosticTroubleCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "diagnostic_trouble_codes"
    __table_args__ = (
        UniqueConstraint("ecu_id", "code", name="uq_diagnostic_trouble_code"),
    )

    ecu_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("electronic_control_units.id", ondelete="CASCADE"),
        index=True,
    )
    code: Mapped[str] = mapped_column(String(6), index=True)
    status_mask: Mapped[int] = mapped_column(Integer, default=0, index=True)
    severity: Mapped[str] = mapped_column(String(16), default="warning", index=True)
    description: Mapped[str] = mapped_column(String(240), default="")
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_ms: Mapped[int] = mapped_column(BigInteger)
    last_seen_ms: Mapped[int] = mapped_column(BigInteger)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
