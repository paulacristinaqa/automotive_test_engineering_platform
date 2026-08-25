from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
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
    __table_args__ = (UniqueConstraint("ecu_id", "command_id", name="uq_diagnostic_command"),)

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


class DiagnosticDataIdentifier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "diagnostic_data_identifiers"
    __table_args__ = (
        UniqueConstraint("ecu_id", "identifier", name="uq_diagnostic_data_identifier"),
        CheckConstraint(
            "identifier >= 0 AND identifier <= 65535", name="ck_diagnostic_did_identifier"
        ),
        CheckConstraint(
            "data_type IN ('boolean', 'integer', 'decimal', 'string')",
            name="ck_diagnostic_did_data_type",
        ),
        CheckConstraint("version >= 1", name="ck_diagnostic_did_version"),
        CheckConstraint(
            "max_length IS NULL OR max_length >= 1", name="ck_diagnostic_did_max_length"
        ),
        CheckConstraint(
            "minimum IS NULL OR maximum IS NULL OR minimum <= maximum",
            name="ck_diagnostic_did_numeric_range",
        ),
    )

    ecu_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("electronic_control_units.id", ondelete="CASCADE"),
        index=True,
    )
    identifier: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(240), default="")
    data_type: Mapped[str] = mapped_column(String(16), index=True)
    unit: Mapped[str] = mapped_column(String(32), default="")
    writable: Mapped[bool] = mapped_column(Boolean, default=False)
    readable_sessions: Mapped[list[str]] = mapped_column(JSON)
    writable_sessions: Mapped[list[str]] = mapped_column(JSON)
    value: Mapped[bool | int | float | str] = mapped_column(JSON)
    minimum: Mapped[float | None] = mapped_column(Float, nullable=True)
    maximum: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class DiagnosticRoutine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "diagnostic_routines"
    __table_args__ = (
        UniqueConstraint("ecu_id", "identifier", name="uq_diagnostic_routine_identifier"),
        CheckConstraint(
            "identifier >= 0 AND identifier <= 65535", name="ck_diagnostic_routine_identifier"
        ),
        CheckConstraint(
            "execution_time_ms >= 0 AND execution_time_ms <= 600000",
            name="ck_diagnostic_routine_execution_time",
        ),
        CheckConstraint("version >= 1", name="ck_diagnostic_routine_version"),
    )

    ecu_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("electronic_control_units.id", ondelete="CASCADE"),
        index=True,
    )
    identifier: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(240), default="")
    allowed_sessions: Mapped[list[str]] = mapped_column(JSON)
    execution_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    supports_stop: Mapped[bool] = mapped_column(Boolean, default=False)
    result_template: Mapped[dict[str, bool | int | float | str]] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class DiagnosticRoutineState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "diagnostic_routine_states"
    __table_args__ = (
        UniqueConstraint("routine_id", name="uq_diagnostic_routine_state"),
        CheckConstraint(
            "status IN ('idle', 'running', 'completed', 'stopped')",
            name="ck_diagnostic_routine_state_status",
        ),
        CheckConstraint("invocation_count >= 0", name="ck_diagnostic_routine_invocations"),
        CheckConstraint("version >= 1", name="ck_diagnostic_routine_state_version"),
    )

    routine_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("diagnostic_routines.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), default="idle", index=True)
    invocation_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    completes_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    stopped_at_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    input_parameters: Mapped[dict[str, bool | int | float | str]] = mapped_column(
        JSON, default=dict
    )
    result: Mapped[dict[str, bool | int | float | str]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)


class DiagnosticTroubleCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "diagnostic_trouble_codes"
    __table_args__ = (UniqueConstraint("ecu_id", "code", name="uq_diagnostic_trouble_code"),)

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
