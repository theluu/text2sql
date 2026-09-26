import time

import redis.asyncio as aioredis


class RateLimiter:
    """Fixed one-minute window per user; allows everything if Redis is unavailable."""

    def __init__(self, client: "aioredis.Redis | None", per_minute: int = 20) -> None:
        self._redis = client
        self.per_minute = per_minute
        self._memory: dict[str, int] = {}

    async def hit(self, user_id: str) -> bool:
        key = f"rl:{user_id}:{int(time.time() // 60)}"
        try:
            if self._redis is None:
                self._memory[key] = self._memory.get(key, 0) + 1
                return self._memory[key] <= self.per_minute
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 70)
            return int(count) <= self.per_minute
        except Exception:
            return True
