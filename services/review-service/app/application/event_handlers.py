"""Materialize review cases from completed verification events."""

import asyncio
import json
from uuid import UUID

import aio_pika

from app.config import get_settings
from app.infrastructure.db import SessionFactory
from app.infrastructure.internal_clients import VerificationClient
from app.infrastructure.models import ReviewCase, ReviewInbox


async def handle(envelope: dict) -> None:
    event_id, event_type = UUID(envelope["event_id"]), envelope["event_type"]
    async with SessionFactory() as session:
        if await session.get(ReviewInbox, event_id):
            return
        run_id = envelope["data"].get("run_id", envelope["aggregate_id"])
        if event_type in {
            "verification.completed.v1",
            "verification.duplicate_suspected.v1",
        }:
            package = await VerificationClient(get_settings()).review_package(run_id)
            if package["assessment"]["review_required"]:
                existing = await session.get(ReviewCase, UUID(run_id))
                if not existing:
                    session.add(
                        ReviewCase(
                            id=UUID(run_id),
                            verification_id=UUID(package["verification_id"]),
                            verification_run_id=UUID(run_id),
                            claim_source=package["claim_source"],
                            claim_id=package["claim_id"],
                            owner_org=UUID(package["owner_org"]),
                            review_package_json=package,
                        )
                    )
        elif event_type == "verification.stale.v1":
            row = await session.get(ReviewCase, UUID(run_id))
            if row:
                row.is_stale = True
        session.add(ReviewInbox(event_id=event_id, event_type=event_type))
        await session.commit()


async def consume_forever() -> None:
    connection = await aio_pika.connect_robust(get_settings().rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=20)
        queue = await channel.get_queue("review.verification-events.q", ensure=False)

        async def on_message(message: aio_pika.IncomingMessage) -> None:
            try:
                await handle(json.loads(message.body))
            except (json.JSONDecodeError, KeyError, ValueError):
                await message.reject(requeue=False)
            except Exception:
                await asyncio.sleep(0.25)
                await message.nack(requeue=True)
            else:
                await message.ack()

        await queue.consume(on_message)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(consume_forever())
