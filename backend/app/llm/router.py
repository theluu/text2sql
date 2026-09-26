"""Failover router: walk the provider chain under one time budget.

Per provider: circuit check → up to `max_retries` retries (429/5xx/timeout only, exponential
backoff + jitter) → on any other error, or when retries run out, move to the next provider.
Chaos-disabled providers fail immediately (and count toward their circuit).
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

import structlog

from app.llm.base import LLMProvider, LLMResponse, Message, ProviderError
from app.llm.circuit import CircuitBreaker

log = structlog.get_logger()


@dataclass
class Attempt:
    purpose: str
    provider: str
    model: str
    attempt: int
    outcome: str  # ok | timeout | error | circuit_open | parse_fail | chaos | rate_limit
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Routed:
    response: LLMResponse
    attempts: list[Attempt]

    @property
    def failover(self) -> bool:
        return any(a.outcome != "ok" for a in self.attempts)


class AllProvidersFailed(Exception):
    def __init__(self, attempts: list[Attempt], reason: str = "all providers failed") -> None:
        super().__init__(reason)
        self.attempts = attempts


_OUTCOME = {"timeout": "timeout", "rate_limit": "rate_limit", "parse": "parse_fail"}


class LLMRouter:
    def __init__(
        self,
        providers: list[LLMProvider],
        breaker: CircuitBreaker,
        *,
        chaos: set[str] | None = None,
        budget_s: float = 20.0,
        call_timeout_s: float = 15.0,
        max_retries: int = 2,
        backoff_s: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.providers = providers
        self.breaker = breaker
        self.chaos = chaos or set()
        self.budget_s = budget_s
        self.call_timeout_s = call_timeout_s
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self._sleep = sleep
        self._clock = clock

    @property
    def available(self) -> bool:
        return bool(self.providers)

    def vendors(self) -> set[str]:
        return {p.vendor for p in self.providers}

    def _ordered(self, avoid_vendor: str | None, only: str | None) -> list[LLMProvider]:
        if only:
            return [p for p in self.providers if p.name == only]
        if not avoid_vendor:
            return list(self.providers)
        others = [p for p in self.providers if p.vendor != avoid_vendor]
        return others + [p for p in self.providers if p.vendor == avoid_vendor]

    async def complete(
        self,
        purpose: str,
        messages: list[Message],
        *,
        schema: dict[str, Any],
        schema_name: str,
        avoid_vendor: str | None = None,
        only: str | None = None,
    ) -> Routed:
        deadline = self._clock() + self.budget_s
        attempts: list[Attempt] = []
        for provider in self._ordered(avoid_vendor, only):
            record = Attempt(purpose, provider.name, provider.model, 1, "error")
            if provider.name in self.chaos:
                record.outcome, record.error = "chaos", "disabled by chaos setting"
                attempts.append(record)
                await self.breaker.record_failure(provider.name)
                continue
            if not await self.breaker.allow(provider.name):
                record.outcome, record.error = "circuit_open", "circuit open"
                attempts.append(record)
                continue
            for attempt in range(1, self.max_retries + 2):
                remaining = deadline - self._clock()
                if remaining < 0.5:
                    raise AllProvidersFailed(attempts, "time budget exhausted")
                record = Attempt(purpose, provider.name, provider.model, attempt, "error")
                try:
                    response = await asyncio.wait_for(
                        provider.complete(
                            messages,
                            schema=schema,
                            schema_name=schema_name,
                            timeout_s=min(self.call_timeout_s, remaining),
                        ),
                        timeout=min(self.call_timeout_s, remaining),
                    )
                except (TimeoutError, ProviderError) as error:
                    kind = error.kind if isinstance(error, ProviderError) else "timeout"
                    record.outcome = _OUTCOME.get(kind, "error")
                    record.error = str(error)[:300]
                    attempts.append(record)
                    retryable = isinstance(error, TimeoutError) or error.retryable
                    if retryable and attempt <= self.max_retries:
                        delay = self.backoff_s * 2 ** (attempt - 1) * (1 + random.random() * 0.25)
                        if deadline - self._clock() - delay < 0.5:
                            break
                        await self._sleep(delay)
                        continue
                    await self.breaker.record_failure(provider.name)
                    log.warning("llm.provider_failed", provider=provider.name, error=record.error)
                    break
                record.outcome = "ok"
                record.latency_ms = response.latency_ms
                record.input_tokens = response.input_tokens
                record.output_tokens = response.output_tokens
                record.cost_usd = response.cost_usd
                attempts.append(record)
                await self.breaker.record_success(provider.name)
                return Routed(response, attempts)
        raise AllProvidersFailed(attempts)
