import asyncio
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.hitl.notifications import Notifier
from tests.flows import REVENUE_2025, ask, db, llm, sql_answer
from tests.helpers import login_token

pytestmark = pytest.mark.usefixtures("clean_app_db")

PII_SQL = "SELECT full_name, email FROM v_customers_masked WHERE segment = 'platinum' ORDER BY customer_id LIMIT 5"
UNCERTAIN = {
    "verdict": "uncertain", "score": 0.5, "issues": ["ambiguous period"], "suggested_fix": "",
    "rubric": {k: {"score": 3, "reason": "?"} for k in
               ("intent", "schema_selection", "joins_filters", "aggregation", "result_sanity")},
}  # fmt: skip


async def headers(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {await login_token(client, email)}"}


async def pending_item(client: httpx.AsyncClient) -> dict[str, Any]:
    queue = (
        await client.get("/api/review", headers=await headers(client, "analyst@demo.vn"))
    ).json()
    assert queue["pending"] >= 1
    return queue["items"][0]  # type: ignore[no-any-return]


async def pii_setup(make_client: Any) -> tuple[httpx.AsyncClient, dict[str, Any]]:
    client = await make_client({"anthropic": llm("anthropic", "anthropic", sql_answer(PII_SQL)),
                                "openai": llm("openai", "openai", sql_answer(PII_SQL))})  # fmt: skip
    _, view = await ask(client, "viewer@demo.vn", "Email khách hàng platinum")
    assert view["status"] == "pending_review"
    return client, view


async def test_viewers_cannot_open_the_review_queue(make_client: Any) -> None:
    client = await make_client({})
    response = await client.get("/api/review", headers=await headers(client, "viewer@demo.vn"))
    assert response.status_code == 403


async def test_queue_detail_shows_reviewer_the_preview(make_client: Any) -> None:
    client, view = await pii_setup(make_client)
    item = await pending_item(client)
    assert item["run_id"] == view["id"] and item["reasons"] == ["PII_ACCESS"]
    assert item["asker"]["role"] == "viewer"
    detail = (
        await client.get(
            f"/api/review/{item['id']}", headers=await headers(client, "analyst@demo.vn")
        )
    ).json()
    assert detail["run"]["result"]["rows"]  # the reviewer sees what the viewer does not
    assert " ".join(detail["original_sql"].split()).startswith("SELECT full_name, email")


async def test_approve_reexecutes_as_the_asker_and_notifies(
    make_client: Any, pg_settings: Settings
) -> None:
    client, view = await pii_setup(make_client)
    item = await pending_item(client)
    analyst = await headers(client, "analyst@demo.vn")
    assert (await client.post(f"/api/review/{item['id']}/claim", headers=analyst)).json() == {
        "status": "claimed"
    }

    app_notifier: Notifier = client._transport.app.state.services.notifier  # type: ignore[attr-defined]
    received: list[dict[str, Any]] = []

    async def listen() -> None:
        async for event in app_notifier.subscribe(
            db(pg_settings, "SELECT id FROM users WHERE email='viewer@demo.vn'")[0][0],
            heartbeat_s=5,
        ):
            if event:
                received.append(event)
                return

    listener = asyncio.create_task(listen())
    await asyncio.sleep(0.05)
    response = await client.post(
        f"/api/review/{item['id']}/approve", json={"add_to_golden": True}, headers=analyst
    )
    assert response.json() == {"status": "approved"}
    await asyncio.wait_for(listener, 2)
    assert received[0]["type"] == "review_resolved" and received[0]["status"] == "answered"

    viewer = await headers(client, "viewer@demo.vn")
    final = (await client.get(f"/api/query-runs/{view['id']}", headers=viewer)).json()
    assert final["status"] == "answered" and final["review"]["status"] == "approved"
    emails = [row[1] for row in final["result"]["rows"]]
    assert emails and all(e.startswith("***@") for e in emails)  # still the masked view

    assert db(pg_settings, "SELECT source FROM verified_examples") == [("review",)]
    assert db(
        pg_settings, "SELECT suite, role, expected_behavior FROM eval_cases WHERE source = 'review'"
    ) == [("review", "viewer", "answer")]


async def test_edit_requires_sql_valid_for_the_askers_role(make_client: Any) -> None:
    client, _ = await pii_setup(make_client)
    item = await pending_item(client)
    analyst = await headers(client, "analyst@demo.vn")
    raw = await client.post(
        f"/api/review/{item['id']}/dry-run",
        json={"sql": "SELECT email FROM customers LIMIT 3"},
        headers=analyst,
    )
    assert raw.json()["ok"] is False and raw.json()["code"] == "TABLE_NOT_ALLOWED"
    rejected = await client.post(
        f"/api/review/{item['id']}/edit",
        json={"sql": "SELECT email FROM customers"},
        headers=analyst,
    )
    assert rejected.status_code == 422
    good = "SELECT full_name, segment FROM v_customers_masked WHERE segment = 'platinum' LIMIT 5"
    dry = (
        await client.post(f"/api/review/{item['id']}/dry-run", json={"sql": good}, headers=analyst)
    ).json()
    assert dry["ok"] and dry["result"]["row_count"] > 0 and dry["pii_columns"] == []
    edited = await client.post(
        f"/api/review/{item['id']}/edit", json={"sql": good, "note": "bỏ email"}, headers=analyst
    )
    assert edited.json() == {"status": "edited"}


async def test_reject_and_return_need_a_note(make_client: Any, pg_settings: Settings) -> None:
    client, view = await pii_setup(make_client)
    item = await pending_item(client)
    analyst = await headers(client, "analyst@demo.vn")
    assert (
        await client.post(f"/api/review/{item['id']}/reject", json={"note": ""}, headers=analyst)
    ).status_code == 422
    ok = await client.post(
        f"/api/review/{item['id']}/reject", json={"note": "Không chia sẻ email"}, headers=analyst
    )
    assert ok.json() == {"status": "rejected"}
    again = await client.post(f"/api/review/{item['id']}/approve", json={}, headers=analyst)
    assert again.status_code == 409
    viewer = await headers(client, "viewer@demo.vn")
    final = (await client.get(f"/api/query-runs/{view['id']}", headers=viewer)).json()
    assert final["status"] == "rejected" and final["review"]["note"] == "Không chia sẻ email"
    assert final["result"] is None and "từ chối" in final["message"]


async def test_disagreement_with_the_judge_is_recorded(
    make_client: Any, pg_settings: Settings
) -> None:
    def judge_uncertain(question: str, prompt: str) -> dict[str, Any]:
        return {"sql": REVENUE_2025, "explanation": "x", "self_confidence": 0.9}

    gen = llm("anthropic", "anthropic", judge_uncertain)
    judge = llm("openai", "openai", judge_uncertain)
    judge.script = [
        lambda m, s: UNCERTAIN if s == "judge_verdict" else {"category": "in_scope", "reason": ""}
    ]
    client = await make_client({"anthropic": gen, "openai": judge})
    _, view = await ask(client, "analyst@demo.vn", "doanh thu năm 2025")
    assert view["status"] == "pending_review"
    # A 0.5 judge score also pulls the blended confidence under 0.7.
    assert [r["code"] for r in view["reasons"]] == ["JUDGE_UNCERTAIN", "LOW_CONFIDENCE"]
    item = await pending_item(client)
    await client.post(
        f"/api/review/{item['id']}/approve",
        json={},
        headers=await headers(client, "analyst@demo.vn"),
    )
    assert db(pg_settings, "SELECT judge_verdict, human_verdict FROM judge_disagreements") == [
        ("uncertain", "pass")
    ]


async def test_approved_sql_is_reused_for_the_same_question(make_client: Any) -> None:
    # No LLM at all: a low-confidence fallback goes to review; once approved, asking again reuses it.
    client = await make_client({})
    _, first = await ask(client, "viewer@demo.vn", "theo khu vực năm 2025")
    assert (
        first["status"] == "pending_review"
        and first["reasons"][0]["code"] == "FALLBACK_LOW_CONFIDENCE"
    )
    item = await pending_item(client)
    await client.post(
        f"/api/review/{item['id']}/approve",
        json={},
        headers=await headers(client, "analyst@demo.vn"),
    )
    _, again = await ask(client, "viewer@demo.vn", "Theo khu vực năm 2025?")
    assert again["status"] == "answered"
    assert again["provider"] == "verified_example" or again["cache_hit"]


async def test_downvote_opens_a_retroactive_review(make_client: Any, pg_settings: Settings) -> None:
    client = await make_client({})
    _, view = await ask(client, "viewer@demo.vn", "Doanh thu theo khu vực năm 2025")
    viewer = await headers(client, "viewer@demo.vn")
    response = await client.post(
        f"/api/query-runs/{view['id']}/feedback",
        json={"rating": "down", "comment": "sai"},
        headers=viewer,
    )
    assert response.json() == {"ok": True, "review_opened": True}
    assert db(pg_settings, "SELECT reasons FROM review_items") == [(["USER_DOWNVOTE"],)]
    again = await client.post(
        f"/api/query-runs/{view['id']}/feedback", json={"rating": "down"}, headers=viewer
    )
    assert again.json()["review_opened"] is False
    other = await headers(client, "analyst@demo.vn")
    assert (
        await client.post(
            f"/api/query-runs/{view['id']}/feedback", json={"rating": "up"}, headers=other
        )
    ).status_code == 404
    assert (await client.get(f"/api/query-runs/{view['id']}", headers=viewer)).json()[
        "feedback"
    ] == "down"


async def test_memory_notifier_delivers_and_heartbeats() -> None:
    notifier = Notifier(None)
    stream = notifier.subscribe("u1", heartbeat_s=0.05)
    assert await anext(stream) is None  # heartbeat
    await notifier.publish("u1", {"type": "review_resolved"})
    assert await anext(stream) == {"type": "review_resolved"}
    await stream.aclose()
