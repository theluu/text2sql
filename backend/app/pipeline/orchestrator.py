"""Deterministic pipeline: every step is timed, traced, streamed and persisted.

input_guard → cache → rewrite → link → fewshot → generate → [validate → cost → execute ↺ repair ≤2]
→ judge → consistency → risk → output
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.eval.comparators import results_match
from app.llm import rule_based
from app.llm.base import Message
from app.llm.router import AllProvidersFailed, LLMRouter
from app.models import VerifiedExample
from app.pipeline import generator
from app.pipeline.cache import cache_key
from app.pipeline.context import Candidate, PipelineContext, StepRecord, is_hard
from app.pipeline.generator import Repair
from app.pipeline.input_guard import CLASSIFY_CODES, CLASSIFY_PROMPT, CLASSIFY_SCHEMA, check_input
from app.pipeline.judge import judge
from app.pipeline.output import chart_spec, mask_result, summarize
from app.pipeline.prompts import PROMPT_VERSION
from app.pipeline.risk import RiskInputs, RiskSettings, confidence, decide
from app.pipeline.sql_guard import validate_sql
from app.semantic.linker import render_schema
from app.services.container import Services
from app.warehouse.executor import QueryResult, WarehouseError, explain_cost, run_query

log = structlog.get_logger()

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]
MAX_REPAIRS = 2
FEWSHOT_K = 3
FEWSHOT_MIN_SIMILARITY = 0.55
# A verified example this close is the same question: reuse its human-approved SQL directly.
REUSE_SIMILARITY = 0.92
REJECT_CODES = frozenset({"NON_SELECT", "MULTI_STATEMENT", "FORBIDDEN_OBJECT", "TABLE_NOT_ALLOWED",
                          "COLUMN_NOT_ALLOWED", "COST_TOO_HIGH", "DB_TIMEOUT", "DB_PERMISSION"})  # fmt: skip


async def _noop(event: str, data: dict[str, Any]) -> None:
    return None


class Pipeline:
    def __init__(
        self,
        services: Services,
        app_settings: dict[str, Any],
        *,
        router: LLMRouter | None = None,
        emit: Emit = _noop,
        use_cache: bool = True,
        only_provider: str | None = None,
        force_rule_based: bool = False,
    ) -> None:
        self.s = services
        self.app_settings = app_settings
        self.router = router or services.router(app_settings)
        self.risk = RiskSettings.from_dict(app_settings.get("risk", {}))
        self.features = app_settings.get("features", {})
        self.emit = emit
        self.use_cache = use_cache and self.features.get("cache", True)
        self.only_provider = only_provider
        self.force_rule_based = force_rule_based

    @property
    def llm_available(self) -> bool:
        return self.router.available and not self.force_rule_based

    # ── step plumbing ────────────────────────────────────────────────────────────
    async def _step(
        self, ctx: PipelineContext, name: str, fn: Callable[[], Awaitable[dict[str, Any] | None]]
    ) -> None:
        started = datetime.now(UTC)
        clock = time.perf_counter()
        await self.emit("step", {"step": name, "status": "start"})
        try:
            detail = await fn()
            status = "skip" if detail is None else detail.pop("_status", "ok")
        except Exception as error:  # a step bug must not leave the run hanging
            log.exception("pipeline.step_failed", step=name)
            detail, status = {"error": str(error)[:300]}, "error"
            ctx.finish("failed", "INTERNAL_ERROR")
        record = StepRecord(
            name, status, started, int((time.perf_counter() - clock) * 1000), detail or {}
        )
        ctx.steps.append(record)
        await self.emit("step", {**record.to_dict(), "status": status})

    async def run(self, ctx: PipelineContext, session: AsyncSession) -> PipelineContext:
        steps: list[tuple[str, Callable[[], Awaitable[dict[str, Any] | None]]]] = [
            ("input_guard", lambda: self.input_guard(ctx)),
            ("rewrite", lambda: self.rewrite(ctx)),
            ("cache", lambda: self.cache_lookup(ctx)),
            ("link", lambda: self.link(ctx, session)),
            ("fewshot", lambda: self.fewshot(ctx, session)),
            ("generate", lambda: self.generate(ctx)),
        ]
        for name, fn in steps:
            await self._step(ctx, name, fn)
            if ctx.finished:
                return ctx
        await self.check_and_execute(ctx)
        if ctx.finished:
            return ctx
        for name, fn in (
            ("judge", lambda: self.run_judge(ctx)),
            ("consistency", lambda: self.consistency(ctx)),
            ("risk", lambda: self.risk_gate(ctx)),
            ("output", lambda: self.output(ctx)),
        ):
            await self._step(ctx, name, fn)
            if ctx.finished and ctx.status in ("failed", "rejected"):
                return ctx
        return ctx

    # ── steps ─────────────────────────────────────────────────────────────────
    async def input_guard(self, ctx: PipelineContext) -> dict[str, Any]:
        check = check_input(ctx.question)
        ctx.lang = check.lang
        detail: dict[str, Any] = {"lang": check.lang, **check.detail}
        if not check.ok:
            ctx.guardrail("L1", check.code or "INVALID_INPUT", **check.detail)
            ctx.finish("rejected", check.code)
            return {**detail, "code": check.code, "_status": "error"}
        if (
            check.needs_classifier
            and self.llm_available
            and self.features.get("llm_classifier", True)
        ):
            try:
                routed = await self.router.complete(
                    "classify",
                    [Message("system", CLASSIFY_PROMPT),
                     Message("user", f"<question>{ctx.question}</question>")],
                    schema=CLASSIFY_SCHEMA,
                    schema_name="question_screen",
                )  # fmt: skip
            except AllProvidersFailed as failed:
                ctx.llm_attempts += failed.attempts
                detail["classifier"] = "unavailable"
            else:
                ctx.llm_attempts += routed.attempts
                category = str(routed.response.content.get("category", "in_scope"))
                detail["classifier"] = category
                code = CLASSIFY_CODES.get(category)
                if code:
                    ctx.guardrail("L1", code, classifier=routed.response.provider)
                    ctx.finish("rejected", code)
                    return {**detail, "code": code, "_status": "error"}
        return detail

    async def rewrite(self, ctx: PipelineContext) -> dict[str, Any] | None:
        if not ctx.history or not self.llm_available:
            return None
        try:
            routed = await generator.rewrite(self.router, ctx.question, ctx.history)
        except AllProvidersFailed as failed:
            ctx.llm_attempts += failed.attempts
            return {"error": "rewrite unavailable", "_status": "error"}
        ctx.llm_attempts += routed.attempts
        rewritten = str(routed.response.content.get("question") or "").strip()
        if rewritten and rewritten != ctx.question:
            ctx.rewritten_question = rewritten
        return {"question": ctx.effective_question}

    def _cache_key(self, ctx: PipelineContext) -> str:
        return cache_key(ctx.effective_question, self.s.layer.version, ctx.role, PROMPT_VERSION)

    async def cache_lookup(self, ctx: PipelineContext) -> dict[str, Any] | None:
        if not self.use_cache:
            return None
        hit = await self.s.cache.get(self._cache_key(ctx))
        if not hit:
            return {"hit": False}
        ctx.cache_hit = True
        ctx.candidate = Candidate(**hit["candidate"])
        ctx.result = QueryResult(**hit["result"])
        ctx.confidence = hit.get("confidence")
        ctx.summary, ctx.chart = hit.get("summary"), hit.get("chart")
        ctx.masked_columns = hit.get("masked_columns", [])
        ctx.decision = decide(RiskInputs(ctx.role, ctx.confidence or 1.0), self.risk)
        ctx.finish("answered")
        return {"hit": True}

    async def link(self, ctx: PipelineContext, session: AsyncSession) -> dict[str, Any]:
        ctx.linked = await self.s.linker.link(session, ctx.effective_question)
        ctx.schema_text = render_schema(self.s.layer, ctx.linked, ctx.role)
        return ctx.linked.to_detail()

    async def fewshot(self, ctx: PipelineContext, session: AsyncSession) -> dict[str, Any]:
        try:
            [vector] = await self.s.embedder.embed([ctx.effective_question])
        except Exception as error:
            return {"error": f"embedding unavailable: {error}"[:200], "_status": "error"}
        distance = VerifiedExample.embedding.cosine_distance(vector)
        rows = await session.execute(
            select(VerifiedExample.id, VerifiedExample.question, VerifiedExample.sql, distance)
            .where(VerifiedExample.active.is_(True))
            .order_by(distance)
            .limit(FEWSHOT_K)
        )
        for example_id, question, sql, dist in rows:
            similarity = round(1.0 - float(dist), 3)
            if similarity >= FEWSHOT_MIN_SIMILARITY:
                ctx.fewshots.append({"id": str(example_id), "question": question, "sql": sql,
                                     "similarity": similarity})  # fmt: skip
        return {
            "examples": [{k: e[k] for k in ("id", "question", "similarity")} for e in ctx.fewshots]
        }

    async def generate(self, ctx: PipelineContext) -> dict[str, Any]:
        best = ctx.fewshots[0] if ctx.fewshots else None
        if best and best["similarity"] >= REUSE_SIMILARITY:
            ctx.candidate = Candidate(
                sql=best["sql"],
                explanation=(
                    "Dùng lại truy vấn đã được chuyên viên dữ liệu xác nhận cho câu hỏi tương tự."
                    if ctx.lang == "vi"
                    else "Reusing SQL a data analyst verified for the same question."
                ),
                self_confidence=best["similarity"],
                source="verified_example",
                provider="verified_example",
            )
            return {"source": "verified_example", "example_id": best["id"]}
        failure: str | None = None
        if self.llm_available:
            messages = generator.build_messages(
                question=ctx.effective_question, schema_text=ctx.schema_text, fewshots=ctx.fewshots,
                role=ctx.role, as_of=self.s.settings.data_as_of,
            )  # fmt: skip
            try:
                routed = await generator.generate(self.router, messages, only=self.only_provider)
            except AllProvidersFailed as failed:
                ctx.llm_attempts += failed.attempts
                failure = str(failed)
            else:
                ctx.llm_attempts += routed.attempts
                candidate = generator.candidate_from(routed)
                if not candidate.sql:
                    ctx.candidate = candidate
                    ctx.finish("failed", "UNANSWERABLE")
                    return {"source": "llm", "provider": candidate.provider, "unanswerable": True,
                            "_status": "error"}  # fmt: skip
                ctx.candidate = candidate
                return {"source": "llm", "provider": candidate.provider, "model": candidate.model,
                        "failover": routed.failover,
                        "attempts": [a.to_dict() for a in routed.attempts]}  # fmt: skip
        ctx.candidate = generator.fallback(
            ctx.effective_question, ctx.role, self.s.settings.data_as_of
        )
        if ctx.candidate is None:
            ctx.suggestions = rule_based.SUGGESTIONS[ctx.lang]
            ctx.finish("failed", "NO_FALLBACK_MATCH")
            return {
                "source": "rule_based",
                "matched": False,
                "llm_error": failure,
                "_status": "error",
            }
        return {"source": "rule_based", "intent": ctx.candidate.intent, "params": ctx.candidate.params,
                "llm_error": failure}  # fmt: skip

    async def _repair(self, ctx: PipelineContext, error: str) -> bool:
        """Ask the LLM to fix its own SQL. Returns False when repair is not possible."""
        candidate = ctx.candidate
        if (
            candidate is None
            or candidate.source != "llm"
            or ctx.repairs >= MAX_REPAIRS
            or not self.llm_available
        ):
            return False
        ctx.repairs += 1

        async def attempt() -> dict[str, Any]:
            messages = generator.build_messages(
                question=ctx.effective_question, schema_text=ctx.schema_text, fewshots=ctx.fewshots,
                role=ctx.role, as_of=self.s.settings.data_as_of, repair=Repair(candidate.sql, error),
            )  # fmt: skip
            try:
                routed = await generator.generate(
                    self.router, messages, purpose="repair", only=self.only_provider
                )
            except AllProvidersFailed as failed:
                ctx.llm_attempts += failed.attempts
                return {"attempt": ctx.repairs, "error": error, "fixed": False, "_status": "error"}
            ctx.llm_attempts += routed.attempts
            fixed = generator.candidate_from(routed)
            if fixed.sql:
                ctx.candidate = fixed
            return {"attempt": ctx.repairs, "error": error, "fixed": bool(fixed.sql)}

        await self._step(ctx, "repair", attempt)
        return ctx.candidate is not candidate

    async def check_and_execute(self, ctx: PipelineContext) -> None:
        """validate → cost → execute; repairable failures loop back through the LLM (≤2 times)."""
        while not ctx.finished:
            failure = await self._check_once(ctx)
            if failure is None or ctx.finished:
                return
            code, detail = failure
            hard = (ctx.check is not None and ctx.check.hard_block) or code in (
                "COST_TOO_HIGH", "DB_TIMEOUT", "DB_PERMISSION",
            )  # fmt: skip
            if not hard and await self._repair(ctx, f"{code}: {detail}"):
                continue
            ctx.finish("rejected" if code in REJECT_CODES else "failed", code)

    async def _check_once(self, ctx: PipelineContext) -> tuple[str, str] | None:
        outcome: dict[str, Any] = {}

        async def validate() -> dict[str, Any]:
            assert ctx.candidate is not None
            check = validate_sql(ctx.candidate.sql, ctx.role, self.s.layer)
            ctx.check = check
            if check.ok:
                return {"sql": check.sql, "tables": check.tables, "pii_columns": check.pii_columns}
            ctx.guardrail("L3", check.code or "SYNTAX_ERROR", message=check.message)
            outcome["error"] = (check.code or "SYNTAX_ERROR", check.message or "")
            return {"code": check.code, "message": check.message, "_status": "error"}

        await self._step(ctx, "validate", validate)
        if not outcome and not ctx.finished:
            await self._step(ctx, "cost", lambda: self._cost(ctx, outcome))
        if not outcome and not ctx.finished:
            await self._step(ctx, "execute", lambda: self._execute(ctx, outcome))
        error: tuple[str, str] | None = outcome.get("error")
        return error

    async def _cost(self, ctx: PipelineContext, outcome: dict[str, Any]) -> dict[str, Any]:
        assert ctx.check and ctx.check.sql
        try:
            ctx.cost = await explain_cost(self.s.settings, ctx.role, ctx.check.sql)
        except WarehouseError as error:
            outcome["error"] = (error.code, error.message)
            return {"code": error.code, "message": error.message, "_status": "error"}
        detail = {"cost": ctx.cost, "gray": self.risk.gray_cost, "max": self.risk.max_cost}
        if ctx.cost > self.risk.max_cost:
            ctx.guardrail("L4", "COST_TOO_HIGH", cost=ctx.cost, max=self.risk.max_cost)
            outcome["error"] = ("COST_TOO_HIGH", f"estimated cost {ctx.cost:.0f}")
            return {**detail, "code": "COST_TOO_HIGH", "_status": "error"}
        return detail

    async def _execute(self, ctx: PipelineContext, outcome: dict[str, Any]) -> dict[str, Any]:
        assert ctx.check and ctx.check.sql
        try:
            ctx.result = await run_query(self.s.settings, ctx.role, ctx.check.sql)
        except WarehouseError as error:
            if error.code in ("DB_TIMEOUT", "DB_PERMISSION"):
                ctx.guardrail("L4", error.code, message=error.message)
            outcome["error"] = (error.code, error.message)
            return {"code": error.code, "message": error.message, "_status": "error"}
        return {"rows": ctx.result.row_count, "truncated": ctx.result.truncated,
                "duration_ms": ctx.result.duration_ms}  # fmt: skip

    async def run_judge(self, ctx: PipelineContext) -> dict[str, Any] | None:
        if not self.llm_available or ctx.result is None or ctx.check is None or not ctx.check.sql:
            return None
        try:
            ctx.judge = await judge(
                self.router,
                question=ctx.effective_question,
                schema_text=ctx.schema_text,
                sql=ctx.check.sql,
                preview=ctx.result.preview(20),
                generator_vendor=ctx.candidate.vendor if ctx.candidate else None,
            )
        except AllProvidersFailed as failed:
            ctx.llm_attempts += failed.attempts
            return {"error": "judge unavailable", "_status": "error"}
        ctx.llm_attempts += ctx.judge.attempts
        return ctx.judge.to_detail()

    async def consistency(self, ctx: PipelineContext) -> dict[str, Any] | None:
        if not (self.features.get("self_consistency", True) and self.llm_available and ctx.judge
                and ctx.candidate and ctx.candidate.source == "llm" and ctx.result is not None
                and is_hard(ctx.effective_question, ctx.linked)):  # fmt: skip
            return None
        main = ctx.result

        async def alternative(n: int) -> bool | None:
            messages = generator.build_messages(
                question=ctx.effective_question, schema_text=ctx.schema_text, fewshots=ctx.fewshots,
                role=ctx.role, as_of=self.s.settings.data_as_of, alternative=n,
            )  # fmt: skip
            try:
                routed = await generator.generate(self.router, messages, only=self.only_provider)
            except AllProvidersFailed as failed:
                ctx.llm_attempts += failed.attempts
                return None
            ctx.llm_attempts += routed.attempts
            check = validate_sql(
                str(routed.response.content.get("sql") or ""), ctx.role, self.s.layer
            )
            if not check.ok or not check.sql:
                return False
            try:
                other = await run_query(self.s.settings, ctx.role, check.sql)
            except WarehouseError:
                return False
            return results_match(main.rows, other.rows)

        votes = [v for v in await asyncio.gather(alternative(1), alternative(2)) if v is not None]
        if not votes:
            return {"error": "no alternative candidates", "_status": "error"}
        ctx.agreement = round(sum(votes) / len(votes), 3)
        return {"candidates": len(votes) + 1, "agreement": ctx.agreement}

    async def risk_gate(self, ctx: PipelineContext) -> dict[str, Any]:
        assert ctx.candidate is not None and ctx.check is not None
        ctx.confidence = confidence(
            ctx.candidate.self_confidence,
            ctx.judge.score if ctx.judge else None,
            ctx.agreement,
            self.risk,
        )
        inputs = RiskInputs(
            role=ctx.role,
            confidence=ctx.confidence,
            judge_verdict=ctx.judge.verdict if ctx.judge else None,
            pii_columns=ctx.check.pii_columns,
            used_fallback=ctx.candidate.used_fallback,
            cost=ctx.cost,
        )
        ctx.decision = decide(inputs, self.risk)
        if "COST_GRAY" in ctx.decision.reasons:
            ctx.guardrail("L4", "COST_GRAY", cost=ctx.cost)
        return {"decision": ctx.decision.decision, "reasons": ctx.decision.reasons,
                "confidence": ctx.confidence}  # fmt: skip

    async def output(self, ctx: PipelineContext) -> dict[str, Any]:
        assert ctx.result is not None and ctx.decision is not None
        ctx.masked_columns = mask_result(ctx.result, ctx.role)
        if ctx.masked_columns:
            ctx.guardrail("L5", "PII_MASKED", columns=ctx.masked_columns)
        ctx.summary = summarize(ctx.result, ctx.lang)
        ctx.chart = chart_spec(ctx.result)
        if ctx.decision.decision == "AUTO_EXECUTE":
            ctx.finish("answered")
            if self.use_cache and ctx.judge and ctx.judge.verdict == "pass":
                await self.s.cache.set(self._cache_key(ctx), cache_payload(ctx))
        else:
            ctx.finish("pending_review")
        return {"chart": ctx.chart["type"], "masked": ctx.masked_columns, "status": ctx.status}


def cache_payload(ctx: PipelineContext) -> dict[str, Any]:
    assert ctx.candidate and ctx.result
    return {
        "candidate": ctx.candidate.__dict__,
        "result": {
            "columns": ctx.result.columns,
            "rows": ctx.result.rows,
            "row_count": ctx.result.row_count,
            "truncated": ctx.result.truncated,
            "column_types": ctx.result.column_types,
        },  # fmt: skip
        "confidence": ctx.confidence,
        "summary": ctx.summary,
        "chart": ctx.chart,
        "masked_columns": ctx.masked_columns,
    }
