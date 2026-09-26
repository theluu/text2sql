from datetime import date
from statistics import median

import psycopg
import pytest

from app.core.config import Settings
from app.warehouse.bootstrap import WAREHOUSE_TABLES, bootstrap_warehouse
from app.warehouse.seed import PERIOD_END, PERIOD_START

LOCAL_DATE = "(order_date AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"

pytestmark = pytest.mark.usefixtures("seeded_warehouse")


def test_every_table_is_populated(seeded_warehouse: dict[str, int]) -> None:
    assert set(seeded_warehouse) == set(WAREHOUSE_TABLES)
    assert all(count > 0 for count in seeded_warehouse.values()), seeded_warehouse
    assert seeded_warehouse["orders"] == 6000
    assert seeded_warehouse["order_items"] > seeded_warehouse["orders"]


def test_orders_fall_inside_business_period(wh_admin: psycopg.Connection) -> None:
    lo, hi = wh_admin.execute(f"SELECT min({LOCAL_DATE}), max({LOCAL_DATE}) FROM orders").fetchone()
    assert lo >= PERIOD_START and hi <= PERIOD_END


def test_offline_orders_are_served_by_staff_of_the_same_store(wh_admin: psycopg.Connection) -> None:
    (bad,) = wh_admin.execute(
        "SELECT count(*) FROM orders o JOIN stores s USING (store_id)"
        " LEFT JOIN employees e ON e.employee_id = o.employee_id"
        " WHERE (s.channel = 'offline' AND e.store_id IS DISTINCT FROM o.store_id)"
        "    OR (s.channel = 'online' AND o.employee_id IS NOT NULL)"
    ).fetchone()
    assert bad == 0


def test_payment_amount_equals_discounted_line_total(wh_admin: psycopg.Connection) -> None:
    (mismatches,) = wh_admin.execute(
        "SELECT count(*) FROM payments p JOIN ("
        "  SELECT order_id, sum(quantity * unit_price * (1 - discount)) AS total"
        "  FROM order_items GROUP BY order_id) t USING (order_id)"
        " WHERE t.total <> p.amount"
    ).fetchone()
    assert mismatches == 0


def test_cancelled_orders_have_no_payment_and_returned_orders_have_a_return(
    wh_admin: psycopg.Connection,
) -> None:
    (paid_cancelled,) = wh_admin.execute(
        "SELECT count(*) FROM orders o JOIN payments p USING (order_id) WHERE o.status = 'cancelled'"
    ).fetchone()
    (returned_without_row,) = wh_admin.execute(
        "SELECT count(*) FROM orders o WHERE o.status = 'returned'"
        " AND NOT EXISTS (SELECT 1 FROM returns r WHERE r.order_id = o.order_id)"
    ).fetchone()
    assert paid_cancelled == 0
    assert returned_without_row == 0


def test_singles_day_shows_a_sales_spike(wh_admin: psycopg.Connection) -> None:
    daily = [n for (n,) in wh_admin.execute(f"SELECT count(*) FROM orders GROUP BY {LOCAL_DATE}")]
    (singles_day,) = wh_admin.execute(
        f"SELECT count(*) FROM orders WHERE {LOCAL_DATE} = %s", (date(2025, 11, 11),)
    ).fetchone()
    assert singles_day > 2 * median(daily)


def test_vietnamese_text_round_trips(wh_admin: psycopg.Connection) -> None:
    (name,) = wh_admin.execute("SELECT name FROM regions WHERE region_id = 5").fetchone()
    assert name == "Đông Nam Bộ"


def test_bootstrap_twice_does_not_duplicate_rows(
    pg_settings: Settings, seeded_warehouse: dict[str, int]
) -> None:
    again = bootstrap_warehouse(pg_settings, scale=pg_settings.warehouse_seed_scale)
    assert again == seeded_warehouse


def test_every_event_timestamp_stays_inside_business_period(wh_admin: psycopg.Connection) -> None:
    for table, column in (("orders", "order_date"), ("payments", "paid_at"),
                          ("returns", "returned_at")):  # fmt: skip
        (latest,) = wh_admin.execute(
            f"SELECT max(({column} AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) FROM {table}"
        ).fetchone()
        assert latest <= PERIOD_END, (table, latest)
