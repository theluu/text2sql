import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models._types import created_at, fk, pk
from app.models.base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = fk("users.id")
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at()


class QueryRun(Base):
    __tablename__ = "query_runs"

    id: Mapped[uuid.UUID] = pk()
    conversation_id: Mapped[uuid.UUID | None] = fk("conversations.id", nullable=True)
    user_id: Mapped[uuid.UUID] = fk("users.id")
    question: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(String(5))
    rewritten_question: Mapped[str | None] = mapped_column(Text)
    final_sql: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    # answered | pending_review | rejected | failed | running
    status: Mapped[str] = mapped_column(String(20), index=True)
    risk_decision: Mapped[str | None] = mapped_column(String(20))
    review_reasons: Mapped[list[str]] = mapped_column(JSONB, default=list)
    confidence: Mapped[float | None] = mapped_column(Float)
    provider_used: Mapped[str | None] = mapped_column(String(40))
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    guardrail_code: Mapped[str | None] = mapped_column(String(40))
    row_count: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    result_preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    chart_spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"

    id: Mapped[uuid.UUID] = pk()
    query_run_id: Mapped[uuid.UUID] = fk("query_runs.id")
    step: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
