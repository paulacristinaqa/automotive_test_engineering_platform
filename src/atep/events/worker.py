import asyncio
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import aio_pika
import structlog
from aio_pika import DeliveryMode, ExchangeType, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from atep.core.config import get_settings
from atep.core.logging import configure_logging
from atep.db.session import session_factory
from atep.events.models import OutboxEvent
from atep.events.observability import OutboxObservability

log = structlog.get_logger()


@dataclass(frozen=True)
class OutboxBacklog:
    count: int
    oldest_age_seconds: float


async def measure_outbox_backlog(
    session: AsyncSession, *, now: datetime | None = None
) -> OutboxBacklog:
    observed_at = now or datetime.now(UTC)
    result = await session.execute(
        select(func.count(), func.min(OutboxEvent.created_at)).where(
            OutboxEvent.published_at.is_(None)
        )
    )
    count, oldest_created_at = result.one()
    oldest_age = (
        max(0.0, (observed_at - oldest_created_at).total_seconds())
        if oldest_created_at is not None
        else 0.0
    )
    return OutboxBacklog(count=int(count), oldest_age_seconds=oldest_age)


async def publish_batch(
    exchange: aio_pika.abc.AbstractExchange, observability: OutboxObservability
) -> int:
    started_at = time.perf_counter()
    async with session_factory() as session, session.begin():
        backlog = await measure_outbox_backlog(session)
        observability.update_backlog(
            count=backlog.count, oldest_age_seconds=backlog.oldest_age_seconds
        )
        result = await session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        )
        events = result.scalars().all()
        for event in events:
            envelope = {
                "event_id": str(event.id),
                "event_type": event.event_type,
                "occurred_at": event.created_at.isoformat(),
                "aggregate": {
                    "type": event.aggregate_type,
                    "id": str(event.aggregate_id),
                },
                "correlation_id": str(event.correlation_id) if event.correlation_id else None,
                "payload": event.payload,
            }
            try:
                await exchange.publish(
                    Message(
                        json.dumps(envelope).encode(),
                        content_type="application/json",
                        delivery_mode=DeliveryMode.PERSISTENT,
                        message_id=str(event.id),
                        correlation_id=(
                            str(event.correlation_id) if event.correlation_id else None
                        ),
                    ),
                    routing_key=event.event_type,
                )
            except Exception:
                observability.publication_attempts.labels("error").inc()
                raise
            observability.publication_attempts.labels("success").inc()
            event.published_at = datetime.now(UTC)
            event.attempts += 1
        observability.batch_duration.observe(time.perf_counter() - started_at)
        return len(events)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    observability = OutboxObservability()
    if settings.metrics_enabled:
        observability.start_server(settings.outbox_metrics_port)
    connection = await aio_pika.connect_robust(settings.rabbitmq_url, fail_fast=False)
    async with connection:
        channel = await connection.channel(publisher_confirms=True)
        exchange = await channel.declare_exchange("atep.events", ExchangeType.TOPIC, durable=True)
        observability.worker_up.set(1)
        log.info("outbox_worker_started")
        while True:
            try:
                published = await publish_batch(exchange, observability)
            except asyncio.CancelledError:
                raise
            except Exception:
                observability.worker_up.set(0)
                log.exception("outbox_publication_batch_failed")
                await asyncio.sleep(settings.outbox_retry_seconds)
                continue
            observability.worker_up.set(1)
            if published == 0:
                await asyncio.sleep(settings.outbox_retry_seconds)


if __name__ == "__main__":
    asyncio.run(run())
