import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth.deps import CurrentUser
from app.services.ask import ConversationNotFound, answer, prepare
from app.services.deps import ServicesDep

router = APIRouter(tags=["query"])


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/query")
async def query(body: QueryRequest, user: CurrentUser, services: ServicesDep) -> StreamingResponse:
    if not await services.rate_limiter.hit(str(user.id)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limited")
    try:
        run_id, conversation_id, history = await prepare(
            services, user.id, body.question, body.conversation_id
        )
    except ConversationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="conversation_not_found") from None
    user_id, role = user.id, user.role.value
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

    async def emit(event: str, data: dict[str, Any]) -> None:
        await queue.put((event, data))

    async def work() -> None:
        try:
            view = await answer(
                services, run_id=run_id, conversation_id=conversation_id, user_id=user_id,
                role=role, question=body.question, history=history, emit=emit,
            )  # fmt: skip
            await queue.put(("result", view))
        except Exception:
            await queue.put(("error", {"code": "INTERNAL_ERROR", "run_id": str(run_id)}))
        finally:
            await queue.put(None)

    # The pipeline keeps running (and persists) even if the client disconnects.
    task = asyncio.create_task(work())

    async def stream() -> AsyncIterator[str]:
        yield sse("meta", {"run_id": str(run_id), "conversation_id": str(conversation_id)})
        while (item := await queue.get()) is not None:
            yield sse(*item)
        await task

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
