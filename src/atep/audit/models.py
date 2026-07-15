from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, UUIDPrimaryKeyMixin


class AuditRecord(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_records"
    __table_args__ = (
        Index("ix_audit_records_created_at_id", "created_at", "id"),
        Index("ix_audit_records_actor_created_at", "actor_user_id", "created_at"),
        Index("ix_audit_records_resource_created_at", "resource_type", "resource_id", "created_at"),
        Index("ix_audit_records_correlation_id", "correlation_id"),
    )

    actor_user_id: Mapped[UUID | None]
    action: Mapped[str] = mapped_column(String(160), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[UUID]
    outcome: Mapped[str] = mapped_column(String(32), default="success")
    correlation_id: Mapped[UUID | None]
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
