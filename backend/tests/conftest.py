from collections.abc import Iterator

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

from app.core.config import Settings
from app.warehouse.bootstrap import apply_schema
from tests.helpers import make_settings

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
