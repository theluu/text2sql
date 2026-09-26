import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import ROLE_RANK, CurrentUser
from app.core.db import get_session
from app.models import Conversation, QueryRun, Role
from app.services.runs import load_view

router = APIRouter(tags=["conversations"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("/conversations")
async def list_conversations(user: CurrentUser, session: Session) -> list[dict[str, Any]]:
    last = (
        select(QueryRun.conversation_id, func.max(QueryRun.created_at).label("last_at"))
        .group_by(QueryRun.conversation_id)
        .subquery()
    )
    rows = await session.execute(
        select(Conversation, last.c.last_at)
        .join(last, last.c.conversation_id == Conversation.id, isouter=True)
        .where(Conversation.user_id == user.id)
        .order_by(func.coalesce(last.c.last_at, Conversation.created_at).desc())
        .limit(50)
    )
    return [
        {"id": str(c.id), "title": c.title, "created_at": c.created_at.isoformat(),
         "last_at": (last_at or c.created_at).isoformat()}
        for c, last_at in rows
    ]  # fmt: skip


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: Session
) -> dict[str, Any]:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    runs = await session.scalars(
        select(QueryRun)
        .where(QueryRun.conversation_id == conversation.id)
        .order_by(QueryRun.created_at)
    )
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "runs": [await load_view(session, run) for run in runs],
    }


@router.get("/query-runs/{run_id}")
async def get_run(run_id: uuid.UUID, user: CurrentUser, session: Session) -> dict[str, Any]:
    run = await session.get(QueryRun, run_id)
    reviewer = ROLE_RANK[user.role] >= ROLE_RANK[Role.analyst]
    if run is None or (run.user_id != user.id and not reviewer):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found")
    return await load_view(session, run, for_reviewer=reviewer and run.user_id != user.id)
