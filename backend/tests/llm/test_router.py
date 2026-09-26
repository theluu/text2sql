import asyncio
from typing import Any

import pytest

from app.llm.base import LLMResponse, Message, ProviderError
from app.llm.circuit import CircuitBreaker, MemoryStore
from app.llm.fake import FakeLLMProvider
from app.llm.router import AllProvidersFailed, LLMRouter

SCHEMA: dict[str, Any] = {"type": "object"}
MSGS = [Message("user", "q")]
OK = {"sql": "SELECT 1"}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_router(*providers: Any, clock: Clock | None = None, **kwargs: Any) -> LLMRouter:
    clock = clock or Clock()
    breaker = CircuitBreaker(MemoryStore(clock), clock=clock)

    async def no_sleep(seconds: float) -> None:
        clock.now += seconds

    return LLMRouter(list(providers), breaker, sleep=no_sleep, clock=clock, **kwargs)


async def complete(router: LLMRouter, **kwargs: Any) -> Any:
    return await router.complete("generate", MSGS, schema=SCHEMA, schema_name="gen", **kwargs)


async def test_first_provider_answers() -> None:
    routed = await complete(make_router(FakeLLMProvider("a", "va", [OK])))
    assert routed.response.provider == "a" and not routed.failover
    assert [a.outcome for a in routed.attempts] == ["ok"]


async def test_rate_limit_is_retried_then_succeeds() -> None:
    a = FakeLLMProvider("a", "va", [ProviderError("rate_limit"), OK])
    routed = await complete(make_router(a))
    assert [x.outcome for x in routed.attempts] == ["rate_limit", "ok"]
    assert routed.response.provider == "a"


async def test_retries_are_capped_then_fail_over() -> None:
    a = FakeLLMProvider("a", "va", [ProviderError("server")])
    b = FakeLLMProvider("b", "vb", [OK])
    routed = await complete(make_router(a, b))
    assert [(x.provider, x.attempt) for x in routed.attempts] == [
        ("a", 1), ("a", 2), ("a", 3), ("b", 1),
    ]  # fmt: skip
    assert routed.response.provider == "b" and routed.failover


async def test_parse_failure_is_not_retried() -> None:
    a = FakeLLMProvider("a", "va", [ProviderError("parse")])
    b = FakeLLMProvider("b", "vb", [OK])
    routed = await complete(make_router(a, b))
    assert [x.outcome for x in routed.attempts] == ["parse_fail", "ok"]


async def test_timeout_moves_on() -> None:
    class Slow:
        name, vendor, model = "slow", "vs", "s"

        async def complete(self, *args: Any, **kwargs: Any) -> LLMResponse:
            await asyncio.sleep(5)
            raise AssertionError("unreachable")

    router = LLMRouter(
        [Slow(), FakeLLMProvider("b", "vb", [OK])],
        CircuitBreaker(MemoryStore()),
        call_timeout_s=0.05,
        max_retries=0,
    )
    routed = await complete(router)
    assert [x.outcome for x in routed.attempts] == ["timeout", "ok"]


async def test_chaos_disables_a_provider() -> None:
    a = FakeLLMProvider("a", "va", [OK])
    routed = await complete(make_router(a, FakeLLMProvider("b", "vb", [OK]), chaos={"a"}))
    assert [x.outcome for x in routed.attempts] == ["chaos", "ok"]
    assert a.calls == []


async def test_all_failing_raises_with_attempts() -> None:
    router = make_router(FakeLLMProvider("a", "va", [ProviderError("auth")]))
    with pytest.raises(AllProvidersFailed) as caught:
        await complete(router)
    assert [x.outcome for x in caught.value.attempts] == ["error"]


async def test_empty_chain_raises() -> None:
    with pytest.raises(AllProvidersFailed):
        await complete(make_router())


async def test_budget_exhaustion_stops_the_chain() -> None:
    clock = Clock()

    def slow_failure(messages: list[Message], name: str) -> dict[str, Any]:
        clock.now += 1.0  # the call itself eats the budget
        raise ProviderError("client")

    b = FakeLLMProvider("b", "vb", [OK])
    router = make_router(FakeLLMProvider("a", "va", [slow_failure]), b, clock=clock, budget_s=1.2)
    with pytest.raises(AllProvidersFailed, match="budget"):
        await complete(router)
    assert b.calls == []


async def test_no_backoff_past_the_budget_moves_to_next_provider() -> None:
    a = FakeLLMProvider("a", "va", [ProviderError("server")])
    router = make_router(a, FakeLLMProvider("b", "vb", [OK]), budget_s=1.2, backoff_s=1.0)
    routed = await complete(router)
    assert [x.provider for x in routed.attempts] == ["a", "b"]


async def test_avoid_vendor_prefers_other_vendors_for_judging() -> None:
    a = FakeLLMProvider("a", "anthropic", [OK])
    b = FakeLLMProvider("b", "openai", [OK])
    routed = await complete(make_router(a, b), avoid_vendor="anthropic")
    assert routed.response.provider == "b"
    solo = await complete(make_router(a), avoid_vendor="anthropic")
    assert solo.response.provider == "a"  # same vendor is the last resort


async def test_only_forces_one_provider() -> None:
    a, b = FakeLLMProvider("a", "va", [OK]), FakeLLMProvider("b", "vb", [OK])
    routed = await complete(make_router(a, b), only="b")
    assert routed.response.provider == "b" and a.calls == []


async def test_circuit_opens_after_five_failures_and_half_opens() -> None:
    clock = Clock()
    breaker = CircuitBreaker(MemoryStore(clock), clock=clock)
    for _ in range(4):
        await breaker.record_failure("a")
    assert await breaker.state("a") == "closed"
    await breaker.record_failure("a")
    assert await breaker.state("a") == "open"
    assert not await breaker.allow("a")
    clock.now += 31
    assert await breaker.state("a") == "half_open"
    assert await breaker.allow("a")  # the single probe
    assert not await breaker.allow("a")
    await breaker.record_failure("a")  # probe failed → open again
    assert await breaker.state("a") == "open"
    clock.now += 31
    assert await breaker.allow("a")
    await breaker.record_success("a")
    assert await breaker.state("a") == "closed"


async def test_failures_outside_the_window_do_not_count() -> None:
    clock = Clock()
    breaker = CircuitBreaker(MemoryStore(clock), clock=clock)
    for _ in range(4):
        await breaker.record_failure("a")
    clock.now += 61
    await breaker.record_failure("a")
    assert await breaker.state("a") == "closed"


async def test_open_circuit_is_skipped_by_router() -> None:
    clock = Clock()
    a = FakeLLMProvider("a", "va", [ProviderError("auth")])
    b = FakeLLMProvider("b", "vb", [OK])
    router = make_router(a, b, clock=clock)
    for _ in range(5):
        await complete(router)
    calls_before = len(a.calls)
    routed = await complete(router)
    assert routed.attempts[0].outcome == "circuit_open"
    assert len(a.calls) == calls_before
