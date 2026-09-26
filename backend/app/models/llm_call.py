import uuid
from datetime import datetime

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models._types import created_at, fk, pk
from app.models.base import Base


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = pk()
    query_run_id: Mapped[uuid.UUID | None] = fk("query_runs.id", nullable=True)
    eval_result_id: Mapped[uuid.UUID | None] = fk("eval_results.id", nullable=True)
    purpose: Mapped[str] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str] = mapped_column(String(80))
    attempt: Mapped[int] = mapped_column(Integer)
    # ok | timeout | error | circuit_open | parse_fail | chaos | rate_limit
    outcome: Mapped[str] = mapped_column(String(20))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = created_at()
