import asyncio
from typing import Annotated, Any

import structlog
from fastapi import Depends, FastAPI, Request

from app.core.config import Settings
from app.llm.base import LLMProvider
from app.semantic.embedder import Embedder
from app.semantic.sync import sync_embeddings
from app.services.container import Services, build_services, connect_redis

log = structlog.get_logger()


async def init_services(app: FastAPI) -> Services:
    """Build services once per app; safe to call concurrently and without lifespan (tests)."""
    lock: asyncio.Lock = app.state.services_lock
    async with lock:
        existing: Services | None = getattr(app.state, "services", None)
        if existing is not None:
            return existing
        settings: Settings = app.state.settings
        overrides: dict[str, Any] = app.state.service_overrides
        redis = await connect_redis(settings.redis_url)
        providers: dict[str, LLMProvider] | None = overrides.get("providers")
        embedder: Embedder | None = overrides.get("embedder")
        services = build_services(
            settings, app.state.sessionmaker, redis=redis, providers=providers, embedder=embedder
        )
        try:
            async with services.sessionmaker() as session:
                await sync_embeddings(session, services.layer, services.embedder)
        except Exception as error:  # embeddings are an optimization; linking falls back to keywords
            log.warning("embeddings.sync_failed", error=str(error))
        app.state.services = services
        return services


async def get_services(request: Request) -> Services:
    services: Services | None = getattr(request.app.state, "services", None)
    return services or await init_services(request.app)


ServicesDep = Annotated[Services, Depends(get_services)]
