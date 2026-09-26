import argparse
import asyncio

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth.demo_users import seed_demo_users
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.migrate import upgrade_head
from app.warehouse.bootstrap import bootstrap_warehouse


async def _seed_users(settings: Settings) -> int:
    engine = create_async_engine(settings.app_db_url)
    try:
        async with async_sessionmaker(engine)() as session:
            return await seed_demo_users(session, settings.demo_password.get_secret_value())
    finally:
        await engine.dispose()


def bootstrap(settings: Settings) -> None:
    """Migrate app-db, prepare + seed warehouse, create demo users. Idempotent."""
    log = structlog.get_logger()
    upgrade_head(settings.app_db_url)
    log.info("app_db.migrated")
    counts = bootstrap_warehouse(settings, scale=settings.warehouse_seed_scale)
    log.info("warehouse.ready", **counts)
    created = asyncio.run(_seed_users(settings))
    log.info("demo_users.ready", created=created)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("bootstrap", help="migrate, seed warehouse and demo users")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.env)
    if args.command == "bootstrap":
        bootstrap(settings)


if __name__ == "__main__":
    main()
