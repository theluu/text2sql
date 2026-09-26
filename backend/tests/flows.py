"""Shared helpers for API flow tests (fake LLMs, asking over SSE, DB peeks)."""

import re
from collections.abc import Callable
from typing import Any

import httpx
import psycopg

from app.core.config import Settings
from app.llm.base import Message
from app.llm.fake import FakeLLMProvider
from tests.helpers import login_token, parse_sse, sync_dsn

REVENUE_2025 = (
    "SELECT ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount))) AS doanh_thu "
    "FROM orders o JOIN order_items oi ON oi.order_id = o.order_id "
    "WHERE o.status <> 'cancelled' AND o.order_date >= DATE '2025-01-01' AND o.order_date < DATE '2026-01-01'"
)
PASS = {
    "verdict": "pass", "score": 0.93, "issues": [], "suggested_fix": "",
    "rubric": {k: {"score": 5, "reason": "ok"} for k in
               ("intent", "schema_selection", "joins_filters", "aggregation", "result_sanity")},
}  # fmt: skip

Script = Callable[[str, str], dict[str, Any]]


def question_of(messages: list[Message]) -> str:
    match = re.search(r"<question>(.*?)</question>", messages[-1].content, re.S)
    return match.group(1) if match else ""


def llm(name: str, vendor: str, answer: Script) -> FakeLLMProvider:
    def step(messages: list[Message], schema: str) -> dict[str, Any]:
        if schema == "judge_verdict":
            return PASS
        if schema == "question_screen":
            return {"category": "in_scope", "reason": ""}
        if schema == "standalone_question":
            return {"question": "doanh thu năm 2025 theo khu vực"}
        return answer(question_of(messages), messages[-1].content)

    return FakeLLMProvider(name, vendor, [step])


def sql_answer(sql: str, confidence: float = 0.9) -> Script:
    return lambda q, prompt: {
        "sql": sql,
        "explanation": "Tổng doanh thu 2025.",
        "self_confidence": confidence,
    }


async def ask(
    client: httpx.AsyncClient, email: str, question: str, conversation_id: str | None = None
) -> tuple[list[tuple[str, dict[str, Any]]], dict[str, Any]]:
    token = await login_token(client, email)
    body: dict[str, Any] = {"question": question}
    if conversation_id:
        body["conversation_id"] = conversation_id
    response = await client.post(
        "/api/query", json=body, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    results = [data for name, data in events if name == "result"]
    assert results, events
    return events, results[0]  # type: ignore[return-value]


def db(settings: Settings, sql: str) -> list[tuple[Any, ...]]:
    with psycopg.connect(sync_dsn(settings.app_db_url)) as conn:
        return conn.execute(sql).fetchall()  # type: ignore[arg-type]
