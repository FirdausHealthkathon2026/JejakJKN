"""RabbitMQ consumer entrypoint."""

import asyncio
import json
import os

import aio_pika

from app.application.handler import handle


async def consume_forever() -> None:
    connection = await aio_pika.connect_robust(
        os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
    )
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)
        queue = await channel.get_queue("narrative.verification-events.q", ensure=False)

        async def on_message(message: aio_pika.IncomingMessage) -> None:
            try:
                await handle(json.loads(message.body))
            except (json.JSONDecodeError, KeyError, ValueError):
                await message.reject(requeue=False)
            except Exception:
                await asyncio.sleep(0.5)
                await message.nack(requeue=True)
            else:
                await message.ack()

        await queue.consume(on_message)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(consume_forever())
