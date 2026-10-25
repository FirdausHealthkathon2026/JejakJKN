"""Build Evidence care episodes from durable Encounter events."""

import asyncio
import json
from datetime import datetime
from uuid import UUID

import aio_pika
from sqlalchemy.exc import SQLAlchemyError

from app.application.use_cases import EvidenceApplication
from app.config import get_settings
from app.infrastructure.db import SessionFactory
from app.infrastructure.models import CareEpisode, EvidenceInbox


async def handle(envelope: dict) -> None:
    event_id = UUID(envelope["event_id"])
    event_type = envelope["event_type"]
    data = envelope["data"]
    encounter_id = UUID(envelope["aggregate_id"])
    async with SessionFactory() as session:
        if await session.get(EvidenceInbox, event_id):
            return
        episode = await session.get(CareEpisode, encounter_id, with_for_update=True)
        if event_type == "encounter.opened.v1":
            if episode is None:
                episode = CareEpisode(
                    encounter_id=encounter_id, organization_id=UUID(envelope["organization_id"]),
                    patient_id=UUID(data["patient_id"]), encounter_status="OPEN",
                    presence_status=data.get("presence_status", "QR_VERIFIED"),
                )
                session.add(episode)
        elif event_type == "encounter.checked_out.v1":
            if episode is None:
                raise RuntimeError("encounter.opened.v1 has not arrived")
            episode.encounter_status = "CHECKED_OUT"
            episode.checked_out_at = datetime.fromisoformat(data["checked_out_at"])
            await EvidenceApplication(session, get_settings())._build_snapshot(episode)
        elif event_type == "encounter.exception_recorded.v1":
            if episode is None:
                episode = CareEpisode(
                    encounter_id=encounter_id, organization_id=UUID(envelope["organization_id"]),
                    patient_id=UUID(data["patient_id"]), encounter_status=data["encounter_status"],
                    presence_status="EXCEPTION_DOCUMENTED",
                )
                session.add(episode)
            else:
                episode.encounter_status = data["encounter_status"]
                episode.presence_status = "EXCEPTION_DOCUMENTED"
            if data.get("checked_out_at"):
                episode.checked_out_at = datetime.fromisoformat(data["checked_out_at"])
                await session.flush()
                await EvidenceApplication(session, get_settings())._build_snapshot(episode)
        session.add(EvidenceInbox(event_id=event_id, event_type=event_type))
        await session.commit()


async def consume_forever() -> None:
    connection = await aio_pika.connect_robust(get_settings().rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=20)
        queue = await channel.get_queue("evidence.encounter-events.q", ensure=False)

        async def on_message(message: aio_pika.IncomingMessage) -> None:
            try:
                envelope = json.loads(message.body)
                await handle(envelope)
            except (json.JSONDecodeError, KeyError, ValueError):
                await message.reject(requeue=False)
            except (SQLAlchemyError, RuntimeError):
                await asyncio.sleep(0.25)
                await message.nack(requeue=True)
            else:
                await message.ack()

        await queue.consume(on_message)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(consume_forever())
