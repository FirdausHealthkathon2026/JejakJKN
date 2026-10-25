"""Publish committed Evidence outbox rows to RabbitMQ."""

import asyncio
import json
from datetime import UTC, datetime

import aio_pika
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.infrastructure.db import SessionFactory
from app.infrastructure.models import EvidenceOutbox


async def publish_forever() -> None:
    connection = await aio_pika.connect_robust(get_settings().rabbitmq_url)
    async with connection:
        channel = await connection.channel(publisher_confirms=True)
        exchange = await channel.get_exchange("jejakjkn.domain.v1", ensure=False)
        while True:
            rows = []
            try:
                async with SessionFactory() as session:
                    rows = list((await session.scalars(select(EvidenceOutbox).where(EvidenceOutbox.published_at.is_(None)).order_by(EvidenceOutbox.created_at).limit(50).with_for_update(skip_locked=True))).all())
                    for row in rows:
                        published_at = datetime.now(UTC)
                        envelope = {
                            "event_id": str(row.event_id), "event_type": row.event_type, "schema_version": "1.0", "producer": "evidence-service",
                            "organization_id": row.organization_id, "aggregate_id": row.aggregate_id, "aggregate_revision": row.aggregate_revision,
                            "occurred_at": row.occurred_at.isoformat(), "published_at": published_at.isoformat(), "correlation_id": row.correlation_id,
                            "causation_id": row.causation_id, "data": row.payload,
                        }
                        await exchange.publish(aio_pika.Message(json.dumps(envelope).encode(), content_type="application/json", delivery_mode=aio_pika.DeliveryMode.PERSISTENT, message_id=str(row.event_id)), routing_key=row.event_type)
                        row.published_at = published_at
                    await session.commit()
            except SQLAlchemyError:
                await asyncio.sleep(2)
                continue
            await asyncio.sleep(0.25 if rows else 1)


if __name__ == "__main__":
    asyncio.run(publish_forever())
