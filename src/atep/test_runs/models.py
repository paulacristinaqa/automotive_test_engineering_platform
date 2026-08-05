from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TestRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "test_runs"
    __table_args__ = (UniqueConstraint("run_id", name="uq_test_runs_run_id"),)

    run_id: Mapped[str] = mapped_column(String(64), index=True)
    vehicle_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), index=True
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    environment_profile_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("environment_profiles.id", ondelete="RESTRICT"),
        index=True,
        default=None,
    )
    environment_profile_version: Mapped[int | None] = mapped_column(Integer, default=None)
    environment_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    name: Mapped[str] = mapped_column(String(160))
    suite: Mapped[str] = mapped_column(String(24), index=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), index=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
