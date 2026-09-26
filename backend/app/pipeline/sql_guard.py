"""L3 guardrail: static SQL analysis with sqlglot.

Exactly one read-only SELECT/WITH statement, relations and columns from the role's
allowlist, no catalog/admin functions, and a LIMIT no larger than `max_rows`. The SQL
returned for execution is re-rendered from the AST, so comments cannot smuggle anything.
"""

import logging
import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.semantic.loader import SemanticLayer, load_semantic_layer

logging.getLogger("sqlglot").setLevel(logging.ERROR)

MAX_ROWS = 1000

# Hard blocks: an attempt to do something a read-only BI query never needs.
HARD_BLOCK = frozenset({"NON_SELECT", "MULTI_STATEMENT", "FORBIDDEN_OBJECT"})
# Mistakes an LLM can fix when shown the error (repair loop), rejected if they persist.
REPAIRABLE = frozenset({"SYNTAX_ERROR", "UNKNOWN_TABLE", "TABLE_NOT_ALLOWED", "COLUMN_NOT_ALLOWED"})

_WRITE_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
    exp.Command, exp.Copy, exp.Set, exp.TruncateTable, exp.Into, exp.Lock, exp.Grant,
    exp.Revoke, exp.Transaction, exp.Commit, exp.Rollback, exp.Use, exp.Analyze,
    exp.Pragma, exp.Execute, exp.Comment, exp.LoadData, exp.Cache, exp.Refresh,
)  # fmt: skip
_FORBIDDEN_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink", "file_", "xpath")
_FORBIDDEN_FUNCTIONS = frozenset({
    "set_config", "current_setting", "query_to_xml", "query_to_xml_and_xmlschema",
    "table_to_xml", "database_to_xml", "schema_to_xml", "cursor_to_xml", "txid_current",
    "version", "inet_server_addr", "inet_client_addr", "has_table_privilege",
    "has_column_privilege", "has_database_privilege", "to_regclass", "to_regproc",
})  # fmt: skip
_FORBIDDEN_FUNCTION_NODES: tuple[type[exp.Expression], ...] = (exp.CurrentVersion,)
_FORBIDDEN_SCHEMAS = frozenset({"pg_catalog", "information_schema", "pg_toast"})
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


@dataclass
class SqlCheck:
    ok: bool
    sql: str | None = None
    code: str | None = None
    message: str | None = None
    tables: list[str] = field(default_factory=list)
    pii_columns: list[str] = field(default_factory=list)

    @property
    def hard_block(self) -> bool:
        return self.code in HARD_BLOCK


def clean_sql(raw: str) -> str:
    """Strip markdown fences, whitespace and trailing semicolons an LLM tends to add."""
    text = _FENCE.sub("", raw.strip()).strip()
    while text.endswith(";"):
        text = text[:-1].rstrip()
    return text


def _fail(code: str, message: str) -> SqlCheck:
    return SqlCheck(ok=False, code=code, message=message)


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    return node.sql_name().lower()


def validate_sql(
    raw: str, role: str, layer: SemanticLayer | None = None, max_rows: int = MAX_ROWS
) -> SqlCheck:
    layer = layer or load_semantic_layer()
    text = clean_sql(raw)
    if not text:
        return _fail("SYNTAX_ERROR", "empty SQL")
    if ";" in text:
        return _fail("MULTI_STATEMENT", "only one statement is allowed")
    try:
        statements = [s for s in sqlglot.parse(text, read="postgres") if s is not None]
    except SqlglotError as error:
        return _fail("SYNTAX_ERROR", str(error).splitlines()[0][:300])
    if len(statements) != 1:
        return _fail("MULTI_STATEMENT", "only one statement is allowed")
    root = statements[0]
    if not isinstance(root, exp.Select | exp.SetOperation):
        if isinstance(root, _WRITE_NODES):
            return _fail("NON_SELECT", f"only SELECT is allowed, got {root.key.upper()}")
        return _fail("SYNTAX_ERROR", "not a valid SELECT statement")
    for node in root.walk():
        if isinstance(node, _WRITE_NODES):
            return _fail("NON_SELECT", f"{node.key.upper()} is not allowed")

    for func in root.find_all(exp.Func):
        name = _function_name(func)
        if (
            isinstance(func, _FORBIDDEN_FUNCTION_NODES)
            or name in _FORBIDDEN_FUNCTIONS
            or name.startswith(_FORBIDDEN_FUNCTION_PREFIXES)
        ):
            return _fail("FORBIDDEN_OBJECT", f"function {name}() is not allowed")

    cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
    allowed = layer.allowed_tables(role)
    aliases: dict[str, str] = {}
    relations: list[str] = []
    for table in root.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            continue  # table function (generate_series, …); vetted by the function check
        name = table.name.lower()
        schema = table.db.lower()
        if schema in _FORBIDDEN_SCHEMAS or name.startswith("pg_") or schema.startswith("pg_"):
            return _fail("FORBIDDEN_OBJECT", f"system catalog {table.sql()} is not allowed")
        if table.catalog or schema not in ("", "public"):
            return _fail("FORBIDDEN_OBJECT", f"schema {schema} is not allowed")
        if not schema and name in cte_names:
            continue
        if name not in layer.tables:
            return _fail("UNKNOWN_TABLE", f"unknown table {name}")
        if name not in allowed:
            hint = layer.tables[name].viewer_via
            suffix = f"; use {hint}" if hint else ""
            return _fail("TABLE_NOT_ALLOWED", f"table {name} is not allowed for {role}{suffix}")
        aliases[table.alias_or_name.lower()] = name
        if name not in relations:
            relations.append(name)

    pii: set[str] = set()
    pii_by_relation = {
        name: {c for c, col in table.columns.items() if col.pii}
        for name, table in layer.tables.items()
    }
    for column in root.find_all(exp.Column):
        qualifier = column.table.lower()
        name = column.name.lower()
        if qualifier:
            relation = aliases.get(qualifier)
            if relation is None:
                continue  # CTE or subquery alias
            if isinstance(column.this, exp.Star):
                pii |= {f"{relation}.{c}" for c in pii_by_relation[relation]}
            elif name not in layer.tables[relation].columns:
                return _fail("COLUMN_NOT_ALLOWED", f"column {relation}.{name} is not allowed")
            elif name in pii_by_relation[relation]:
                pii.add(f"{relation}.{name}")
        else:
            pii |= {f"{r}.{name}" for r in relations if name in pii_by_relation[r]}
    if any(isinstance(star.parent, exp.Select) for star in root.find_all(exp.Star)):
        for relation in relations:
            pii |= {f"{relation}.{c}" for c in pii_by_relation[relation]}

    limited = _enforce_limit(root, max_rows)
    return SqlCheck(
        ok=True,
        sql=limited.sql(dialect="postgres", comments=False),
        tables=relations,
        pii_columns=sorted(pii),
    )


def _enforce_limit(root: exp.Expression, max_rows: int) -> exp.Expression:
    limit = root.args.get("limit")
    if limit is None:
        return (
            root.limit(max_rows, copy=False)
            if isinstance(root, exp.Select)
            else _wrap(root, max_rows)
        )
    if isinstance(limit, exp.Fetch):
        count = limit.args.get("count")
        keep = isinstance(count, exp.Literal) and count.is_int and int(count.this) <= max_rows
        root.set("limit", exp.Limit(expression=count if keep else exp.Literal.number(max_rows)))
        return root
    value = limit.expression
    if isinstance(value, exp.Literal) and value.is_int and int(value.this) <= max_rows:
        return root
    limit.set("expression", exp.Literal.number(max_rows))
    return root


def _wrap(root: exp.Expression, max_rows: int) -> exp.Expression:
    """UNION/INTERSECT without LIMIT: attach one to the set operation itself."""
    root.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
    return root
