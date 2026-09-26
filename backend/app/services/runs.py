"""Persisting a pipeline run and rendering it for the API (live stream and history alike)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    GuardrailEvent,
    JudgeVerdict,
    LlmCall,
    PipelineStep,
    QueryRun,
    ReviewItem,
    UserFeedback,
)
from app.pipeline.context import PipelineContext
from app.pipeline.messages import message, reason_label
from app.pipeline.prompts import PROMPT_VERSION

HIDE_PREVIEW_REASONS = frozenset({"PII_ACCESS", "COST_GRAY"})
DRAFT_PREVIEW_ROWS = 20


def result_payload(ctx: PipelineContext) -> dict[str, Any] | None:
    if ctx.result is None:
        return None
    return {
        "columns": ctx.result.columns,
        "column_types": ctx.result.column_types,
        "rows": ctx.result.rows,
        "row_count": ctx.result.row_count,
        "truncated": ctx.result.truncated,
    }


async def persist(session: AsyncSession, ctx: PipelineContext, latency_ms: int) -> QueryRun:
    run = await session.get_one(QueryRun, ctx.run_id)
    candidate = ctx.candidate
    run.lang = ctx.lang
    run.rewritten_question = ctx.rewritten_question
    run.final_sql = (ctx.check.sql if ctx.check and ctx.check.sql else None) or (
        candidate.sql if candidate else None
    )
    run.explanation = candidate.explanation if candidate else None
    run.status = ctx.status if ctx.finished else "failed"
    run.risk_decision = (
        ctx.decision.decision if ctx.decision else ("REJECT" if ctx.status == "rejected" else None)
    )
    run.review_reasons = ctx.decision.reasons if ctx.decision else []
    run.confidence = ctx.confidence
    run.provider_used = candidate.provider if candidate else None
    run.used_fallback = bool(candidate and candidate.used_fallback)
    run.guardrail_code = ctx.error_code
    run.row_count = ctx.result.row_count if ctx.result else None
    run.latency_ms = latency_ms
    run.cost_usd = round(sum(a.cost_usd for a in ctx.llm_attempts), 6)
    run.cache_hit = ctx.cache_hit
    run.result_preview = result_payload(ctx)
    run.chart_spec = ctx.chart
    run.summary = ctx.summary
    run.prompt_version = PROMPT_VERSION
    run.updated_at = datetime.now(UTC)

    session.add_all(
        PipelineStep(query_run_id=run.id, step=s.step, status=s.status, started_at=s.started_at,
                     duration_ms=s.duration_ms, detail=s.detail)
        for s in ctx.steps
    )  # fmt: skip
    session.add_all(
        LlmCall(query_run_id=run.id, purpose=a.purpose, provider=a.provider, model=a.model,
                attempt=a.attempt, outcome=a.outcome, input_tokens=a.input_tokens,
                output_tokens=a.output_tokens, latency_ms=a.latency_ms, cost_usd=a.cost_usd)
        for a in ctx.llm_attempts
    )  # fmt: skip
    session.add_all(
        GuardrailEvent(query_run_id=run.id, layer=layer, code=code, detail=detail)
        for layer, code, detail in ctx.guardrail_events
    )  # fmt: skip
    if ctx.judge:
        session.add(
            JudgeVerdict(query_run_id=run.id, judge_model=f"{ctx.judge.provider}:{ctx.judge.model}",
                         verdict=ctx.judge.verdict, score=ctx.judge.score, rubric=ctx.judge.rubric,
                         issues=ctx.judge.issues, same_vendor=ctx.judge.same_vendor)
        )  # fmt: skip
    if run.status == "pending_review" and ctx.decision:
        session.add(
            ReviewItem(query_run_id=run.id, reasons=ctx.decision.reasons,
                       risk_weight=ctx.decision.weight, original_sql=run.final_sql)
        )  # fmt: skip
    await session.commit()
    return run


async def load_view(
    session: AsyncSession, run: QueryRun, *, for_reviewer: bool = False
) -> dict[str, Any]:
    steps = list(
        await session.scalars(
            select(PipelineStep)
            .where(PipelineStep.query_run_id == run.id)
            .order_by(PipelineStep.started_at)
        )
    )
    verdict = await session.scalar(select(JudgeVerdict).where(JudgeVerdict.query_run_id == run.id))
    review = await session.scalar(
        select(ReviewItem)
        .where(ReviewItem.query_run_id == run.id)
        .order_by(ReviewItem.created_at.desc())
        .limit(1)
    )
    rating = await session.scalar(
        select(UserFeedback.rating).where(UserFeedback.query_run_id == run.id, UserFeedback.user_id == run.user_id)
        .order_by(UserFeedback.created_at.desc()).limit(1)
    )  # fmt: skip
    return run_view(run, steps, verdict, review, rating, for_reviewer=for_reviewer)


def run_view(
    run: QueryRun,
    steps: list[PipelineStep],
    verdict: JudgeVerdict | None,
    review: ReviewItem | None,
    rating: str | None,
    *,
    for_reviewer: bool = False,
) -> dict[str, Any]:
    lang = run.lang or "vi"
    reasons = list(run.review_reasons or [])
    result = run.result_preview
    if run.status == "pending_review" and not for_reviewer:
        if set(reasons) & HIDE_PREVIEW_REASONS or result is None:
            result = None
        else:
            result = {**result, "rows": result["rows"][:DRAFT_PREVIEW_ROWS], "draft": True}
    elif run.status in ("rejected", "failed") and not for_reviewer:
        result = None
    code = run.guardrail_code
    if run.status == "pending_review":
        text = message("PENDING_REVIEW", lang)
    elif run.status == "rejected" and review and review.status == "rejected":
        text = message("REVIEW_REJECTED", lang)
    elif run.status == "failed" and review and review.status == "returned":
        text = message("REVIEW_RETURNED", lang)
    elif code:
        text = message(code, lang)
    else:
        text = None
    return {
        "id": str(run.id),
        "conversation_id": str(run.conversation_id) if run.conversation_id else None,
        "question": run.question,
        "rewritten_question": run.rewritten_question,
        "lang": lang,
        "status": run.status,
        "decision": run.risk_decision,
        "reasons": [{"code": r, "label": reason_label(r, lang)} for r in reasons],
        "sql": run.final_sql if (run.status != "rejected" or for_reviewer) else None,
        "explanation": run.explanation,
        "summary": run.summary if result is not None else None,
        "chart": run.chart_spec if result is not None else None,
        "result": result,
        "confidence": run.confidence,
        "provider": run.provider_used,
        "used_fallback": run.used_fallback,
        "code": code,
        "message": text,
        "cost_usd": run.cost_usd,
        "latency_ms": run.latency_ms,
        "cache_hit": run.cache_hit,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "judge": None
        if verdict is None
        else {
            "verdict": verdict.verdict,
            "score": verdict.score,
            "rubric": verdict.rubric,
            "issues": verdict.issues,
            "model": verdict.judge_model,
            "same_vendor": verdict.same_vendor,
        },  # fmt: skip
        "review": None
        if review is None
        else {
            "id": str(review.id),
            "status": review.status,
            "note": review.reviewer_note,
            "edited": bool(review.final_sql and review.final_sql != review.original_sql),
        },  # fmt: skip
        "feedback": rating,
        "trace": [
            {"step": s.step, "status": s.status, "duration_ms": s.duration_ms, "detail": s.detail}
            for s in steps
        ],
    }


def new_run(user_id: uuid.UUID, conversation_id: uuid.UUID | None, question: str) -> QueryRun:
    return QueryRun(
        id=uuid.uuid4(), user_id=user_id, conversation_id=conversation_id, question=question,
        lang="vi", status="running", review_reasons=[],
    )  # fmt: skip
