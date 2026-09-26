import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes import auth, conversations, health, query
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.services.deps import init_services


def create_app(settings: Settings | None = None, **service_overrides: Any) -> FastAPI:
    """`service_overrides` (providers=…, embedder=…) let tests inject fakes."""
    settings = settings or get_settings()
    configure_logging(settings.env)
    engine = create_async_engine(settings.app_db_url, pool_pre_ping=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await init_services(app)
        yield
        services = getattr(app.state, "services", None)
        if services and services.redis:
            await services.redis.aclose()
        await engine.dispose()

    app = FastAPI(title="Text2SQL API", version="0.2.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    app.state.services_lock = asyncio.Lock()
    app.state.service_overrides = service_overrides
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(query.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")
    return app
