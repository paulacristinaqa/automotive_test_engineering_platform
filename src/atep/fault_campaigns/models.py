from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class FaultCampaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fault_campaigns"
    __table_args__ = (UniqueConstraint("campaign_id", name="uq_fault_campaigns_campaign_id"),)

    campaign_id: Mapped[str] = mapped_column(String(64), index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    blast_radius: Mapped[str] = mapped_column(String(20), index=True)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class FaultCampaignExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fault_campaign_executions"
    __table_args__ = (
        UniqueConstraint("execution_id", name="uq_fault_campaign_executions_execution_id"),
    )

    execution_id: Mapped[str] = mapped_column(String(64), index=True)
    campaign_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fault_campaigns.id", ondelete="RESTRICT"), index=True
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
    seed: Mapped[int] = mapped_column(Integer)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), index=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FaultStepResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "fault_step_results"
    __table_args__ = (
        UniqueConstraint("execution_id", "step_id", name="uq_fault_step_results_execution_step"),
    )

    execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fault_campaign_executions.id", ondelete="CASCADE"),
        index=True,
    )
    step_id: Mapped[str] = mapped_column(String(64))
    order: Mapped[int] = mapped_column(Integer)
    domain: Mapped[str] = mapped_column(String(24), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    target_id: Mapped[str] = mapped_column(String(120))
    required: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(16), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    observed_effect: Mapped[str | None] = mapped_column(Text)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
