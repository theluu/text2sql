import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_min_role
from app.core.db import get_session
from app.hitl import review_service
from app.hitl.review_service import ReviewError
from app.models import Role, User
from app.services.deps import ServicesDep
from app.services.runs import load_view

router = APIRouter(tags=["review"])
Session = Annotated[AsyncSession, Depends(get_session)]
Reviewer = Annotated[User, Depends(require_min_role(Role.analyst))]

ERROR_STATUS = {
    "not_found": status.HTTP_404_NOT_FOUND,
    "already_resolved": status.HTTP_409_CONFLICT,
    "claimed_by_other": status.HTTP_409_CONFLICT,
    "note_required": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "dry_run_failed": status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _raise(error: ReviewError) -> None:
    detail: Any = error.code if not error.detail else {"code": error.code, "message": error.detail}
    raise HTTPException(
        ERROR_STATUS.get(error.code, status.HTTP_400_BAD_REQUEST), detail=detail
    ) from error


class SqlBody(BaseModel):
    sql: str = Field(min_length=1, max_length=20_000)


class ResolveBody(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    add_to_golden: bool = False


class EditBody(ResolveBody):
    sql: str = Field(min_length=1, max_length=20_000)


class NoteBody(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


@router.get("/review")
async def list_queue(
    _: Reviewer,
    session: Session,
    status_filter: Annotated[str, Query(alias="status")] = "pending",
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "items": await review_service.queue(session, status_filter, reason),
        "pending": await review_service.pending_count(session),
    }


@router.get("/review/count")
async def pending(_: Reviewer, session: Session) -> dict[str, int]:
    return {"pending": await review_service.pending_count(session)}


@router.get("/review/{item_id}")
async def detail(item_id: uuid.UUID, _: Reviewer, session: Session) -> dict[str, Any]:
    try:
        item, run, asker = await review_service.load(session, item_id)
    except ReviewError as error:
        _raise(error)
        raise
    return {
        "id": str(item.id),
        "status": item.status,
        "reasons": item.reasons,
        "original_sql": item.original_sql,
        "final_sql": item.final_sql,
        "note": item.reviewer_note,
        "add_to_golden": item.add_to_golden,
        "assignee_id": str(item.assignee_id) if item.assignee_id else None,
        "created_at": item.created_at.isoformat(),
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "asker": {"name": asker.name, "email": asker.email, "role": asker.role.value},
        "run": await load_view(session, run, for_reviewer=True),
    }


@router.post("/review/{item_id}/claim")
async def claim(item_id: uuid.UUID, reviewer: Reviewer, session: Session) -> dict[str, str]:
    try:
        item = await review_service.claim(session, item_id, reviewer)
    except ReviewError as error:
        _raise(error)
        raise
    return {"status": item.status}


@router.post("/review/{item_id}/dry-run")
async def dry_run(
    item_id: uuid.UUID, body: SqlBody, _: Reviewer, session: Session, services: ServicesDep
) -> dict[str, Any]:
    try:
        asker = (await review_service.load(session, item_id))[2]
    except ReviewError as error:
        _raise(error)
        raise
    return (await review_service.dry_run(services, body.sql, asker.role.value)).to_dict()


async def _resolve(
    services: Any, session: AsyncSession, item_id: uuid.UUID, reviewer: User, **kwargs: Any
) -> dict[str, str]:
    try:
        item = await review_service.resolve(
            services, services.notifier, session, item_id, reviewer, **kwargs
        )
    except ReviewError as error:
        _raise(error)
        raise
    return {"status": item.status}


@router.post("/review/{item_id}/approve")
async def approve(item_id: uuid.UUID, body: ResolveBody, reviewer: Reviewer, session: Session,
                  services: ServicesDep) -> dict[str, str]:  # fmt: skip
    return await _resolve(services, session, item_id, reviewer, action="approve", note=body.note,
                          add_to_golden=body.add_to_golden)  # fmt: skip


@router.post("/review/{item_id}/edit")
async def edit(item_id: uuid.UUID, body: EditBody, reviewer: Reviewer, session: Session,
               services: ServicesDep) -> dict[str, str]:  # fmt: skip
    return await _resolve(services, session, item_id, reviewer, action="edit", sql=body.sql, note=body.note,
                          add_to_golden=body.add_to_golden)  # fmt: skip


@router.post("/review/{item_id}/reject")
async def reject(item_id: uuid.UUID, body: NoteBody, reviewer: Reviewer, session: Session,
                 services: ServicesDep) -> dict[str, str]:  # fmt: skip
    return await _resolve(services, session, item_id, reviewer, action="reject", note=body.note)


@router.post("/review/{item_id}/return")
async def return_to_asker(item_id: uuid.UUID, body: NoteBody, reviewer: Reviewer, session: Session,
                          services: ServicesDep) -> dict[str, str]:  # fmt: skip
    return await _resolve(services, session, item_id, reviewer, action="return", note=body.note)
