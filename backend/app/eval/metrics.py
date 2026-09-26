"""Aggregate eval results into the harness KPIs."""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.semantic.loader import load_semantic_layer


@dataclass
class CaseOutcome:
    key: str
    difficulty: str
    tags: list[str]
    expected: str  # answer | review | reject
    behavior: str  # answer | review | reject | fail
    ex: bool | None = None
    esm: bool | None = None
    judge_verdict: str | None = None
    gold_tables: list[str] = field(default_factory=list)
    linked_tables: list[str] = field(default_factory=list)
    latency_ms: int = 0
    cost_usd: float = 0.0
    failover: bool = False
    used_fallback: bool = False


def tables_in(sql: str | None) -> list[str]:
    """Base warehouse tables a SQL touches (masked views count as their base table)."""
    if not sql:
        return []
    layer = load_semantic_layer()
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except SqlglotError:
        return []
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    found: set[str] = set()
    for table in tree.find_all(exp.Table):
        name = table.name
        if name in ctes or name not in layer.tables:
            continue
        found.add(layer.tables[name].base or name)
    return sorted(found)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return float(ordered[index])


def cohen_kappa(a: list[bool], b: list[bool]) -> float | None:
    """Agreement beyond chance between two binary raters."""
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pa, pb = sum(a) / n, sum(b) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    if expected == 1:
        return 1.0 if observed == 1 else 0.0
    return round((observed - expected) / (1 - expected), 3)


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 4) if den else None


def summarize(outcomes: list[CaseOutcome]) -> dict[str, Any]:
    answerable = [o for o in outcomes if o.expected == "answer"]
    ex_values = [o.ex for o in answerable if o.ex is not None]
    adversarial = [o for o in outcomes if "adversarial" in o.tags]
    predicted_reject = [o for o in outcomes if o.behavior == "reject"]
    tp = sum(1 for o in adversarial if o.behavior == "reject")

    judged = [o for o in answerable if o.judge_verdict and o.ex is not None]
    judge_flags = [o.judge_verdict != "pass" for o in judged]
    wrong = [not o.ex for o in judged]
    flagged_wrong = sum(1 for f, w in zip(judge_flags, wrong, strict=True) if f and w)

    recalls = [
        len(set(o.gold_tables) & set(o.linked_tables)) / len(o.gold_tables)
        for o in answerable if o.gold_tables and o.linked_tables
    ]  # fmt: skip
    latencies = [float(o.latency_ms) for o in outcomes]

    def group(key: str) -> dict[str, dict[str, Any]]:
        buckets: dict[str, list[CaseOutcome]] = defaultdict(list)
        for o in outcomes:
            labels = [o.difficulty] if key == "difficulty" else o.tags
            for label in labels:
                buckets[label].append(o)
        return {
            label: {
                "n": len(items),
                "ex": _ratio(
                    sum(1 for i in items if i.ex), sum(1 for i in items if i.ex is not None)
                ),
                "behavior": _ratio(sum(1 for i in items if i.behavior == i.expected), len(items)),
            }
            for label, items in sorted(buckets.items())
        }

    return {
        "cases": len(outcomes),
        "ex": _ratio(sum(ex_values), len(ex_values)),
        "esm": _ratio(sum(1 for o in answerable if o.esm), len(answerable)),
        "behavior_accuracy": _ratio(
            sum(1 for o in outcomes if o.behavior == o.expected), len(outcomes)
        ),
        "guardrail_recall": _ratio(tp, len(adversarial)),
        "guardrail_precision": _ratio(tp, len(predicted_reject)),
        "adversarial_leaks": [o.key for o in adversarial if o.behavior != "reject"],
        "judge_precision": _ratio(flagged_wrong, sum(judge_flags)),
        "judge_recall": _ratio(flagged_wrong, sum(wrong)),
        "judge_kappa": cohen_kappa(judge_flags, wrong),
        "linking_recall": _ratio(sum(recalls), len(recalls)),
        "latency_p50_ms": percentile(latencies, 0.5),
        "latency_p95_ms": percentile(latencies, 0.95),
        "cost_per_query_usd": round(sum(o.cost_usd for o in outcomes) / len(outcomes), 6)
        if outcomes
        else 0.0,
        "failover_rate": _ratio(sum(1 for o in outcomes if o.failover), len(outcomes)),
        "fallback_rate": _ratio(sum(1 for o in outcomes if o.used_fallback), len(outcomes)),
        "by_difficulty": group("difficulty"),
        "by_tag": group("tag"),
    }
