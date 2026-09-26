from collections.abc import AsyncIterator, Iterator

import httpx
import psycopg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer

from app.core.config import Settings
from app.warehouse.bootstrap import apply_schema
from tests.helpers import DEMO_PASSWORD, make_settings

TEST_DATABASES = ("app_test", "warehouse_test", "app_migration_test")


@pytest.fixture(scope="session")
def pg() -> Iterator[PostgresContainer]:
    with PostgresContainer(
        "pgvector/pgvector:pg16",
        username="postgres",
        password="postgres",
        dbname="postgres",
        driver=None,
    ) as container:
        yield container


@pytest.fixture(scope="session")
def pg_settings(pg: PostgresContainer) -> Settings:
    host = pg.get_container_host_ip()
    port = int(pg.get_exposed_port(5432))
    with psycopg.connect(
        f"postgresql://postgres:postgres@{host}:{port}/postgres", autocommit=True
    ) as conn:
        for name in TEST_DATABASES:
            conn.execute(f"DROP DATABASE IF EXISTS {name}")
            conn.execute(f"CREATE DATABASE {name}")
    return make_settings(
        app_db_url=f"postgresql+asyncpg://postgres:postgres@{host}:{port}/app_test",
        warehouse_host=host,
        warehouse_port=port,
        warehouse_db="warehouse_test",
        warehouse_admin_user="postgres",
        warehouse_admin_password="postgres",
        warehouse_viewer_password="viewer-test-pw",
        warehouse_analyst_password="analyst-test-pw",
        warehouse_seed_scale=0.1,
    )


@pytest.fixture(scope="session")
def warehouse_schema(pg_settings: Settings) -> None:
    with psycopg.connect(pg_settings.warehouse_dsn("admin"), autocommit=True) as conn:
        apply_schema(conn, pg_settings)


@pytest.fixture
def wh_admin(pg_settings: Settings, warehouse_schema: None) -> Iterator[psycopg.Connection]:
    with psycopg.connect(pg_settings.warehouse_dsn("admin"), autocommit=True) as conn:
        yield conn


@pytest.fixture(scope="session")
def seeded_warehouse(pg_settings: Settings, warehouse_schema: None) -> dict[str, int]:
    from app.warehouse.bootstrap import bootstrap_warehouse

    return bootstrap_warehouse(pg_settings, scale=pg_settings.warehouse_seed_scale)


@pytest.fixture(scope="session")
def migrated_app_db(pg_settings: Settings) -> None:
    from app.db.migrate import upgrade_head

    upgrade_head(pg_settings.app_db_url)


@pytest.fixture(scope="session")
async def demo_users(pg_settings: Settings, migrated_app_db: None) -> None:
    from app.auth.demo_users import seed_demo_users

    engine = create_async_engine(pg_settings.app_db_url)
    async with async_sessionmaker(engine)() as session:
        await seed_demo_users(session, DEMO_PASSWORD)
    await engine.dispose()


@pytest.fixture
async def client(pg_settings: Settings, demo_users: None) -> AsyncIterator[httpx.AsyncClient]:
    from app.main import create_app

    app = create_app(pg_settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    await app.state.engine.dispose()
