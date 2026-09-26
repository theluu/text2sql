import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.core.db import get_session
from app.hitl.feedback_service import FeedbackError, record_feedback
from app.services.deps import ServicesDep

router = APIRouter(tags=["notifications"])


@router.get("/notifications/stream")
async def stream(request: Request, user: CurrentUser, services: ServicesDep) -> StreamingResponse:
    user_id = user.id

    async def events() -> AsyncIterator[str]:
        yield ": connected\n\n"
        async for event in services.notifier.subscribe(user_id):
            if await request.is_disconnected():
                break
            if event is None:
                yield ": heartbeat\n\n"
            else:
                yield f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})  # fmt: skip


class FeedbackBody(BaseModel):
    rating: str = Field(pattern="^(up|down)$")
    comment: str | None = Field(default=None, max_length=1000)


feedback_router = APIRouter(tags=["feedback"])


@feedback_router.post("/query-runs/{run_id}/feedback")
async def feedback(
    run_id: uuid.UUID,
    body: FeedbackBody,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    try:
        review_opened = await record_feedback(session, run_id, user.id, body.rating, body.comment)
    except FeedbackError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="not_found") from None
    return {"ok": True, "review_opened": review_opened}
