"""Per-provider circuit breaker: 5 failures in 60 s → open 30 s → half-open lets one probe through.

State lives in Redis so every API worker shares it; `MemoryStore` backs tests and the
no-Redis fallback.
"""

import time
import uuid
from collections.abc import Callable
from typing import Literal, Protocol

import redis.asyncio as aioredis

State = Literal["closed", "open", "half_open"]


class BreakerStore(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl: float | None = None) -> None: ...
    async def set_nx(self, key: str, value: str, ttl: float) -> bool: ...
    async def delete(self, *keys: str) -> None: ...
    async def add_event(self, key: str, now: float, window: float) -> int: ...


class MemoryStore:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._values: dict[str, tuple[str, float | None]] = {}
        self._events: dict[str, list[float]] = {}

    def _live(self, key: str) -> str | None:
        item = self._values.get(key)
        if item is None:
            return None
        value, expires = item
        if expires is not None and self._clock() >= expires:
            del self._values[key]
            return None
        return value

    async def get(self, key: str) -> str | None:
        return self._live(key)

    async def set(self, key: str, value: str, ttl: float | None = None) -> None:
        self._values[key] = (value, self._clock() + ttl if ttl else None)

    async def set_nx(self, key: str, value: str, ttl: float) -> bool:
        if self._live(key) is not None:
            return False
        await self.set(key, value, ttl)
        return True

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._values.pop(key, None)
            self._events.pop(key, None)

    async def add_event(self, key: str, now: float, window: float) -> int:
        events = [t for t in self._events.get(key, []) if t > now - window] + [now]
        self._events[key] = events
        return len(events)


class RedisStore:
    def __init__(self, client: "aioredis.Redis") -> None:
        self._r = client

    async def get(self, key: str) -> str | None:
        value = await self._r.get(key)
        return value.decode() if isinstance(value, bytes) else value

    async def set(self, key: str, value: str, ttl: float | None = None) -> None:
        await self._r.set(key, value, px=int(ttl * 1000) if ttl else None)

    async def set_nx(self, key: str, value: str, ttl: float) -> bool:
        return bool(await self._r.set(key, value, px=int(ttl * 1000), nx=True))

    async def delete(self, *keys: str) -> None:
        await self._r.delete(*keys)

    async def add_event(self, key: str, now: float, window: float) -> int:
        async with self._r.pipeline(transaction=True) as pipe:
            pipe.zadd(key, {f"{now:.6f}:{uuid.uuid4().hex[:8]}": now})  # unique per failure
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zcard(key)
            pipe.expire(key, int(window) + 1)
            results = await pipe.execute()
        return int(results[2])


class CircuitBreaker:
    def __init__(
        self,
        store: BreakerStore,
        *,
        threshold: int = 5,
        window_s: float = 60.0,
        cooldown_s: float = 30.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self.threshold = threshold
        self.window_s = window_s
        self.cooldown_s = cooldown_s
        self.clock = clock

    def _keys(self, name: str) -> tuple[str, str, str]:
        return f"cb:{name}:open_until", f"cb:{name}:failures", f"cb:{name}:probe"

    async def state(self, name: str) -> State:
        open_key, _, _ = self._keys(name)
        until = await self.store.get(open_key)
        if until is None:
            return "closed"
        return "open" if self.clock() < float(until) else "half_open"

    async def allow(self, name: str) -> bool:
        state = await self.state(name)
        if state == "closed":
            return True
        if state == "open":
            return False
        _, _, probe_key = self._keys(name)
        # Only one request probes a half-open circuit; its outcome closes or reopens it.
        return await self.store.set_nx(probe_key, "1", ttl=self.cooldown_s)

    async def record_success(self, name: str) -> None:
        await self.store.delete(*self._keys(name))

    async def record_failure(self, name: str) -> None:
        open_key, failures_key, probe_key = self._keys(name)
        now = self.clock()
        if await self.state(name) == "half_open":
            await self._open(open_key, probe_key, now)
            return
        if await self.store.add_event(failures_key, now, self.window_s) >= self.threshold:
            await self._open(open_key, probe_key, now)

    async def _open(self, open_key: str, probe_key: str, now: float) -> None:
        # Keep the marker past the cooldown so the half-open phase is observable.
        await self.store.set(open_key, str(now + self.cooldown_s), ttl=self.cooldown_s * 20)
        await self.store.delete(probe_key)
