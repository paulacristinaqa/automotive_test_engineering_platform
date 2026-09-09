from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CrossPlatformAutomationReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cross_platform_automation_reports"
    __table_args__ = (
        UniqueConstraint("report_id", name="uq_cross_platform_automation_report_id"),
        UniqueConstraint("test_run_id", name="uq_cross_platform_automation_test_run"),
    )

    report_id: Mapped[str] = mapped_column(String(64), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), index=True
    )
    test_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("test_runs.id", ondelete="RESTRICT"), index=True
    )
    gateway_module_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("platform_modules.id", ondelete="RESTRICT"), index=True
    )
    fault_execution_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fault_campaign_executions.id", ondelete="RESTRICT"),
        index=True,
    )
    mutation_execution_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("mutation_executions.id", ondelete="RESTRICT"),
        index=True,
    )
    telemetry_event_ids: Mapped[list[str]] = mapped_column(JSON)
    vehicle_command_ids: Mapped[list[str]] = mapped_column(JSON)
    carsystemui_observations: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    outcome: Mapped[str] = mapped_column(String(16), index=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
