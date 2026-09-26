from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_min_role
from app.core.db import get_session
from app.hitl.review_service import pending_count
from app.llm.registry import KNOWN_PROVIDERS
from app.models import (
    GuardrailEvent,
    JudgeDisagreement,
    JudgeVerdict,
    LlmCall,
    QueryRun,
    ReviewItem,
    Role,
    User,
)
from app.services.app_settings import load_app_settings
from app.services.deps import ServicesDep

router = APIRouter(tags=["dashboard"])
Session = Annotated[AsyncSession, Depends(get_session)]
Admin = Annotated[User, Depends(require_min_role(Role.admin))]


def _day(column: Any) -> Any:
    return cast(func.timezone("Asia/Ho_Chi_Minh", column), Date)


async def provider_health(
    services: Any, session: AsyncSession, since: datetime
) -> list[dict[str, Any]]:
    app_settings = await load_app_settings(session)
    chaos = set(app_settings["chaos"].get("disabled_providers", []))
    stats = {
        row.provider: row
        for row in await session.execute(
            select(
                LlmCall.provider,
                func.count().label("calls"),
                func.count().filter(LlmCall.outcome != "ok").label("errors"),
                func.avg(LlmCall.latency_ms).filter(LlmCall.outcome == "ok").label("latency"),
            )
            .where(LlmCall.created_at >= since)
            .group_by(LlmCall.provider)
        )
    }
    result = []
    for name in KNOWN_PROVIDERS:
        provider = services.providers.get(name)
        row = stats.get(name)
        result.append({
            "name": name,
            "configured": provider is not None,
            "model": provider.model if provider else None,
            "in_chain": name in app_settings["llm_chain"],
            "chaos": name in chaos,
            "circuit": await services.breaker.state(name) if provider else None,
            "calls": int(row.calls) if row else 0,
            "error_rate": round(row.errors / row.calls, 3) if row and row.calls else None,
            "avg_latency_ms": round(float(row.latency)) if row and row.latency else None,
        })  # fmt: skip
    return result


@router.get("/dashboard/ops")
async def ops(
    _: Admin, session: Session, services: ServicesDep, days: Annotated[int, Query(ge=1, le=90)] = 14
) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)
    day = _day(QueryRun.created_at).label("day")
    decision_rows = await session.execute(
        select(
            day,
            func.count().filter(QueryRun.risk_decision == "AUTO_EXECUTE").label("auto"),
            func.count().filter(QueryRun.risk_decision == "NEEDS_REVIEW").label("review"),
            func.count().filter(QueryRun.status == "rejected").label("reject"),
            func.count().filter(QueryRun.status == "failed").label("failed"),
            func.count().filter(QueryRun.used_fallback).label("fallback"),
        )
        .where(QueryRun.created_at >= since, QueryRun.status != "running")
        .group_by(day)
        .order_by(day)
    )
    failover_runs = (
        select(LlmCall.query_run_id)
        .where(LlmCall.outcome != "ok", LlmCall.query_run_id.is_not(None))
        .distinct()
    )
    failover_rows = dict(
        (r.day, r.n)
        for r in await session.execute(
            select(day, func.count().label("n"))
            .where(QueryRun.created_at >= since, QueryRun.id.in_(failover_runs))
            .group_by(day)
        )  # fmt: skip
    )
    decisions = [
        {"day": r.day.isoformat(), "auto": r.auto, "review": r.review, "reject": r.reject, "failed": r.failed,
         "fallback": r.fallback, "failover": failover_rows.get(r.day, 0)}
        for r in decision_rows
    ]  # fmt: skip

    cost_day = _day(LlmCall.created_at).label("day")
    costs = [
        {"day": r.day.isoformat(), "cost_usd": round(float(r.cost or 0), 6), "calls": r.calls,
         "tokens": int(r.tokens or 0)}
        for r in await session.execute(
            select(cost_day, func.sum(LlmCall.cost_usd).label("cost"), func.count().label("calls"),
                   func.sum(LlmCall.input_tokens + LlmCall.output_tokens).label("tokens"))
            .where(LlmCall.created_at >= since).group_by(cost_day).order_by(cost_day)
        )
    ]  # fmt: skip
    guardrails = [
        {"layer": r.layer, "code": r.code, "count": r.n}
        for r in await session.execute(
            select(GuardrailEvent.layer, GuardrailEvent.code, func.count().label("n"))
            .where(GuardrailEvent.created_at >= since)
            .group_by(GuardrailEvent.layer, GuardrailEvent.code)
            .order_by(func.count().desc())
            .limit(8)
        )
    ]  # fmt: skip

    totals_row = (
        await session.execute(
            select(
                func.count().label("questions"),
                func.count().filter(QueryRun.risk_decision == "AUTO_EXECUTE").label("auto"),
                func.count().filter(QueryRun.used_fallback).label("fallback"),
                func.count().filter(QueryRun.cache_hit).label("cache"),
                func.percentile_cont(0.95).within_group(QueryRun.latency_ms).label("p95"),
                func.sum(QueryRun.cost_usd).label("cost"),
            ).where(QueryRun.created_at >= since, QueryRun.status != "running")
        )
    ).one()
    reviewed = await session.scalar(
        select(func.count()).select_from(ReviewItem)
        .join(JudgeVerdict, JudgeVerdict.query_run_id == ReviewItem.query_run_id)
        .where(ReviewItem.resolved_at.is_not(None), ReviewItem.status != "returned")
    )  # fmt: skip
    disagreements = await session.scalar(select(func.count()).select_from(JudgeDisagreement))
    questions = int(totals_row.questions or 0)

    def rate(n: Any) -> float | None:
        return round(int(n or 0) / questions, 3) if questions else None

    return {
        "days": days,
        "totals": {
            "questions": questions,
            "auto_rate": rate(totals_row.auto),
            "fallback_rate": rate(totals_row.fallback),
            "cache_hit_rate": rate(totals_row.cache),
            "failover_rate": rate(sum(d["failover"] for d in decisions)),
            "latency_p95_ms": round(float(totals_row.p95)) if totals_row.p95 is not None else None,
            "cost_usd": round(float(totals_row.cost or 0), 4),
            "pending_reviews": await pending_count(session),
            "judge_human_agreement": round(1 - (disagreements or 0) / reviewed, 3)
            if reviewed
            else None,
        },
        "decisions": decisions,
        "costs": costs,
        "guardrails": guardrails,
        "providers": await provider_health(services, session, since),
    }
