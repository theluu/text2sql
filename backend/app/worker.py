"""arq worker: runs eval jobs off the API process. `arq app.worker.WorkerSettings`"""

import uuid
from typing import Any

from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.eval.runner import execute_run
from app.services.container import build_services, connect_redis

settings = get_settings()


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging(settings.env)
    engine = create_async_engine(settings.app_db_url, pool_pre_ping=True)
    redis = await connect_redis(settings.redis_url)
    ctx["engine"] = engine
    ctx["services"] = build_services(
        settings, async_sessionmaker(engine, expire_on_commit=False), redis=redis
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    services = ctx["services"]
    if services.redis:
        await services.redis.aclose()
    await ctx["engine"].dispose()


async def run_eval_job(ctx: dict[str, Any], run_id: str) -> dict[str, Any]:
    return await execute_run(ctx["services"], uuid.UUID(run_id))


class WorkerSettings:
    functions = [run_eval_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url or "redis://localhost:6379/0")
    job_timeout = 3600
    max_jobs = 2
