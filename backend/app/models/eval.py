import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models._types import created_at, fk, pk
from app.models.base import Base


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[uuid.UUID] = pk()
    key: Mapped[str] = mapped_column(String(80), unique=True)
    suite: Mapped[str] = mapped_column(String(20), index=True)
    question: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(String(5))
    role: Mapped[str] = mapped_column(String(10))
    gold_sql: Mapped[str | None] = mapped_column(Text)
    expected_behavior: Mapped[str] = mapped_column(String(10))
    difficulty: Mapped[str] = mapped_column(String(10))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(30)), default=list)
    source: Mapped[str] = mapped_column(String(10), default="seed")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = pk()
    suite: Mapped[str] = mapped_column(String(20))
    git_sha: Mapped[str | None] = mapped_column(String(40))
    prompt_version: Mapped[str] = mapped_column(String(20))
    model_chain: Mapped[list[str]] = mapped_column(JSONB, default=list)
    mode: Mapped[str] = mapped_column(String(40))
    # queued | running | done | failed
    status: Mapped[str] = mapped_column(String(10))
    total: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = pk()
    eval_run_id: Mapped[uuid.UUID] = fk("eval_runs.id")
    eval_case_id: Mapped[uuid.UUID] = fk("eval_cases.id")
    predicted_sql: Mapped[str | None] = mapped_column(Text)
    behavior: Mapped[str] = mapped_column(String(10))
    ex_match: Mapped[bool | None] = mapped_column(Boolean)
    esm_match: Mapped[bool | None] = mapped_column(Boolean)
    judge_verdict: Mapped[str | None] = mapped_column(String(20))
    guardrail_code: Mapped[str | None] = mapped_column(String(40))
    provider_used: Mapped[str | None] = mapped_column(String(40))
    used_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    linked_tables: Mapped[list[str]] = mapped_column(JSONB, default=list)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = created_at()
