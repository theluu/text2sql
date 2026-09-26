"""Per-user notifications (review outcomes) over Redis pub/sub, in-process fallback."""

import asyncio
import json
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis
import structlog

log = structlog.get_logger()


def channel(user_id: uuid.UUID | str) -> str:
    return f"notify:{user_id}"


class Notifier:
    def __init__(self, client: "aioredis.Redis | None") -> None:
        self._redis = client
        self._local: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    async def publish(self, user_id: uuid.UUID | str, event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False, default=str)
        if self._redis is not None:
            try:
                await self._redis.publish(channel(user_id), payload)
                return
            except Exception as error:
                log.warning("notify.redis_failed", error=str(error))
        for queue in list(self._local[channel(user_id)]):
            queue.put_nowait(json.loads(payload))

    async def subscribe(
        self, user_id: uuid.UUID | str, heartbeat_s: float = 15.0
    ) -> AsyncIterator[dict[str, Any] | None]:
        """Yields events; yields None as a heartbeat so the HTTP stream stays alive."""
        if self._redis is not None:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(channel(user_id))
            try:
                while True:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=heartbeat_s
                    )
                    if message is None:
                        yield None
                    else:
                        yield json.loads(message["data"])
            finally:
                await pubsub.unsubscribe(channel(user_id))
                await pubsub.aclose()  # type: ignore[no-untyped-call]
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._local[channel(user_id)].add(queue)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=heartbeat_s)
                except TimeoutError:
                    yield None
        finally:
            self._local[channel(user_id)].discard(queue)
