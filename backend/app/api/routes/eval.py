import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_min_role
from app.core.db import get_session
from app.eval.runner import create_run, execute_run, validate_mode
from app.models import EvalCase, EvalResult, EvalRun, Role, User
from app.services.container import Services
from app.services.deps import ServicesDep

log = structlog.get_logger()
router = APIRouter(tags=["eval"])
Session = Annotated[AsyncSession, Depends(get_session)]
Analyst = Annotated[User, Depends(require_min_role(Role.analyst))]
_background: set[asyncio.Task[Any]] = set()


class RunRequest(BaseModel):
    suite: str = Field(default="smoke", pattern="^(smoke|full|review)$")
    mode: str = Field(default="chain", max_length=40)


def run_dict(run: EvalRun, done: int | None = None) -> dict[str, Any]:
    return {
        "id": str(run.id), "suite": run.suite, "mode": run.mode, "status": run.status, "total": run.total,
        "done": done, "git_sha": run.git_sha, "prompt_version": run.prompt_version,
        "model_chain": run.model_chain, "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None, "summary": run.summary,
    }  # fmt: skip


async def _enqueue(services: Services, run_id: uuid.UUID) -> str:
    """Prefer the arq worker; without Redis run in-process so the page still works."""
    if services.redis is not None:
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            pool = await create_pool(RedisSettings.from_dsn(services.settings.redis_url))
            await pool.enqueue_job("run_eval_job", str(run_id))
            await pool.aclose()
            return "worker"
        except Exception as error:
            log.warning("eval.enqueue_failed", error=str(error))
    task = asyncio.create_task(execute_run(services, run_id))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return "inline"


@router.get("/eval/runs")
async def list_runs(_: Analyst, session: Session) -> list[dict[str, Any]]:
    done = dict(
        (
            await session.execute(
                select(EvalResult.eval_run_id, func.count()).group_by(EvalResult.eval_run_id)
            )
        ).all()
    )
    runs = await session.scalars(select(EvalRun).order_by(EvalRun.started_at.desc()).limit(50))
    return [run_dict(r, done.get(r.id, 0)) for r in runs]


@router.post("/eval/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: RunRequest, user: Analyst, services: ServicesDep) -> dict[str, Any]:
    try:
        validate_mode(body.mode, sorted(services.providers))
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from None
    run = await create_run(services, body.suite, body.mode, user.id)
    where = await _enqueue(services, run.id)
    return {**run_dict(run, 0), "executor": where}


@router.get("/eval/runs/{run_id}")
async def get_run(run_id: uuid.UUID, _: Analyst, session: Session) -> dict[str, Any]:
    run = await session.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    rows = await session.execute(
        select(EvalResult, EvalCase).join(EvalCase, EvalCase.id == EvalResult.eval_case_id)
        .where(EvalResult.eval_run_id == run.id).order_by(EvalCase.key)
    )  # fmt: skip
    results = [
        {
            "case_id": str(case.id),
            "key": case.key,
            "question": case.question,
            "lang": case.lang,
            "role": case.role,
            "difficulty": case.difficulty,
            "tags": case.tags,
            "expected": case.expected_behavior,
            "behavior": result.behavior,
            "ex": result.ex_match,
            "esm": result.esm_match,
            "judge": result.judge_verdict,
            "guardrail_code": result.guardrail_code,
            "provider": result.provider_used,
            "fallback": result.used_fallback,
            "latency_ms": result.latency_ms,
            "cost_usd": result.cost_usd,
            "gold_sql": case.gold_sql,
            "predicted_sql": result.predicted_sql,
            "error": result.error,
            "linked_tables": result.linked_tables,
        }  # fmt: skip
        for result, case in rows
    ]
    return {**run_dict(run, len(results)), "results": results}


@router.get("/eval/runs/{run_id}/stream")
async def stream(
    run_id: uuid.UUID, request: Request, _: Analyst, services: ServicesDep
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        while not await request.is_disconnected():
            async with services.sessionmaker() as session:
                run = await session.get(EvalRun, run_id)
                if run is None:
                    return
                done = await session.scalar(
                    select(func.count()).where(EvalResult.eval_run_id == run_id)
                )  # fmt: skip
            payload = {"status": run.status, "done": done, "total": run.total}
            yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
            if run.status in ("done", "failed"):
                return
            await asyncio.sleep(1.0)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})  # fmt: skip


def _correct(row: dict[str, Any]) -> bool:
    return (
        bool(row["ex"])
        if row["expected"] == "answer" and row["ex"] is not None
        else row["behavior"] == row["expected"]
    )


@router.get("/eval/compare")
async def compare(a: uuid.UUID, b: uuid.UUID, user: Analyst, session: Session) -> dict[str, Any]:
    left, right = await get_run(a, user, session), await get_run(b, user, session)
    by_key = {r["key"]: r for r in left["results"]}
    improved, regressed, same = [], [], 0
    for row in right["results"]:
        before = by_key.get(row["key"])
        if before is None:
            continue
        was, now = _correct(before), _correct(row)
        entry = {"key": row["key"], "question": row["question"], "before": before["behavior"], "after": row["behavior"],
                 "ex_before": before["ex"], "ex_after": row["ex"]}  # fmt: skip
        if now and not was:
            improved.append(entry)
        elif was and not now:
            regressed.append(entry)
        else:
            same += 1
    return {
        "a": {k: v for k, v in left.items() if k != "results"},
        "b": {k: v for k, v in right.items() if k != "results"},
        "improved": improved, "regressed": regressed, "unchanged": same,
    }  # fmt: skip
