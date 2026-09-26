"""Result cache (Redis, in-memory fallback). Key = question, schema version, role, prompt version."""

import hashlib
import json
import time
from typing import Any

import redis.asyncio as aioredis
import structlog

from app.core.text import normalize

log = structlog.get_logger()
TTL_S = 3600


def cache_key(question: str, schema_version: str, role: str, prompt_version: str) -> str:
    raw = "|".join([normalize(question), schema_version, role, prompt_version])
    return "qcache:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


class ResultCache:
    def __init__(self, client: "aioredis.Redis | None") -> None:
        self._redis = client
        self._memory: dict[str, tuple[float, str]] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        try:
            raw = await self._redis.get(key) if self._redis else self._memory_get(key)
        except Exception as error:  # cache is an optimization, never a failure
            log.warning("cache.get_failed", error=str(error))
            return None
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: dict[str, Any]) -> None:
        raw = json.dumps(value, ensure_ascii=False, default=str)
        try:
            if self._redis:
                await self._redis.set(key, raw, ex=TTL_S)
            else:
                self._memory[key] = (time.time() + TTL_S, raw)
        except Exception as error:
            log.warning("cache.set_failed", error=str(error))

    def _memory_get(self, key: str) -> str | None:
        item = self._memory.get(key)
        if not item or item[0] < time.time():
            self._memory.pop(key, None)
            return None
        return item[1]
