import asyncio
import json
from datetime import UTC, datetime

import aio_pika
import structlog
from aio_pika import DeliveryMode, ExchangeType, Message
from sqlalchemy import select

from atep.core.config import get_settings
from atep.core.logging import configure_logging
from atep.db.session import session_factory
from atep.events.models import OutboxEvent

log = structlog.get_logger()


async def publish_batch(exchange: aio_pika.abc.AbstractExchange) -> int:
    async with session_factory() as session, session.begin():
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
            await exchange.publish(
                Message(
                    json.dumps(envelope).encode(),
                    content_type="application/json",
                    delivery_mode=DeliveryMode.PERSISTENT,
                    message_id=str(event.id),
                    correlation_id=(str(event.correlation_id) if event.correlation_id else None),
                ),
                routing_key=event.event_type,
            )
            event.published_at = datetime.now(UTC)
            event.attempts += 1
        return len(events)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    connection = await aio_pika.connect_robust(settings.rabbitmq_url, fail_fast=False)
    async with connection:
        channel = await connection.channel(publisher_confirms=True)
        exchange = await channel.declare_exchange("atep.events", ExchangeType.TOPIC, durable=True)
        log.info("outbox_worker_started")
        while True:
            published = await publish_batch(exchange)
            if published == 0:
                await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run())
