import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models._types import created_at, fk, pk
from app.models.base import Base


class JudgeVerdict(Base):
    __tablename__ = "judge_verdicts"

    id: Mapped[uuid.UUID] = pk()
    query_run_id: Mapped[uuid.UUID] = fk("query_runs.id")
    judge_model: Mapped[str] = mapped_column(String(80))
    verdict: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float)
    rubric: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    issues: Mapped[list[str]] = mapped_column(JSONB, default=list)
    same_vendor: Mapped[bool] = mapped_column(Boolean, default=False)


class GuardrailEvent(Base):
    __tablename__ = "guardrail_events"

    id: Mapped[uuid.UUID] = pk()
    query_run_id: Mapped[uuid.UUID | None] = fk("query_runs.id", nullable=True)
    layer: Mapped[str] = mapped_column(String(4))
    code: Mapped[str] = mapped_column(String(40), index=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = created_at()
