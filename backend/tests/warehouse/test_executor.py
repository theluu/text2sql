import pytest

from app.core.config import Settings
from app.warehouse.executor import WarehouseError, explain_cost, run_query, warehouse_role

pytestmark = pytest.mark.usefixtures("seeded_warehouse")


def test_role_mapping() -> None:
    assert warehouse_role("viewer") == "viewer"
    assert warehouse_role("analyst") == "analyst"
    assert warehouse_role("admin") == "analyst"


async def test_run_query_returns_json_safe_rows(pg_settings: Settings) -> None:
    result = await run_query(
        pg_settings,
        "viewer",
        "SELECT region_id, name, 1.5::numeric AS ratio, 10::numeric AS whole,"
        " date '2025-01-02' AS day FROM regions ORDER BY region_id LIMIT 2",
    )
    assert result.columns == ["region_id", "name", "ratio", "whole", "day"]
    assert result.rows[0] == [1, "Đồng bằng sông Hồng", 1.5, 10, "2025-01-02"]
    assert result.column_types == ["number", "text", "number", "number", "date"]
    assert result.row_count == 2 and not result.truncated


async def test_run_query_truncates_to_max_rows(pg_settings: Settings) -> None:
    result = await run_query(pg_settings, "viewer", "SELECT order_id FROM orders", max_rows=5)
    assert result.row_count == 5 and result.truncated


async def test_viewer_role_cannot_read_raw_customers(pg_settings: Settings) -> None:
    with pytest.raises(WarehouseError) as caught:
        await run_query(pg_settings, "viewer", "SELECT email FROM customers LIMIT 1")
    assert caught.value.code == "DB_PERMISSION"


async def test_writes_fail_even_if_they_slip_past_the_validator(pg_settings: Settings) -> None:
    with pytest.raises(WarehouseError) as caught:
        await run_query(pg_settings, "admin", "DELETE FROM orders")
    assert caught.value.code == "DB_PERMISSION"


async def test_timeout_is_reported(pg_settings: Settings) -> None:
    with pytest.raises(WarehouseError) as caught:
        await run_query(
            pg_settings,
            "analyst",
            "SELECT count(*) FROM orders a, orders b, orders c",
            timeout_ms=200,
        )
    assert caught.value.code == "DB_TIMEOUT"


async def test_bad_column_is_a_db_error_with_message(pg_settings: Settings) -> None:
    with pytest.raises(WarehouseError) as caught:
        await run_query(pg_settings, "viewer", "SELECT nope FROM orders")
    assert caught.value.code == "DB_ERROR"
    assert "nope" in caught.value.message


async def test_explain_cost_grows_with_query_size(pg_settings: Settings) -> None:
    small = await explain_cost(pg_settings, "viewer", "SELECT * FROM regions")
    huge = await explain_cost(pg_settings, "viewer", "SELECT count(*) FROM orders a, orders b")
    assert 0 < small < huge
