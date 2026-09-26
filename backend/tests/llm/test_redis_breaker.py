import redis.asyncio as aioredis

from app.llm.circuit import CircuitBreaker, RedisStore


async def test_breaker_state_is_shared_through_redis(redis_url: str) -> None:
    now = [5000.0]
    client = aioredis.from_url(redis_url)
    try:
        await client.flushdb()
        first = CircuitBreaker(RedisStore(client), clock=lambda: now[0])
        second = CircuitBreaker(RedisStore(client), clock=lambda: now[0])
        for _ in range(5):
            await first.record_failure("anthropic")
        assert await second.state("anthropic") == "open"
        now[0] += 31
        assert await second.allow("anthropic")
        assert not await first.allow("anthropic")  # one probe across workers
        await second.record_success("anthropic")
        assert await first.state("anthropic") == "closed"
    finally:
        await client.aclose()
