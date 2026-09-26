"""Run validated SQL on the warehouse as the caller's read-only DB role."""

import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import errors

from app.core.config import Settings, WarehouseRole

DEFAULT_TIMEOUT_MS = 10_000


class WarehouseError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool = False
    duration_ms: int = 0
    column_types: list[str] = field(default_factory=list)

    def preview(self, limit: int) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "column_types": self.column_types,
            "rows": self.rows[:limit],
            "row_count": self.row_count,
            "truncated": self.truncated or self.row_count > limit,
        }


def warehouse_role(user_role: str) -> WarehouseRole:
    """Viewers get the masked-view role; analysts and admins read raw tables."""
    return "viewer" if user_role == "viewer" else "analyst"


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bytes | memoryview):
        return None
    if isinstance(value, list | tuple):
        return [_json_value(v) for v in value]
    return value


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float | Decimal):
        return "number"
    if isinstance(value, datetime | date):
        return "date"
    return "text"


def _column_types(rows: list[tuple[Any, ...]], width: int) -> list[str]:
    kinds: list[str] = []
    for index in range(width):
        sample = next((r[index] for r in rows if r[index] is not None), None)
        kinds.append(_kind(sample) if sample is not None else "text")
    return kinds


async def _connect(settings: Settings, role: str, timeout_ms: int) -> psycopg.AsyncConnection[Any]:
    conn = await psycopg.AsyncConnection.connect(
        settings.warehouse_dsn(warehouse_role(role)),
        options=f"-c statement_timeout={int(timeout_ms)}",
        connect_timeout=5,
    )
    await conn.set_read_only(True)
    return conn


def _translate(error: psycopg.Error) -> WarehouseError:
    message = (str(error).strip().splitlines() or [""])[0][:300]
    if isinstance(error, errors.QueryCanceled):
        return WarehouseError("DB_TIMEOUT", "query exceeded the time limit")
    if isinstance(error, errors.InsufficientPrivilege | errors.ReadOnlySqlTransaction):
        return WarehouseError("DB_PERMISSION", message)
    return WarehouseError("DB_ERROR", message)


async def run_query(
    settings: Settings,
    role: str,
    sql: str,
    *,
    max_rows: int = 1000,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> QueryResult:
    started = time.perf_counter()
    try:
        async with await _connect(settings, role, timeout_ms) as conn, conn.cursor() as cur:
            await cur.execute(sql)  # type: ignore[arg-type]  # validated, re-rendered SQL
            columns = [d.name for d in cur.description or []]
            raw = await cur.fetchmany(max_rows + 1)
    except psycopg.OperationalError as error:
        if isinstance(error, errors.QueryCanceled):
            raise _translate(error) from error
        raise WarehouseError("DB_UNAVAILABLE", "warehouse is unreachable") from error
    except psycopg.Error as error:
        raise _translate(error) from error
    truncated = len(raw) > max_rows
    raw = raw[:max_rows]
    return QueryResult(
        columns=columns,
        rows=[[_json_value(v) for v in row] for row in raw],
        row_count=len(raw),
        truncated=truncated,
        duration_ms=int((time.perf_counter() - started) * 1000),
        column_types=_column_types(raw, len(columns)),
    )


async def explain_cost(settings: Settings, role: str, sql: str) -> float:
    """Planner's total cost estimate (no execution)."""
    try:
        async with await _connect(settings, role, DEFAULT_TIMEOUT_MS) as conn, conn.cursor() as cur:
            await cur.execute(f"EXPLAIN (FORMAT JSON) {sql}")  # type: ignore[arg-type]
            row = await cur.fetchone()
    except psycopg.OperationalError as error:
        if isinstance(error, errors.QueryCanceled):
            raise _translate(error) from error
        raise WarehouseError("DB_UNAVAILABLE", "warehouse is unreachable") from error
    except psycopg.Error as error:
        raise _translate(error) from error
    plan = row[0] if row else [{}]
    return float(plan[0]["Plan"]["Total Cost"])
