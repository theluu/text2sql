"""Process-wide services, built once per app (or injected by tests)."""

from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.ratelimit import RateLimiter
from app.hitl.notifications import Notifier
from app.llm.base import LLMProvider
from app.llm.circuit import BreakerStore, CircuitBreaker, MemoryStore, RedisStore
from app.llm.registry import build_providers, build_router
from app.llm.router import LLMRouter
from app.pipeline.cache import ResultCache
from app.semantic.embedder import Embedder, build_embedder
from app.semantic.linker import SchemaLinker
from app.semantic.loader import SemanticLayer, load_semantic_layer

log = structlog.get_logger()


@dataclass
class Services:
    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession]
    layer: SemanticLayer
    embedder: Embedder
    linker: SchemaLinker
    providers: dict[str, LLMProvider]
    breaker: CircuitBreaker
    cache: ResultCache
    rate_limiter: RateLimiter
    notifier: Notifier
    redis: "aioredis.Redis | None" = None
    extra: dict[str, Any] = field(default_factory=dict)

    def router(self, app_settings: dict[str, Any]) -> LLMRouter:
        return build_router(
            self.providers, self.breaker, app_settings["llm_chain"], app_settings["chaos"]
        )


async def connect_redis(url: str | None) -> "aioredis.Redis | None":
    if not url:
        return None
    client: aioredis.Redis = aioredis.from_url(url)  # type: ignore[no-untyped-call]
    try:
        await client.ping()
    except Exception as error:
        log.warning("redis.unavailable", error=str(error))
        await client.aclose()
        return None
    return client


def build_services(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    redis: "aioredis.Redis | None",
    providers: dict[str, LLMProvider] | None = None,
    embedder: Embedder | None = None,
) -> Services:
    layer = load_semantic_layer()
    embedder = embedder or build_embedder(
        settings.openai_api_key.get_secret_value() if settings.openai_api_key else None,
        settings.openai_embedding_model,
        settings.ollama_base_url,
        settings.ollama_embedding_model,
    )
    store: BreakerStore = RedisStore(redis) if redis else MemoryStore()
    return Services(
        settings=settings,
        sessionmaker=sessionmaker,
        layer=layer,
        embedder=embedder,
        linker=SchemaLinker(layer, embedder),
        providers=build_providers(settings) if providers is None else providers,
        breaker=CircuitBreaker(store),
        cache=ResultCache(redis),
        rate_limiter=RateLimiter(redis),
        notifier=Notifier(redis),
        redis=redis,
    )
