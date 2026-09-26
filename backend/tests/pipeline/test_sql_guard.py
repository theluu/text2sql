import pytest

from app.pipeline.sql_guard import clean_sql, validate_sql

ATTACKS: list[tuple[str, str, str]] = [
    # (role, sql, expected code)
    ("analyst", "DELETE FROM orders", "NON_SELECT"),
    ("analyst", "UPDATE products SET unit_price = 1", "NON_SELECT"),
    ("analyst", "INSERT INTO regions VALUES (9, 'x', 'x')", "NON_SELECT"),
    ("analyst", "DROP TABLE orders", "NON_SELECT"),
    ("analyst", "TRUNCATE orders", "NON_SELECT"),
    ("analyst", "ALTER TABLE orders ADD COLUMN x int", "NON_SELECT"),
    ("analyst", "CREATE TABLE hack AS SELECT * FROM customers", "NON_SELECT"),
    ("analyst", "GRANT SELECT ON customers TO wh_viewer", "NON_SELECT"),
    ("analyst", "REVOKE SELECT ON orders FROM wh_analyst", "NON_SELECT"),
    ("analyst", "COPY customers TO STDOUT", "NON_SELECT"),
    ("analyst", "COPY (SELECT email FROM customers) TO '/tmp/x'", "NON_SELECT"),
    ("analyst", "SET statement_timeout = 0", "NON_SELECT"),
    ("analyst", "SHOW ALL", "NON_SELECT"),
    ("analyst", "DO $$ BEGIN DELETE FROM orders; END $$", "MULTI_STATEMENT"),
    ("analyst", "DO $$ BEGIN PERFORM 1 END $$", "NON_SELECT"),
    ("analyst", "EXPLAIN ANALYZE DELETE FROM orders", "NON_SELECT"),
    ("analyst", "CALL refresh()", "NON_SELECT"),
    ("analyst", "VACUUM orders", "NON_SELECT"),
    ("analyst", "BEGIN", "NON_SELECT"),
    ("analyst", "SELECT * INTO hack FROM orders", "NON_SELECT"),
    ("analyst", "SELECT * FROM orders FOR UPDATE", "NON_SELECT"),
    ("analyst", "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d", "NON_SELECT"),
    (
        "analyst",
        "WITH u AS (UPDATE products SET unit_price = 0 RETURNING 1) SELECT 1",
        "NON_SELECT",
    ),
    (
        "analyst",
        "WITH i AS (INSERT INTO regions VALUES (9,'a','b') RETURNING 1) SELECT 1",
        "NON_SELECT",
    ),
    ("analyst", "SELECT 1; DROP TABLE orders", "MULTI_STATEMENT"),
    ("analyst", "SELECT 1; SELECT 2", "MULTI_STATEMENT"),
    ("analyst", "SELECT 1 ; ; DELETE FROM orders", "MULTI_STATEMENT"),
    (
        "analyst",
        "SELECT * FROM orders -- ; DROP TABLE orders\n; DELETE FROM orders",
        "MULTI_STATEMENT",
    ),
    ("analyst", "SELECT 1 /* ; */ ; DELETE FROM orders", "MULTI_STATEMENT"),
    ("analyst", "SELECT ';' || 'x'; DELETE FROM orders", "MULTI_STATEMENT"),
    ("analyst", "SELECT pg_sleep(30)", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT PG_SLEEP(30)", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT pg_sleep_for('1 minute')", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT count(*) FROM orders WHERE pg_sleep(1) IS NOT NULL", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT pg_read_file('/etc/passwd')", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT pg_ls_dir('.')", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT pg_terminate_backend(1)", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT lo_import('/etc/passwd')", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT lo_export(1, '/tmp/x')", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT * FROM dblink('host=evil', 'select 1') AS t(a int)", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT dblink_exec('host=evil', 'drop table x')", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT set_config('statement_timeout', '0', false)", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT current_setting('data_directory')", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT query_to_xml('delete from orders', true, true, '')", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT version()", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT * FROM pg_catalog.pg_user", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT * FROM pg_shadow", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT * FROM pg_roles", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT * FROM information_schema.tables", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT table_name FROM information_schema.columns", "FORBIDDEN_OBJECT"),
    (
        "analyst",
        "SELECT * FROM orders WHERE order_id IN (SELECT oid FROM pg_class)",
        "FORBIDDEN_OBJECT",
    ),
    ("analyst", "SELECT * FROM other_schema.orders", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT * FROM otherdb.public.orders", "FORBIDDEN_OBJECT"),
    ("analyst", "SELECT 1 UNION SELECT usename::int FROM pg_user", "FORBIDDEN_OBJECT"),
    ("viewer", "SELECT email FROM customers", "TABLE_NOT_ALLOWED"),
    ("viewer", "SELECT salary FROM employees", "TABLE_NOT_ALLOWED"),
    (
        "viewer",
        "SELECT o.order_id FROM orders o JOIN customers c USING (customer_id)",
        "TABLE_NOT_ALLOWED",
    ),
    (
        "viewer",
        "SELECT * FROM orders WHERE customer_id IN (SELECT customer_id FROM customers)",
        "TABLE_NOT_ALLOWED",
    ),
    ("viewer", "WITH c AS (SELECT * FROM customers) SELECT count(*) FROM c", "TABLE_NOT_ALLOWED"),
    ("viewer", "SELECT 1 UNION ALL SELECT salary FROM employees", "TABLE_NOT_ALLOWED"),
    ("viewer", "SELECT e.salary FROM v_employees_masked e", "COLUMN_NOT_ALLOWED"),
    ("viewer", "SELECT c.address FROM v_customers_masked c", "COLUMN_NOT_ALLOWED"),
    ("analyst", "SELECT o.password FROM orders o", "COLUMN_NOT_ALLOWED"),
    ("analyst", "SELECT * FROM users", "UNKNOWN_TABLE"),
    ("analyst", "SELECT * FROM app_settings", "UNKNOWN_TABLE"),
    ("analyst", "SELEC * FRM orders", "SYNTAX_ERROR"),
    ("analyst", "", "SYNTAX_ERROR"),
]


@pytest.mark.parametrize(("role", "sql", "code"), ATTACKS)
def test_attacks_are_blocked(role: str, sql: str, code: str) -> None:
    check = validate_sql(sql, role)
    assert not check.ok
    assert check.code == code, check.message


def test_attack_suite_is_at_least_sixty_cases() -> None:
    assert len(ATTACKS) >= 60


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("```sql\nSELECT 1;\n```", "SELECT 1"),
        ("  SELECT 1 ;; ", "SELECT 1"),
        ("```\nSELECT 2\n```", "SELECT 2"),
    ],
)
def test_clean_sql_strips_fences_and_trailing_semicolons(raw: str, expected: str) -> None:
    assert clean_sql(raw) == expected


def test_llm_formatting_is_not_mistaken_for_multi_statement() -> None:
    check = validate_sql("```sql\nSELECT count(*) FROM orders;\n```", "viewer")
    assert check.ok
    assert check.sql == "SELECT COUNT(*) FROM orders LIMIT 1000"


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT * FROM orders", "SELECT * FROM orders LIMIT 1000"),
        ("SELECT * FROM orders LIMIT 10", "SELECT * FROM orders LIMIT 10"),
        ("SELECT * FROM orders LIMIT 50000", "SELECT * FROM orders LIMIT 1000"),
        ("SELECT * FROM orders LIMIT ALL", "SELECT * FROM orders LIMIT 1000"),
        ("SELECT 1 UNION SELECT 2", "SELECT 1 UNION SELECT 2 LIMIT 1000"),
        ("SELECT * FROM orders FETCH FIRST 5000 ROWS ONLY", "SELECT * FROM orders LIMIT 1000"),
    ],
)
def test_limit_is_added_or_clamped(sql: str, expected: str) -> None:
    check = validate_sql(sql, "analyst")
    assert check.ok, check.message
    assert check.sql == expected


def test_comments_are_dropped_from_executed_sql() -> None:
    check = validate_sql("SELECT order_id /* hi */ FROM orders -- trailing", "analyst")
    assert check.ok
    assert "--" not in (check.sql or "") and "/*" not in (check.sql or "")


def test_valid_queries_pass_and_report_tables() -> None:
    check = validate_sql(
        "WITH r AS (SELECT s.region_id, SUM(oi.quantity * oi.unit_price) AS revenue "
        "FROM orders o JOIN order_items oi ON oi.order_id = o.order_id "
        "JOIN stores s ON s.store_id = o.store_id WHERE o.status <> 'cancelled' "
        "GROUP BY 1) SELECT g.name, r.revenue FROM r JOIN regions g USING (region_id) "
        "ORDER BY 2 DESC",
        "viewer",
    )
    assert check.ok, check.message
    assert set(check.tables) == {"orders", "order_items", "stores", "regions"}
    assert check.pii_columns == []


def test_generate_series_is_allowed() -> None:
    assert validate_sql("SELECT d FROM generate_series(1, 3) AS d", "viewer").ok


@pytest.mark.parametrize(
    ("role", "sql", "pii"),
    [
        ("viewer", "SELECT email FROM v_customers_masked", ["v_customers_masked.email"]),
        ("viewer", "SELECT c.phone FROM v_customers_masked c", ["v_customers_masked.phone"]),
        (
            "analyst",
            "SELECT * FROM customers",
            ["customers.address", "customers.email", "customers.phone"],
        ),
        ("analyst", "SELECT AVG(salary) FROM employees", ["employees.salary"]),
        (
            "analyst",
            "SELECT email, count(*) FROM customers c JOIN orders o USING (customer_id) GROUP BY email",
            ["customers.email"],
        ),
        ("viewer", "SELECT full_name, segment FROM v_customers_masked", []),
    ],
)
def test_pii_columns_are_reported_anywhere_in_the_ast(role: str, sql: str, pii: list[str]) -> None:
    check = validate_sql(sql, role)
    assert check.ok, check.message
    assert check.pii_columns == pii
