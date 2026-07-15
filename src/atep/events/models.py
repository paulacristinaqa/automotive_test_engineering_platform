from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from atep.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OutboxEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(String(180), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80))
    aggregate_id: Mapped[UUID]
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    correlation_id: Mapped[UUID | None]
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
