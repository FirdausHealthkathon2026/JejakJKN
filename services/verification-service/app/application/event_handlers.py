"""Invalidate completed assessments when their dependencies change."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import aio_pika
from sqlalchemy import select

from app.config import get_settings
from app.infrastructure.db import SessionFactory
from app.infrastructure.models import (
    CandidateEvaluation,
    VerificationInbox,
    VerificationOutbox,
    VerificationRequest,
    VerificationRun,
)


async def handle(envelope: dict) -> None:
    event_id, event_type = UUID(envelope["event_id"]), envelope["event_type"]
    async with SessionFactory() as session:
        if await session.get(VerificationInbox, event_id):
            return
        if (
            event_type.startswith("evidence.")
            or event_type == "patient.confirmation_recorded.v1"
        ):
            encounter_id = UUID(envelope["aggregate_id"])
            rows = await session.execute(
                select(VerificationRun, VerificationRequest)
                .join(
                    CandidateEvaluation,
                    CandidateEvaluation.run_id == VerificationRun.id,
                )
                .join(
                    VerificationRequest,
                    VerificationRequest.id == VerificationRun.request_id,
                )
                .where(
                    CandidateEvaluation.encounter_id == encounter_id,
                    VerificationRun.status == "COMPLETED",
                    VerificationRun.data_freshness == "CURRENT",
                )
            )
            for run, request in rows.tuples():
                run.data_freshness = "STALE_INPUT"
                session.add(
                    VerificationOutbox(
                        event_id=uuid4(),
                        event_type="verification.stale.v1",
                        aggregate_id=str(run.id),
                        aggregate_revision=run.run_number,
                        organization_id=str(request.verifier_org_id),
                        correlation_id=str(request.id),
                        causation_id=str(event_id),
                        payload={
                            "verification_id": str(request.id),
                            "run_id": str(run.id),
                            "trigger_event_type": event_type,
                            "encounter_id": str(encounter_id),
                        },
                        occurred_at=datetime.now(UTC),
                    )
                )
        session.add(VerificationInbox(event_id=event_id, event_type=event_type))
        await session.commit()


async def consume_forever() -> None:
    connection = await aio_pika.connect_robust(get_settings().rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=20)
        queue = await channel.get_queue("verification.domain-events.q", ensure=False)

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
