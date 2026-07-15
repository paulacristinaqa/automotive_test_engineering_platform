from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from atep.events.models import OutboxEvent


def enqueue_event(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    payload: dict[str, Any],
    correlation_id: UUID | None = None,
) -> OutboxEvent:
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        correlation_id=correlation_id,
    )
    session.add(event)
    return event
