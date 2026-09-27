from collections.abc import Iterator

import psycopg
import pytest

from app.core.config import Settings

DENIED = (psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction)


@pytest.fixture
def pii_row(wh_admin: psycopg.Connection) -> Iterator[int]:
    wh_admin.execute("INSERT INTO regions VALUES (99, 'Vùng thử', 'Test region')")
    wh_admin.execute(
        "INSERT INTO customers VALUES (9999999, 'Phạm Thị Test', 'pham.test@example.vn',"
        " '0912345678', '1 Lê Lợi', 'Huế', 99, 'gold', '2023-01-01')"
    )
    yield 9999999
    wh_admin.execute("DELETE FROM customers WHERE customer_id = 9999999")
    wh_admin.execute("DELETE FROM regions WHERE region_id = 99")


def connect(settings: Settings, role: str) -> psycopg.Connection:
    return psycopg.connect(settings.warehouse_dsn(role))  # type: ignore[arg-type]


@pytest.mark.usefixtures("warehouse_schema")
def test_viewer_cannot_read_raw_pii_tables(pg_settings: Settings) -> None:
    for query in ("SELECT email FROM customers LIMIT 1", "SELECT salary FROM employees LIMIT 1"):
        with connect(pg_settings, "viewer") as conn, pytest.raises(DENIED):
            conn.execute(query)


def test_viewer_reads_masked_customer_view(pg_settings: Settings, pii_row: int) -> None:
    with connect(pg_settings, "viewer") as conn:
        row = conn.execute(
            "SELECT email, phone, full_name FROM v_customers_masked WHERE customer_id = %s",
            (pii_row,),
        ).fetchone()
    assert row == ("***@example.vn", "***678", "Phạm Thị Test")


def test_masked_employee_view_has_no_salary(
    pg_settings: Settings, wh_admin: psycopg.Connection
) -> None:
    columns = {
        r[0]
        for r in wh_admin.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = 'v_employees_masked'"
        )
    }
    assert "salary" not in columns
    assert {"employee_id", "full_name", "store_id"} <= columns


def test_analyst_can_read_raw_customers(pg_settings: Settings, pii_row: int) -> None:
    with connect(pg_settings, "analyst") as conn:
        row = conn.execute(
            "SELECT email FROM customers WHERE customer_id = %s", (pii_row,)
        ).fetchone()
    assert row == ("pham.test@example.vn",)


def connect_read_write(settings: Settings, role: str) -> psycopg.Connection:
    """Session with the read-only default switched off, so only privileges can deny."""
    conn = connect(settings, role)
    conn.autocommit = True
    conn.execute("SET default_transaction_read_only = off")
    return conn


@pytest.mark.usefixtures("warehouse_schema")
@pytest.mark.parametrize("role", ["viewer", "analyst"])
@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO regions VALUES (98, 'x', 'x')",
        "UPDATE products SET unit_price = 1",
        "DELETE FROM orders",
        "CREATE TABLE hack (i int)",
        "DROP TABLE regions",
        "CREATE TEMP TABLE hack (i int)",
    ],
)
def test_warehouse_roles_cannot_write_even_without_read_only_default(
    pg_settings: Settings, role: str, statement: str
) -> None:
    with (
        connect_read_write(pg_settings, role) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(statement)


@pytest.mark.usefixtures("warehouse_schema")
@pytest.mark.parametrize("role", ["viewer", "analyst"])
@pytest.mark.parametrize(
    "statement",
    [
        "SELECT set_config('statement_timeout', '0', false)",
        "SELECT set_config('default_transaction_read_only', 'off', false)",
        "SELECT pg_sleep(0)",
        "SELECT pg_sleep_for('0 seconds')",
        "SELECT pg_sleep_until(now())",
    ],
)
def test_warehouse_roles_cannot_call_session_or_sleep_functions(
    pg_settings: Settings, role: str, statement: str
) -> None:
    with connect(pg_settings, role) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)


@pytest.mark.usefixtures("warehouse_schema")
@pytest.mark.parametrize("role", ["viewer", "analyst"])
def test_warehouse_roles_have_readonly_defaults(pg_settings: Settings, role: str) -> None:
    with connect(pg_settings, role) as conn:
        read_only = conn.execute("SHOW default_transaction_read_only").fetchone()
        timeout = conn.execute("SHOW statement_timeout").fetchone()
    assert read_only == ("on",)
    assert timeout == ("10s",)


def test_apply_schema_is_idempotent(pg_settings: Settings, wh_admin: psycopg.Connection) -> None:
    from app.warehouse.bootstrap import apply_schema

    apply_schema(wh_admin, pg_settings)
    apply_schema(wh_admin, pg_settings)


def test_hardening_is_skipped_not_fatal_for_non_superuser_admin(
    pg_settings: Settings, wh_admin: psycopg.Connection
) -> None:
    """On a shared server the warehouse admin is not a superuser but owns the schema and the
    tables it created: bootstrap must still succeed and only skip the pg_catalog hardening."""
    from app.warehouse.bootstrap import WAREHOUSE_TABLES, apply_schema

    relations = [*WAREHOUSE_TABLES, "v_customers_masked", "v_employees_masked"]
    wh_admin.execute("DROP ROLE IF EXISTS t2s_limited")
    wh_admin.execute("CREATE ROLE t2s_limited LOGIN CREATEROLE PASSWORD 'limited-pw'")
    wh_admin.execute("ALTER SCHEMA public OWNER TO t2s_limited")
    # PG16: CREATEROLE only manages roles it has ADMIN on (it would, having created them).
    wh_admin.execute("GRANT wh_viewer, wh_analyst TO t2s_limited WITH ADMIN OPTION")
    for name in relations:
        wh_admin.execute(f"ALTER TABLE {name} OWNER TO t2s_limited")
    try:
        dsn = pg_settings.warehouse_dsn("admin").replace(
            "postgres:postgres@", "t2s_limited:limited-pw@"
        )
        with psycopg.connect(dsn, autocommit=True) as conn:
            apply_schema(conn, pg_settings)  # must not raise
    finally:
        wh_admin.execute("ALTER SCHEMA public OWNER TO postgres")
        for name in relations:
            wh_admin.execute(f"ALTER TABLE {name} OWNER TO postgres")
        wh_admin.execute("DROP OWNED BY t2s_limited")
        wh_admin.execute("DROP ROLE t2s_limited")
