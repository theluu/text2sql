from typing import Any

import httpx
import pytest

from app.core.config import Settings
from tests.flows import REVENUE_2025, db, llm, sql_answer
from tests.helpers import login_token

pytestmark = pytest.mark.usefixtures("clean_app_db")


async def run_smoke(client: httpx.AsyncClient, mode: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {await login_token(client, 'analyst@demo.vn')}"}
    started = await client.post(
        "/api/eval/runs", json={"suite": "smoke", "mode": mode}, headers=headers
    )
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]
    # No Redis in tests: the run executes in-process; wait on the progress stream.
    stream = await client.get(f"/api/eval/runs/{run_id}/stream", headers=headers)
    assert '"status": "done"' in stream.text
    detail = (await client.get(f"/api/eval/runs/{run_id}", headers=headers)).json()
    return detail  # type: ignore[no-any-return]


async def test_rule_based_smoke_run_scores_and_blocks_attacks(
    make_client: Any, pg_settings: Settings
) -> None:
    client = await make_client({})
    from app.cli import _seed_app_data

    await _seed_app_data(pg_settings)
    detail = await run_smoke(client, "rule_based")
    summary = detail["summary"]
    assert detail["status"] == "done" and detail["total"] == 30 and len(detail["results"]) == 30
    assert summary["guardrail_recall"] == 1.0 and summary["adversarial_leaks"] == []
    assert summary["ex"] is not None and summary["ex"] > 0.3
    assert summary["fallback_rate"] > 0.5
    assert {"easy", "medium", "hard"} <= set(summary["by_difficulty"])
    e01 = next(r for r in detail["results"] if r["key"] == "e01")
    assert e01["ex"] is True and e01["behavior"] == "answer"


async def test_chain_mode_with_fake_llm_and_compare(
    make_client: Any, pg_settings: Settings
) -> None:
    gen = llm("openai", "openai", sql_answer(REVENUE_2025))
    client = await make_client(
        {"openai": gen, "anthropic": llm("anthropic", "anthropic", sql_answer("SELECT 1"))}
    )
    from app.cli import _seed_app_data

    await _seed_app_data(pg_settings)
    first = await run_smoke(client, "chain")
    assert first["summary"]["cases"] == 30
    assert first["model_chain"][:2] == ["openai:fake-1", "anthropic:fake-1"]
    e01 = next(r for r in first["results"] if r["key"] == "e01")
    assert e01["ex"] is True and e01["provider"] == "openai"
    second = await run_smoke(client, "rule_based")
    headers = {"Authorization": f"Bearer {await login_token(client, 'analyst@demo.vn')}"}
    comparison = (
        await client.get(f"/api/eval/compare?a={first['id']}&b={second['id']}", headers=headers)
    ).json()
    assert comparison["improved"] or comparison["regressed"]
    assert (
        len(comparison["improved"]) + len(comparison["regressed"]) + comparison["unchanged"] == 30
    )
    assert db(pg_settings, "SELECT count(*) FROM eval_results")[0][0] == 60


async def test_eval_requires_analyst_and_valid_mode(make_client: Any) -> None:
    client = await make_client({})
    viewer = {"Authorization": f"Bearer {await login_token(client, 'viewer@demo.vn')}"}
    assert (await client.get("/api/eval/runs", headers=viewer)).status_code == 403
    analyst = {"Authorization": f"Bearer {await login_token(client, 'analyst@demo.vn')}"}
    bad = await client.post(
        "/api/eval/runs", json={"suite": "smoke", "mode": "provider=gpt9"}, headers=analyst
    )
    assert bad.status_code == 422
