"""LLM SQL generation (with repair and alternative-candidate modes) and rule-based fallback."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.llm import rule_based
from app.llm.base import Message
from app.llm.router import LLMRouter, Routed
from app.pipeline.context import Candidate
from app.pipeline.prompts import GENERATE_SCHEMA, GENERATE_SYSTEM, REWRITE_SCHEMA, REWRITE_SYSTEM


@dataclass
class Repair:
    sql: str
    error: str


def _examples_block(fewshots: list[dict[str, Any]]) -> str:
    if not fewshots:
        return ""
    lines = [f"Q: {e['question']}\nSQL: {e['sql']}" for e in fewshots]
    return (
        "<examples>\nVerified question/SQL pairs for this database:\n"
        + "\n\n".join(lines)
        + "\n</examples>\n"
    )


def build_messages(
    *,
    question: str,
    schema_text: str,
    fewshots: list[dict[str, Any]],
    role: str,
    as_of: date,
    repair: Repair | None = None,
    alternative: int | None = None,
) -> list[Message]:
    access = (
        "The user's role reads customers and employees only through the masked views shown in <schema>."
        if role == "viewer"
        else "The user's role may read every table in <schema>."
    )
    user = f"<schema>\n{schema_text}\n</schema>\n{_examples_block(fewshots)}{access}\n<question>{question}</question>"
    if repair:
        user += (
            f"\n<previous_attempt>\n{repair.sql}\n</previous_attempt>\n"
            f"That SQL failed with: {repair.error}\nReturn a corrected query."
        )
    if alternative:
        user += (
            f"\nWrite an independent formulation of the query (variant #{alternative}): reason from "
            "scratch rather than reusing a single obvious shape."
        )
    return [
        Message("system", GENERATE_SYSTEM.format(as_of=as_of.isoformat())),
        Message("user", user),
    ]


def candidate_from(routed: Routed) -> Candidate:
    content = routed.response.content
    try:
        confidence = float(content.get("self_confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    return Candidate(
        sql=str(content.get("sql") or "").strip(),
        explanation=str(content.get("explanation") or ""),
        self_confidence=min(max(confidence, 0.0), 1.0),
        source="llm",
        provider=routed.response.provider,
        vendor=routed.response.vendor,
        model=routed.response.model,
    )


async def generate(router: LLMRouter, messages: list[Message], purpose: str = "generate",
                   only: str | None = None) -> Routed:  # fmt: skip
    return await router.complete(
        purpose, messages, schema=GENERATE_SCHEMA, schema_name="sql_candidate", only=only
    )


def fallback(question: str, role: str, as_of: date) -> Candidate | None:
    found = rule_based.match(question, role, as_of)
    if found is None:
        return None
    return Candidate(
        sql=found.sql,
        explanation=found.explanation,
        self_confidence=found.confidence,
        source="rule_based",
        provider="rule_based",
        intent=found.intent,
        params=found.params,
    )


async def rewrite(
    router: LLMRouter, question: str, history: list[tuple[str, str | None]]
) -> Routed:
    turns = "\n".join(f"User: {q}" + (f"\nSQL: {sql}" if sql else "") for q, sql in history[-3:])
    return await router.complete(
        "rewrite",
        [Message("system", REWRITE_SYSTEM),
         Message("user", f"<history>\n{turns}\n</history>\n<question>{question}</question>")],
        schema=REWRITE_SCHEMA,
        schema_name="standalone_question",
    )  # fmt: skip
