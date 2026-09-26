import psycopg

from app.cli import bootstrap
from app.core.config import Settings
from tests.helpers import sync_dsn


def test_bootstrap_is_idempotent(pg_settings: Settings, seeded_warehouse: dict[str, int]) -> None:
    bootstrap(pg_settings)
    bootstrap(pg_settings)
    with psycopg.connect(sync_dsn(pg_settings.app_db_url)) as conn:
        emails = sorted(r[0] for r in conn.execute("SELECT email FROM users"))
    assert emails == ["admin@demo.vn", "analyst@demo.vn", "viewer@demo.vn"]
    with psycopg.connect(pg_settings.warehouse_dsn("admin")) as conn:
        row = conn.execute("SELECT count(*) FROM orders").fetchone()
    assert row == (seeded_warehouse["orders"],)
