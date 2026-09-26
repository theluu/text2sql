"""Run eval cases through the real pipeline and score them."""

import asyncio
import os
import subprocess
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from app.eval.cassette import CASSETTE_DIR, with_cassette
from app.eval.comparators import exact_structure_match, has_order_by, results_match
from app.eval.metrics import CaseOutcome, summarize, tables_in
from app.llm.registry import build_router
from app.models import EvalCase, EvalResult, EvalRun
from app.pipeline.context import PipelineContext
from app.pipeline.orchestrator import Pipeline
from app.pipeline.prompts import PROMPT_VERSION
from app.pipeline.sql_guard import validate_sql
from app.services.app_settings import load_app_settings
from app.services.container import Services
from app.warehouse.executor import QueryResult, WarehouseError, run_query

log = structlog.get_logger()
BEHAVIOR = {"answered": "answer", "pending_review": "review", "rejected": "reject"}
MODES = ("chain", "rule_based")  # plus provider=<name>


def git_sha() -> str | None:
    if sha := os.environ.get("GIT_SHA"):
        return sha[:40]
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
                              timeout=2).stdout.strip() or None  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None


def validate_mode(mode: str, available: list[str]) -> None:
    if mode in MODES:
        return
    if mode.startswith("provider=") and mode.split("=", 1)[1] in available:
        return
    raise ValueError(
        f"unknown mode {mode!r}; use chain, rule_based or provider=<{'|'.join(available)}>"
    )


async def create_run(
    services: Services, suite: str, mode: str, user_id: uuid.UUID | None
) -> EvalRun:
    async with services.sessionmaker() as session:
        statement = select(EvalCase).where(EvalCase.active.is_(True))
        if suite == "smoke":
            statement = statement.where(EvalCase.tags.contains(["smoke"]))
        elif suite != "full":
            statement = statement.where(EvalCase.suite == suite)
        total = len(list(await session.scalars(statement)))
        run = EvalRun(suite=suite, git_sha=git_sha(), prompt_version=PROMPT_VERSION, model_chain=[],
                      mode=mode, status="queued", total=total, created_by=user_id)  # fmt: skip
        session.add(run)
        await session.commit()
        return run


async def execute_run(
    services: Services, run_id: uuid.UUID, *, concurrency: int = 4, cassette_mode: str = "off"
) -> dict[str, Any]:
    async with services.sessionmaker() as session:
        run = await session.get_one(EvalRun, run_id)
        statement = select(EvalCase).where(EvalCase.active.is_(True)).order_by(EvalCase.key)
        if run.suite == "smoke":
            statement = statement.where(EvalCase.tags.contains(["smoke"]))
        elif run.suite != "full":
            statement = statement.where(EvalCase.suite == run.suite)
        cases = list(await session.scalars(statement))
        app_settings = await load_app_settings(session)
        app_settings["chaos"] = {"disabled_providers": []}  # evals measure the system, not a drill
        app_settings["features"] = {**app_settings["features"], "cache": False}
        providers, cassette = with_cassette(
            services.providers, cassette_mode, CASSETTE_DIR / f"{run.suite}.json"
        )
        only = run.mode.split("=", 1)[1] if run.mode.startswith("provider=") else None
        chain = [only] if only else app_settings["llm_chain"]
        router = build_router(
            providers, services.breaker, chain, app_settings["chaos"],
            call_timeout_s=services.settings.llm_call_timeout_s, budget_s=services.settings.llm_budget_s,
        )  # fmt: skip
        run.model_chain = [f"{p.name}:{p.model}" for p in router.providers] + (
            [] if only else ["rule_based"]
        )
        run.status, run.total = "running", len(cases)
        await session.commit()

    semaphore = asyncio.Semaphore(concurrency)
    gold_cache: dict[str, QueryResult | None] = {}
    outcomes: list[CaseOutcome] = []

    async def one(case: EvalCase) -> None:
        async with semaphore:
            outcome = await _run_case(services, app_settings, router, run, case, gold_cache,
                                      force_rule_based=run.mode == "rule_based")  # fmt: skip
            outcomes.append(outcome)

    try:
        await asyncio.gather(*(one(c) for c in cases))
        summary = summarize(outcomes)
        status = "done"
    except Exception as error:  # keep partial results; mark the run failed
        log.exception("eval.run_failed", run_id=str(run_id))
        summary = {**summarize(outcomes), "error": str(error)[:300]}
        status = "failed"
    if cassette:
        cassette.save()
    async with services.sessionmaker() as session:
        run = await session.get_one(EvalRun, run_id)
        run.status, run.summary, run.finished_at = status, summary, datetime.now(UTC)
        await session.commit()
    return summary


async def _gold(
    services: Services, case: EvalCase, cache: dict[str, QueryResult | None]
) -> QueryResult | None:
    if not case.gold_sql:
        return None
    if case.key not in cache:
        check = validate_sql(case.gold_sql, case.role, services.layer)
        cache[case.key] = (
            await run_query(services.settings, case.role, check.sql)
            if check.ok and check.sql
            else None
        )
    return cache[case.key]


async def _run_case(
    services: Services, app_settings: dict[str, Any], router: Any, run: EvalRun, case: EvalCase,
    gold_cache: dict[str, QueryResult | None], *, force_rule_based: bool,
) -> CaseOutcome:  # fmt: skip
    started = time.perf_counter()
    ctx = PipelineContext(run_id=uuid.uuid4(), user_id=run.created_by or uuid.uuid4(), role=case.role,
                          question=case.question)  # fmt: skip
    error: str | None = None
    try:
        async with services.sessionmaker() as session:
            pipeline = Pipeline(services, app_settings, router=router, use_cache=False,
                                force_rule_based=force_rule_based)  # fmt: skip
            await pipeline.run(ctx, session)
    except Exception as exc:
        error = str(exc)[:300]
        ctx.finish("failed", "INTERNAL_ERROR")
    latency = int((time.perf_counter() - started) * 1000)
    behavior = BEHAVIOR.get(ctx.status, "fail")
    predicted_sql = ctx.check.sql if ctx.check and ctx.check.sql else None
    ex = esm = None
    if case.expected_behavior == "answer" and case.gold_sql:
        try:
            gold = await _gold(services, case, gold_cache)
        except WarehouseError as exc:
            gold, error = None, f"gold failed: {exc.message}"
        if gold is not None:
            ex = bool(ctx.result is not None and results_match(
                gold.rows, ctx.result.rows, ordered=has_order_by(case.gold_sql)))  # fmt: skip
            esm = bool(predicted_sql and exact_structure_match(case.gold_sql, predicted_sql))
    outcome = CaseOutcome(
        key=case.key, difficulty=case.difficulty, tags=list(case.tags), expected=case.expected_behavior,
        behavior=behavior, ex=ex, esm=esm, judge_verdict=ctx.judge.verdict if ctx.judge else None,
        gold_tables=tables_in(case.gold_sql), linked_tables=ctx.linked.tables if ctx.linked else [],
        latency_ms=latency, cost_usd=round(sum(a.cost_usd for a in ctx.llm_attempts), 6),
        failover=any(a.outcome != "ok" for a in ctx.llm_attempts),
        used_fallback=bool(ctx.candidate and ctx.candidate.used_fallback),
    )  # fmt: skip
    async with services.sessionmaker() as session:
        session.add(EvalResult(
            eval_run_id=run.id, eval_case_id=case.id, predicted_sql=predicted_sql, behavior=behavior,
            ex_match=ex, esm_match=esm, judge_verdict=outcome.judge_verdict, guardrail_code=ctx.error_code,
            provider_used=ctx.candidate.provider if ctx.candidate else None, used_fallback=outcome.used_fallback,
            linked_tables=outcome.linked_tables, latency_ms=latency, cost_usd=outcome.cost_usd, error=error,
            trace=[s.to_dict() for s in ctx.steps],
        ))  # fmt: skip
        await session.commit()
    return outcome


def gate(summary: dict[str, Any], baseline: dict[str, Any], max_ex_drop: float = 0.02) -> list[str]:
    """CI gate: EX may drop at most 2 points vs the committed baseline; no adversarial leaks."""
    problems = []
    ex, base = summary.get("ex"), baseline.get("ex")
    if ex is not None and base is not None and ex < base - max_ex_drop:
        problems.append(f"EX {ex:.3f} < baseline {base:.3f} - {max_ex_drop}")
    if summary.get("adversarial_leaks"):
        problems.append(f"adversarial cases leaked: {', '.join(summary['adversarial_leaks'])}")
    return problems
