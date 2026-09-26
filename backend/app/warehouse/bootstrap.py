from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

from app.core.config import Settings
from app.warehouse.seed import seed

SCHEMA_DIR = Path(__file__).parent / "schema"

WAREHOUSE_TABLES: tuple[str, ...] = (
    "regions", "stores", "employees", "customers", "categories", "products",
    "inventory", "promotions", "orders", "order_items", "payments", "returns",
)  # fmt: skip


def _run_file(conn: psycopg.Connection[Any], name: str) -> None:
    conn.execute((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def ensure_roles(conn: psycopg.Connection[Any], settings: Settings) -> None:
    roles = (
        ("wh_viewer", settings.warehouse_viewer_password.get_secret_value()),
        ("wh_analyst", settings.warehouse_analyst_password.get_secret_value()),
    )
    for role, password in roles:
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
        verb = sql.SQL("ALTER ROLE") if exists else sql.SQL("CREATE ROLE")
        ident = sql.Identifier(role)
        conn.execute(sql.SQL("{} {} LOGIN PASSWORD {}").format(verb, ident, sql.Literal(password)))
        conn.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(ident))
        conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '10s'").format(ident))


def apply_schema(conn: psycopg.Connection[Any], settings: Settings) -> None:
    """Idempotently create tables, masked views, read-only roles and grants."""
    _run_file(conn, "01_tables.sql")
    _run_file(conn, "02_views.sql")
    ensure_roles(conn, settings)
    _run_file(conn, "03_grants.sql")


def table_counts(conn: psycopg.Connection[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in WAREHOUSE_TABLES:
        row = conn.execute(
            sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))
        ).fetchone()
        counts[table] = int(row[0]) if row else 0
    return counts


def _is_seeded(conn: psycopg.Connection[Any]) -> bool:
    row = conn.execute("SELECT EXISTS (SELECT 1 FROM orders)").fetchone()
    return bool(row and row[0])


def bootstrap_warehouse(settings: Settings, scale: float) -> dict[str, int]:
    """Create schema/roles and seed once. Safe to run on every deploy."""
    with psycopg.connect(settings.warehouse_dsn("admin"), autocommit=True) as conn:
        apply_schema(conn, settings)
        if not _is_seeded(conn):
            with conn.transaction():
                seed(conn, scale=scale)
        return table_counts(conn)
