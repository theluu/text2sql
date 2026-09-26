"""One question end to end: conversation bookkeeping, pipeline run, persistence, events."""

import time
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, QueryRun
from app.pipeline.context import PipelineContext, StepRecord
from app.pipeline.messages import message
from app.pipeline.orchestrator import Emit, Pipeline
from app.services.app_settings import load_app_settings
from app.services.container import Services
from app.services.runs import load_view, new_run, persist

log = structlog.get_logger()


class ConversationNotFound(Exception):
    pass


async def _conversation(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID | None, question: str
) -> Conversation:
    if conversation_id:
        found = await session.get(Conversation, conversation_id)
        if found is None or found.user_id != user_id:
            raise ConversationNotFound
        return found
    conversation = Conversation(user_id=user_id, title=question.strip()[:120] or "…")
    session.add(conversation)
    await session.flush()
    return conversation


async def _history(
    session: AsyncSession, conversation_id: uuid.UUID
) -> list[tuple[str, str | None]]:
    rows = await session.execute(
        select(QueryRun.question, QueryRun.final_sql)
        .where(
            QueryRun.conversation_id == conversation_id,
            QueryRun.status.in_(("answered", "pending_review")),
        )
        .order_by(QueryRun.created_at.desc())
        .limit(3)
    )
    return [(q, sql) for q, sql in rows][::-1]


async def prepare(
    services: Services, user_id: uuid.UUID, question: str, conversation_id: uuid.UUID | None
) -> tuple[uuid.UUID, uuid.UUID, list[tuple[str, str | None]]]:
    async with services.sessionmaker() as session:
        conversation = await _conversation(session, user_id, conversation_id, question)
        history = await _history(session, conversation.id) if conversation_id else []
        run = new_run(user_id, conversation.id, question)
        session.add(run)
        await session.commit()
        return run.id, conversation.id, history


async def answer(
    services: Services,
    *,
    run_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    question: str,
    history: list[tuple[str, str | None]],
    emit: Emit,
) -> dict[str, Any]:
    started = time.perf_counter()
    ctx = PipelineContext(run_id=run_id, user_id=user_id, role=role, question=question,
                          conversation_id=conversation_id, history=history)  # fmt: skip
    async with services.sessionmaker() as session:
        try:
            app_settings = await load_app_settings(session)
            await Pipeline(services, app_settings, emit=emit).run(ctx, session)
        except Exception as error:  # never leave a run stuck in "running"
            log.exception("pipeline.crashed", run_id=str(run_id))
            ctx.finish("failed", "INTERNAL_ERROR")
            ctx.steps.append(
                StepRecord("pipeline", "error", datetime.now(UTC), 0, {"error": str(error)[:300]})
            )
        await session.rollback()
        run = await persist(session, ctx, int((time.perf_counter() - started) * 1000))
        view = await load_view(session, run)
    if ctx.status in ("rejected", "failed") and ctx.suggestions:
        view["suggestions"] = ctx.suggestions
    if view["message"] is None and ctx.error_code:
        view["message"] = message(ctx.error_code, ctx.lang)
    return view
