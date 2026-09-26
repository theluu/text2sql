"""Human review of risky answers, and the feedback loop that learns from it."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hitl.notifications import Notifier
from app.models import (
    EvalCase,
    JudgeDisagreement,
    JudgeVerdict,
    QueryRun,
    ReviewItem,
    User,
    VerifiedExample,
)
from app.pipeline.cache import cache_key
from app.pipeline.output import chart_spec, mask_result, summarize
from app.pipeline.prompts import PROMPT_VERSION
from app.pipeline.sql_guard import validate_sql
from app.services.container import Services
from app.warehouse.executor import QueryResult, WarehouseError, explain_cost, run_query

OPEN_STATUSES = ("open", "claimed")


class ReviewError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass
class DryRun:
    ok: bool
    sql: str | None
    code: str | None
    message: str | None
    result: dict[str, Any] | None
    cost: float | None
    pii_columns: list[str]
    masked: list[str]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


def priority_expr() -> Any:
    age_hours = func.extract("epoch", func.now() - ReviewItem.created_at) / 3600.0
    return ReviewItem.risk_weight * (1.0 + age_hours)


async def queue(
    session: AsyncSession, status: str = "pending", reason: str | None = None
) -> list[dict[str, Any]]:
    statement = (
        select(ReviewItem, QueryRun, User, priority_expr().label("priority"))
        .join(QueryRun, QueryRun.id == ReviewItem.query_run_id)
        .join(User, User.id == QueryRun.user_id)
    )
    if status == "pending":
        statement = statement.where(ReviewItem.status.in_(OPEN_STATUSES))
    elif status != "all":
        statement = statement.where(ReviewItem.status == status)
    if reason:
        statement = statement.where(ReviewItem.reasons.contains([reason]))
    statement = statement.order_by(
        ReviewItem.status.in_(OPEN_STATUSES).desc(), priority_expr().desc()
    ).limit(200)
    rows = await session.execute(statement)
    assignees = {u.id: u.name for u in await session.scalars(select(User))}
    return [
        {
            "id": str(item.id),
            "run_id": str(run.id),
            "question": run.question,
            "lang": run.lang,
            "asker": {"name": user.name, "role": user.role.value},
            "reasons": item.reasons,
            "status": item.status,
            "priority": round(float(priority), 2),
            "assignee": assignees.get(item.assignee_id) if item.assignee_id else None,
            "confidence": run.confidence,
            "provider": run.provider_used,
            "created_at": item.created_at.isoformat(),
            "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        }
        for item, run, user, priority in rows
    ]


async def load(session: AsyncSession, item_id: uuid.UUID) -> tuple[ReviewItem, QueryRun, User]:
    item = await session.get(ReviewItem, item_id)
    if item is None:
        raise ReviewError("not_found")
    run = await session.get_one(QueryRun, item.query_run_id)
    asker = await session.get_one(User, run.user_id)
    return item, run, asker


async def claim(session: AsyncSession, item_id: uuid.UUID, reviewer: User) -> ReviewItem:
    item, _, _ = await load(session, item_id)
    _ensure_actionable(item, reviewer, claiming=True)
    item.status, item.assignee_id = "claimed", reviewer.id
    await session.commit()
    return item


def _ensure_actionable(item: ReviewItem, reviewer: User, *, claiming: bool = False) -> None:
    if item.status not in OPEN_STATUSES:
        raise ReviewError("already_resolved")
    if (
        item.status == "claimed"
        and item.assignee_id not in (None, reviewer.id)
        and reviewer.role.value != "admin"
    ):
        raise ReviewError("claimed_by_other")


async def dry_run(services: Services, sql: str, asker_role: str) -> DryRun:
    """Run SQL exactly as the asker would get it: L3 for the asker's role, L4 cost, L5 masking."""
    check = validate_sql(sql, asker_role, services.layer)
    if not check.ok or not check.sql:
        return DryRun(False, None, check.code, check.message, None, None, [], [])
    try:
        cost = await explain_cost(services.settings, asker_role, check.sql)
        result = await run_query(services.settings, asker_role, check.sql)
    except WarehouseError as error:
        return DryRun(
            False, check.sql, error.code, error.message, None, None, check.pii_columns, []
        )
    masked = mask_result(result, asker_role)
    preview = result.preview(1000)
    return DryRun(True, check.sql, None, None, preview, cost, check.pii_columns, masked)


async def resolve(
    services: Services,
    notifier: Notifier,
    session: AsyncSession,
    item_id: uuid.UUID,
    reviewer: User,
    *,
    action: str,  # approve | edit | reject | return
    sql: str | None = None,
    note: str | None = None,
    add_to_golden: bool = False,
) -> ReviewItem:
    item, run, asker = await load(session, item_id)
    _ensure_actionable(item, reviewer)
    if action in ("reject", "return") and not (note and note.strip()):
        raise ReviewError("note_required")
    now = datetime.now(UTC)
    item.assignee_id = reviewer.id
    item.reviewer_note = (note or "").strip() or None
    item.resolved_at = now
    run.updated_at = now

    if action in ("approve", "edit"):
        final = sql if action == "edit" and sql else (item.original_sql or run.final_sql or "")
        outcome = await dry_run(services, final, asker.role.value)
        if not outcome.ok or outcome.result is None or not outcome.sql:
            raise ReviewError("dry_run_failed", f"{outcome.code}: {outcome.message}")
        edited = action == "edit" and _normalized(outcome.sql) != _normalized(
            item.original_sql or ""
        )
        item.status = "edited" if edited else "approved"
        item.final_sql = outcome.sql
        item.add_to_golden = add_to_golden
        result = QueryResult(outcome.result["columns"], outcome.result["rows"], outcome.result["row_count"],
                             outcome.result["truncated"], column_types=outcome.result["column_types"])  # fmt: skip
        run.status = "answered"
        run.final_sql = outcome.sql
        run.result_preview = outcome.result
        run.row_count = result.row_count
        run.summary = summarize(result, run.lang)
        run.chart_spec = chart_spec(result)
        run.guardrail_code = None
        await _learn(
            services, session, item, run, reviewer, outcome.sql, add_to_golden, asker.role.value
        )
        await _disagreement(session, item, run, human="pass" if not edited else "fail")
        await services.cache.set(
            cache_key(
                run.rewritten_question or run.question,
                services.layer.version,
                asker.role.value,
                PROMPT_VERSION,
            ),
            {
                "candidate": {
                    "sql": outcome.sql,
                    "explanation": run.explanation or "",
                    "self_confidence": 1.0,
                    "source": "verified_example",
                    "provider": "verified_example",
                },
                "result": {
                    k: outcome.result[k]
                    for k in ("columns", "rows", "row_count", "truncated", "column_types")
                },
                "confidence": 1.0,
                "summary": run.summary,
                "chart": run.chart_spec,
                "masked_columns": outcome.masked,
            },  # fmt: skip
        )
        run.provider_used = "verified_example" if edited else run.provider_used
    elif action == "reject":
        item.status = "rejected"
        run.status = "rejected"
        run.guardrail_code = "REVIEW_REJECTED"
        await _disagreement(session, item, run, human="fail")
    elif action == "return":
        item.status = "returned"
        run.status = "failed"
        run.guardrail_code = "REVIEW_RETURNED"
    else:
        raise ReviewError("unknown_action")
    await session.commit()
    await notifier.publish(
        asker.id,
        {"type": "review_resolved", "run_id": str(run.id), "conversation_id": str(run.conversation_id),
         "status": run.status, "question": run.question},
    )  # fmt: skip
    return item


def _normalized(sql: str) -> str:
    check = validate_sql(sql, "admin")
    return check.sql or sql.strip()


async def _learn(
    services: Services, session: AsyncSession, item: ReviewItem, run: QueryRun, reviewer: User,
    sql: str, add_to_golden: bool, asker_role: str,
) -> None:  # fmt: skip
    """Approved SQL becomes a few-shot example at once, and optionally a golden eval case."""
    question = run.rewritten_question or run.question
    try:
        [vector] = await services.embedder.embed([question])
    except Exception:
        vector = None
    if vector is not None:
        session.add(VerifiedExample(question=question, lang=run.lang, sql=sql, source="review",
                                    embedding=vector, approved_by=reviewer.id))  # fmt: skip
    if add_to_golden:
        session.add(
            EvalCase(key=f"review-{item.id}", suite="review", question=question, lang=run.lang,
                     role=asker_role, gold_sql=sql, expected_behavior="answer", difficulty="medium",
                     tags=["from_review"], source="review")
        )  # fmt: skip


async def _disagreement(
    session: AsyncSession, item: ReviewItem, run: QueryRun, *, human: str
) -> None:
    verdict = await session.scalar(
        select(JudgeVerdict.verdict).where(JudgeVerdict.query_run_id == run.id)
    )
    if verdict and verdict != human:
        session.add(
            JudgeDisagreement(review_item_id=item.id, judge_verdict=verdict, human_verdict=human)
        )


async def pending_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(select(func.count()).where(ReviewItem.status.in_(OPEN_STATUSES))) or 0
    )
