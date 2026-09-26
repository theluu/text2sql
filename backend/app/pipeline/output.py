"""L5 output shaping: role-based masking, deterministic summary, chart suggestion."""

import re
from typing import Any

from app.warehouse.executor import QueryResult

PII_COLUMN = re.compile(r"email|phone|dien_thoai|sdt|address|dia_chi|salary|luong", re.I)
TIME_COLUMN = re.compile(
    r"^(month|thang|day|ngay|date|quarter|quy|year|nam|week|tuan|period|ky)\b|_(date|month|day|at|on)$",
    re.I,
)
TIME_VALUE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?|-Q[1-4])")


def _mask_value(column: str, value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    if "email" in column.lower() and "@" in text:
        return "***@" + text.split("@", 1)[1]
    if re.search(r"phone|dien_thoai|sdt", column, re.I):
        return "***" + text[-3:]
    return "***"


def mask_result(result: QueryResult, role: str) -> list[str]:
    """Defense in depth on top of the masked views: viewers never see raw PII-named columns."""
    if role != "viewer":
        return []
    masked = [c for c in result.columns if PII_COLUMN.search(c)]
    if not masked:
        return []
    indexes = [result.columns.index(c) for c in masked]
    for row in result.rows:
        for i in indexes:
            row[i] = _mask_value(result.columns[i], row[i])
    return masked


def humanize(column: str) -> str:
    """ty_le_hoan_pct -> "ty le hoan (%)" — readable without a label dictionary."""
    text = column.replace("_", " ").strip()
    return re.sub(r" pct$", " (%)", text)


def fmt_number(value: float | int, lang: str) -> str:
    text = (
        f"{value:,.2f}"
        if isinstance(value, float) and not value.is_integer()
        else f"{int(value):,}"
    )
    return text.translate(str.maketrans(",.", ".,")) if lang == "vi" else text


def _fmt(value: Any, lang: str) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | float):
        return fmt_number(value, lang)
    return "—" if value is None else str(value)


def _numeric_columns(result: QueryResult) -> list[int]:
    return [i for i, kind in enumerate(result.column_types) if kind == "number"]


def _is_time(result: QueryResult, index: int) -> bool:
    if result.column_types[index] == "date" or TIME_COLUMN.search(result.columns[index]):
        return True
    sample = next((r[index] for r in result.rows if r[index] is not None), None)
    return isinstance(sample, str) and bool(TIME_VALUE.match(sample))


def chart_spec(result: QueryResult) -> dict[str, Any]:
    if result.row_count == 0 or not result.columns:
        return {"type": "empty"}
    numeric = _numeric_columns(result)
    if result.row_count == 1 and len(result.columns) == 1 and numeric:
        return {"type": "kpi", "value": result.columns[0]}
    labels = [i for i in range(len(result.columns)) if i not in numeric]
    if not labels or not numeric:
        return {"type": "table"}
    time_labels = [i for i in labels if _is_time(result, i)]
    label = time_labels[0] if time_labels else labels[0]
    x, y = result.columns[label], [result.columns[i] for i in numeric][:3]
    series = _series_column(result, [i for i in labels if i != label])
    if series is not None:
        # Long format (month, channel, revenue): one series per channel, not one zig-zag line.
        chart_type = "line" if label in time_labels else "bar"
        return {"type": chart_type, "x": x, "y": y[:1], "series": result.columns[series]}
    if label in time_labels and result.row_count >= 2:
        return {"type": "line", "x": x, "y": y}
    if result.row_count <= 30:
        longest = max(len(str(r[label])) for r in result.rows)
        return {"type": "bar", "x": x, "y": y[:2], "horizontal": longest > 14}
    return {"type": "table"}


MAX_SERIES = 3  # the validated chart palette has three categorical slots


def _series_column(result: QueryResult, candidates: list[int]) -> int | None:
    for index in candidates:
        distinct = {row[index] for row in result.rows}
        if 2 <= len(distinct) <= MAX_SERIES:
            return index
    return None


def summarize(result: QueryResult, lang: str) -> str:
    vi = lang == "vi"
    if result.row_count == 0:
        return "Không có dữ liệu phù hợp với câu hỏi." if vi else "No data matches the question."
    numeric = _numeric_columns(result)
    if result.row_count == 1:
        row = result.rows[0]
        if len(row) == 1:
            if row[0] is None:
                return (
                    "Không có dữ liệu phù hợp với câu hỏi."
                    if vi
                    else "No data matches the question."
                )
            return f"{humanize(result.columns[0])}: {_fmt(row[0], lang)}"
        return "; ".join(
            f"{humanize(c)}: {_fmt(v, lang)}"
            for c, v in list(zip(result.columns, row, strict=True))[:5]
        )
    rows_text = (f"{result.row_count} dòng" if vi else f"{result.row_count} rows") + (
        (" (đã giới hạn)" if vi else " (truncated)") if result.truncated else ""
    )
    labels = [i for i in range(len(result.columns)) if i not in numeric]
    time_labels = [i for i in labels if _is_time(result, i)]
    label = time_labels[0] if time_labels else (labels[0] if labels else None)
    metric = next((i for i in numeric if i != label), None)
    if label is None or metric is None:
        return rows_text + "."
    series = _series_column(result, [i for i in labels if i != label]) if time_labels else None
    if series is not None:
        # Long format: first → last per series, never across series.
        parts = []
        for name in dict.fromkeys(row[series] for row in result.rows):
            points = [
                r for r in result.rows if r[series] == name and isinstance(r[metric], int | float)
            ]
            if not points:
                continue
            first, last = points[0][metric], points[-1][metric]
            change = f" ({(last - first) / first * 100:+.1f}%)" if first else ""
            parts.append(f"{name} {_fmt(first, lang)} → {_fmt(last, lang)}{change}")
        span = f"{_fmt(result.rows[0][label], lang)} → {_fmt(result.rows[-1][label], lang)}"
        return f"{rows_text}. {humanize(result.columns[metric])}, {span}: " + "; ".join(parts) + "."
    values = [(r[label], r[metric]) for r in result.rows if isinstance(r[metric], int | float)]
    if not values:
        return rows_text + "."
    name = humanize(result.columns[metric])
    if _is_time(result, label):
        (first_label, first), (last_label, last) = values[0], values[-1]
        change = f" ({(last - first) / first * 100:+.1f}%)" if first else ""
        return (
            f"{rows_text}. {name}: {_fmt(first_label, lang)} → {_fmt(last_label, lang)}: "
            f"{_fmt(first, lang)} → {_fmt(last, lang)}{change}."
        )
    top = max(values, key=lambda v: v[1])
    bottom = min(values, key=lambda v: v[1])
    high, low = ("cao nhất", "thấp nhất") if vi else ("highest", "lowest")
    return (
        f"{rows_text}. {name} {high}: {_fmt(top[0], lang)} ({_fmt(top[1], lang)}); "
        f"{low}: {_fmt(bottom[0], lang)} ({_fmt(bottom[1], lang)})."
    )
