"""Result-set comparison for Execution Accuracy (EX) and self-consistency.

Rows are compared as a multiset (as a list when order matters). Column names and column
order do not matter; numbers match within 1e-6 relative tolerance.
"""

import math
from collections import Counter
from collections.abc import Sequence
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.normalize import normalize as normalize_bool


def _value(value: Any) -> str:
    if value is None:
        return "∅"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        number = float(value)
        if math.isnan(number):
            return "nan"
        # 1e-6 relative tolerance ≈ agreement on 7 significant digits
        return f"{number:.6e}" if number else "0"
    text = str(value)
    try:
        return _value(float(text))
    except ValueError:
        return text.strip()


def _row(row: Sequence[Any]) -> tuple[str, ...]:
    return tuple(sorted(_value(v) for v in row))


def results_match(
    gold: Sequence[Sequence[Any]], predicted: Sequence[Sequence[Any]], *, ordered: bool = False
) -> bool:
    if len(gold) != len(predicted):
        return False
    gold_rows = [_row(r) for r in gold]
    pred_rows = [_row(r) for r in predicted]
    if ordered:
        return gold_rows == pred_rows
    return Counter(gold_rows) == Counter(pred_rows)


def has_order_by(sql: str) -> bool:
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except SqlglotError:
        return False
    return tree.args.get("order") is not None


def exact_structure_match(gold_sql: str, predicted_sql: str) -> bool:
    """ESM: normalized ASTs equal (aliases, casing and formatting ignored)."""
    try:
        return _canonical(gold_sql) == _canonical(predicted_sql)
    except SqlglotError:
        return False


def _canonical(sql: str) -> str:
    tree = sqlglot.parse_one(sql, read="postgres")
    tree = tree.transform(lambda n: n.this if isinstance(n, exp.Alias) else n)
    for table in tree.find_all(exp.Table):
        table.set("alias", None)
    for column in tree.find_all(exp.Column):
        column.set("table", None)
    limit = tree.args.get("limit")
    if limit is not None:
        tree.set("limit", None)
    return normalize_bool(tree).sql(dialect="postgres", normalize=True, comments=False).lower()
