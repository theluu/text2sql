import math
from pathlib import Path

import pytest
import sqlglot
from sqlglot import exp

from app.core.text import normalize, strip_accents
from app.semantic.embedder import HashingEmbedder
from app.semantic.linker import SchemaLinker, render_schema
from app.semantic.loader import load_semantic_layer

SCHEMA_DIR = Path("app/warehouse/schema")
LAYER = load_semantic_layer()


def _ddl_columns() -> dict[str, set[str]]:
    columns: dict[str, set[str]] = {}
    for statement in sqlglot.parse((SCHEMA_DIR / "01_tables.sql").read_text(), read="postgres"):
        if isinstance(statement, exp.Create) and statement.kind == "TABLE":
            schema = statement.this
            name = schema.this.name
            columns[name] = {c.name for c in schema.expressions if isinstance(c, exp.ColumnDef)}
    return columns


def test_every_semantic_column_exists_in_the_warehouse_ddl() -> None:
    ddl = _ddl_columns()
    base_tables = {n: t for n, t in LAYER.tables.items() if not t.is_view}
    assert set(base_tables) == set(ddl)
    for name, table in base_tables.items():
        assert set(table.columns) == ddl[name], name


def test_masked_views_match_view_ddl_and_hide_raw_pii() -> None:
    views_sql = (SCHEMA_DIR / "02_views.sql").read_text()
    for view in ("v_customers_masked", "v_employees_masked"):
        assert view in views_sql
    assert "salary" not in LAYER.tables["v_employees_masked"].columns
    assert "address" not in LAYER.tables["v_customers_masked"].columns


def test_role_allowlists() -> None:
    viewer = LAYER.allowed_tables("viewer")
    assert {"customers", "employees"}.isdisjoint(viewer)
    assert {"v_customers_masked", "v_employees_masked", "orders"} <= viewer
    assert {"customers", "employees"} <= LAYER.allowed_tables("analyst")
    assert LAYER.visible_name("customers", "viewer") == "v_customers_masked"
    assert LAYER.visible_name("customers", "admin") == "customers"
    assert ("customers", "email") in LAYER.pii_columns()


def test_text_normalization() -> None:
    assert strip_accents("Đồng bằng sông Hồng") == "Dong bang song Hong"
    assert normalize("Doanh thu, THÁNG 7!") == "doanh thu thang 7"


def test_hashing_embedder_is_deterministic_unit_length() -> None:
    embedder = HashingEmbedder()
    a, b = embedder.embed_one("doanh thu khu vực"), embedder.embed_one("doanh thu khu vực")
    assert a == b
    assert len(a) == 1024
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-9)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Doanh thu theo khu vực quý này", {"orders", "order_items", "regions", "stores"}),
        ("doanh thu tung cua hang thang 7", {"orders", "order_items", "stores"}),
        ("Những cửa hàng nào có tồn kho dưới mức đặt lại?", {"inventory", "stores"}),
        ("Tỷ lệ hoàn hàng theo danh mục năm 2025", {"orders", "categories"}),
        ("average order value by payment method", {"orders", "payments"}),
        ("revenue by category last quarter", {"categories", "products", "order_items"}),
    ],
)
async def test_linker_recalls_needed_tables(question: str, expected: set[str]) -> None:
    linked = await SchemaLinker(LAYER, HashingEmbedder()).link(None, question)
    assert expected <= set(linked.tables)
    assert len(linked.tables) <= 9


async def test_render_schema_uses_masked_views_for_viewers() -> None:
    linked = await SchemaLinker(LAYER, HashingEmbedder()).link(None, "email khách hàng")
    viewer_block = render_schema(LAYER, linked, "viewer")
    assert "TABLE v_customers_masked" in viewer_block
    assert "TABLE customers " not in viewer_block
    assert "TABLE customers " in render_schema(LAYER, linked, "analyst")
