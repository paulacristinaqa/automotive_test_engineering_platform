from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PerformanceProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "performance_profiles"
    __table_args__ = (UniqueConstraint("profile_id", name="uq_performance_profiles_profile_id"),)

    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    workload_type: Mapped[str] = mapped_column(String(16), index=True)
    target: Mapped[str] = mapped_column(String(200))
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    thresholds: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    resource_limits: Mapped[dict[str, Any]] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)


class PerformanceExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "performance_executions"
    __table_args__ = (
        UniqueConstraint("execution_id", name="uq_performance_executions_execution_id"),
    )

    execution_id: Mapped[str] = mapped_column(String(64), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    profile_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("performance_profiles.id", ondelete="RESTRICT"), index=True
    )
    profile_version: Mapped[int] = mapped_column(Integer)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    test_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="RESTRICT"), index=True
    )
    baseline_execution_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("performance_executions.id", ondelete="RESTRICT"),
        index=True,
    )
    recorded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    sample_count: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[float] = mapped_column(Float)
    metrics: Mapped[dict[str, float]] = mapped_column(JSON)
    threshold_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    comparison: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON)
    outcome: Mapped[str] = mapped_column(String(16), index=True)
