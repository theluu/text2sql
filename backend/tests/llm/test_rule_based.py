from datetime import date

import pytest

from app.core.config import Settings
from app.llm.rule_based import detect_lang, match
from app.pipeline.sql_guard import validate_sql
from app.warehouse.executor import run_query

AS_OF = date(2026, 8, 31)

CASES: list[tuple[str, str, dict[str, object]]] = [
    (
        "Doanh thu theo khu vực trong quý này so với quý trước?",
        "revenue_compare_by_region",
        {"dimension": "region"},
    ),
    ("Top 10 sản phẩm bán chạy nhất tháng trước", "top_units_by_product", {"top": 10}),
    ("Những cửa hàng nào có tồn kho dưới mức đặt lại?", "low_stock_by_store", {}),
    ("sản phẩm sắp hết hàng", "low_stock_items", {}),
    (
        "Tỷ lệ hoàn hàng theo danh mục năm 2025",
        "return_rate_by_category",
        {"metric": "return_rate"},
    ),
    ("Doanh thu theo tháng năm nay", "revenue_by_month", {"dimension": "month"}),
    (
        "doanh thu thang 7 khu vuc dong nam bo",
        "revenue_total",
        {"filters": [{"dimension": "region", "value": "Đông Nam Bộ"}]},
    ),
    ("How many orders last month?", "orders_total", {"lang": "en"}),
    ("average order value by channel this year", "aov_by_channel", {}),
    ("revenue by payment method in 2025", "revenue_by_payment_method", {}),
    ("top 5 customers by revenue", "top_revenue_by_customer", {"top": 5}),
    ("lý do trả hàng phổ biến", "return_reasons", {}),
    ("số khách hàng mới theo tháng năm 2025", "new_customers_by_month", {}),
    (
        "doanh thu điện thoại quý 2",
        "revenue_total",
        {"filters": [{"dimension": "category", "value": "Điện thoại"}]},
    ),
    ("lợi nhuận gộp theo thương hiệu", "margin_by_brand", {}),
    (
        "doanh thu Hà Nội tháng này",
        "revenue_total",
        {"filters": [{"dimension": "city", "value": "Hà Nội"}]},
    ),
    ("số đơn theo trạng thái", "orders_by_status", {}),
    ("tăng trưởng doanh thu tháng này so với cùng kỳ năm trước", "revenue_compare", {}),
    ("doanh thu theo quý năm 2025", "revenue_by_quarter", {}),
    (
        "doanh thu online năm nay",
        "revenue_total",
        {"filters": [{"dimension": "channel", "value": "online"}]},
    ),
    (
        "5 cửa hàng có doanh thu thấp nhất năm 2025",
        "top_revenue_by_store",
        {"order": "asc", "top": 5},
    ),
    (
        "doanh thu khách hàng gold theo tháng",
        "revenue_by_month",
        {"filters": [{"dimension": "segment", "value": "gold"}]},
    ),
    (
        "doanh thu thoi trang nam nam ngoai",
        "revenue_total",
        {"filters": [{"dimension": "category", "value": "Thời trang nam"}]},
    ),
    (
        "doanh thu dien thaoi",
        "revenue_total",
        {"filters": [{"dimension": "category", "value": "Điện thoại"}]},
    ),  # typo
    ("tồn kho theo danh mục", "inventory_by_category", {}),
    ("doanh thu từng chương trình khuyến mãi năm 2025", "revenue_by_promotion", {}),
    ("số nhân viên mỗi cửa hàng", "employees_by_store", {}),
]


@pytest.mark.parametrize(("question", "intent", "params"), CASES)
def test_intents_and_params(question: str, intent: str, params: dict[str, object]) -> None:
    found = match(question, "viewer", AS_OF)
    assert found is not None, question
    assert found.intent == intent
    for key, value in params.items():
        assert found.params[key] == value, key
    assert validate_sql(found.sql, "viewer").ok, found.sql


def test_intent_count_is_at_least_twenty_five() -> None:
    assert len({intent for _, intent, _ in CASES}) >= 20
    assert len(CASES) >= 25


@pytest.mark.parametrize(
    "question",
    [
        "viết bài thơ về mùa thu",
        "lương trung bình nhân viên",
        "email của khách hàng",
        "tại sao doanh thu giảm",
        "",
        "hello",
    ],
)
def test_unhandled_questions_return_none(question: str) -> None:
    assert match(question, "viewer", AS_OF) is None


def test_fuzzy_entities_lower_confidence() -> None:
    exact = match("doanh thu dien thoai", "viewer", AS_OF)
    typo = match("doanh thu dien thaoi", "viewer", AS_OF)
    assert exact and typo and typo.confidence < exact.confidence
    assert typo.confidence < 0.9


def test_guessing_the_metric_is_below_review_threshold() -> None:
    guessed = match("theo khu vực năm 2025", "viewer", AS_OF)
    assert guessed is not None and guessed.confidence < 0.8


def test_viewer_customer_queries_use_masked_view() -> None:
    viewer = match("top 5 customers by revenue", "viewer", AS_OF)
    analyst = match("top 5 customers by revenue", "analyst", AS_OF)
    assert viewer and "v_customers_masked" in viewer.sql
    assert analyst and "JOIN customers cu" in analyst.sql


def test_language_detection() -> None:
    assert detect_lang("Doanh thu tháng này") == "vi"
    assert detect_lang("doanh thu thang nay") == "vi"
    assert detect_lang("revenue this month") == "en"


@pytest.mark.usefixtures("seeded_warehouse")
async def test_every_template_runs_on_the_warehouse(pg_settings: Settings) -> None:
    for question, _, _ in CASES:
        for role in ("viewer", "analyst"):
            found = match(question, role, AS_OF)
            assert found is not None
            check = validate_sql(found.sql, role)
            assert check.ok and check.sql
            result = await run_query(pg_settings, role, check.sql)
            assert result.columns, question


@pytest.mark.usefixtures("seeded_warehouse")
async def test_revenue_template_matches_hand_written_sql(pg_settings: Settings) -> None:
    found = match("doanh thu năm 2025", "viewer", AS_OF)
    assert found
    auto = await run_query(pg_settings, "viewer", found.sql)
    manual = await run_query(
        pg_settings,
        "viewer",
        "SELECT ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount))) FROM orders o "
        "JOIN order_items oi USING (order_id) WHERE o.status <> 'cancelled' "
        "AND o.order_date >= '2025-01-01' AND o.order_date < '2026-01-01'",
    )
    assert auto.rows == manual.rows
