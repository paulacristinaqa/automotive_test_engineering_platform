from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MutationCampaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mutation_campaigns"
    __table_args__ = (UniqueConstraint("campaign_id", name="uq_mutation_campaigns_campaign_id"),)

    campaign_id: Mapped[str] = mapped_column(String(64), index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    catalog_suite_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("test_suites.id", ondelete="RESTRICT"), index=True
    )
    suite_version: Mapped[int] = mapped_column(Integer)
    suite_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    mutants: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class MutationExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mutation_executions"
    __table_args__ = (UniqueConstraint("execution_id", name="uq_mutation_executions_execution_id"),)

    execution_id: Mapped[str] = mapped_column(String(64), index=True)
    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mutation_campaigns.id", ondelete="RESTRICT"), index=True
    )
    campaign_version: Mapped[int] = mapped_column(Integer)
    campaign_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), index=True
    )
    test_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="RESTRICT"), index=True
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), index=True)
    total_mutants: Mapped[int] = mapped_column(Integer)
    completed_mutants: Mapped[int] = mapped_column(Integer, default=0)
    killed_mutants: Mapped[int] = mapped_column(Integer, default=0)
    survived_mutants: Mapped[int] = mapped_column(Integer, default=0)
    mutation_score: Mapped[float | None] = mapped_column(Float)
    version: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MutantResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mutant_results"
    __table_args__ = (
        UniqueConstraint("execution_id", "mutant_id", name="uq_mutant_results_execution_mutant"),
    )

    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("mutation_executions.id", ondelete="CASCADE"), index=True
    )
    mutant_id: Mapped[str] = mapped_column(String(64))
    order: Mapped[int] = mapped_column(Integer)
    operator: Mapped[str] = mapped_column(String(32), index=True)
    target: Mapped[str] = mapped_column(String(240))
    required: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(16), index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    detected_by: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)


class RequirementCoverage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "requirement_coverage"
    __table_args__ = (
        UniqueConstraint("requirement_id", name="uq_requirement_coverage_requirement_id"),
    )

    requirement_id: Mapped[str] = mapped_column(String(80), index=True)
    managed_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(240))
    criticality: Mapped[str] = mapped_column(String(16), index=True)
    definition_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
