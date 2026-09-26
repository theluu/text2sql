import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.text import normalize
from app.llm.router import Attempt
from app.pipeline.judge import JudgeResult
from app.pipeline.risk import RiskDecision
from app.pipeline.sql_guard import SqlCheck
from app.semantic.linker import LinkedSchema
from app.warehouse.executor import QueryResult


@dataclass
class Candidate:
    sql: str
    explanation: str
    self_confidence: float
    source: str  # llm | rule_based | verified_example
    provider: str
    vendor: str | None = None
    model: str | None = None
    intent: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def used_fallback(self) -> bool:
        return self.source == "rule_based"


@dataclass
class StepRecord:
    step: str
    status: str  # ok | error | skip
    started_at: datetime
    duration_ms: int
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"step": self.step, "status": self.status, "duration_ms": self.duration_ms,
                "detail": self.detail}  # fmt: skip


@dataclass
class PipelineContext:
    run_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    question: str
    conversation_id: uuid.UUID | None = None
    history: list[tuple[str, str | None]] = field(default_factory=list)
    lang: str = "vi"
    rewritten_question: str | None = None
    linked: LinkedSchema | None = None
    schema_text: str = ""
    fewshots: list[dict[str, Any]] = field(default_factory=list)
    candidate: Candidate | None = None
    check: SqlCheck | None = None
    cost: float | None = None
    result: QueryResult | None = None
    judge: JudgeResult | None = None
    agreement: float | None = None
    confidence: float | None = None
    decision: RiskDecision | None = None
    status: str = "running"
    error_code: str | None = None
    masked_columns: list[str] = field(default_factory=list)
    summary: str | None = None
    chart: dict[str, Any] | None = None
    suggestions: list[str] = field(default_factory=list)
    cache_hit: bool = False
    repairs: int = 0
    guardrail_events: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    llm_attempts: list[Attempt] = field(default_factory=list)
    steps: list[StepRecord] = field(default_factory=list)
    finished: bool = False

    @property
    def effective_question(self) -> str:
        return self.rewritten_question or self.question

    def guardrail(self, layer: str, code: str, **detail: Any) -> None:
        self.guardrail_events.append((layer, code, detail))

    def finish(self, status: str, code: str | None = None) -> None:
        self.status, self.error_code, self.finished = status, code, True


HARD_SIGNALS = re.compile(
    r"luy ke|cumulative|running total|xep hang|\brank|trung binh truot|moving average|ty trong|"
    r"share of|percent of total|phan tram (tren )?tong|so voi|so sanh|compared?|\bvs\b|versus|"
    r"tang truong|growth|cung ky|\bmom\b|\byoy\b|moi khach|per customer|trung vi|median"
)


def is_hard(question: str, linked: LinkedSchema | None) -> bool:
    """Heuristic difficulty: window/comparison phrasing, or many tables at once."""
    signals = len(set(HARD_SIGNALS.findall(normalize(question))))
    if linked and len(linked.tables) >= 6:
        signals += 1
    return signals >= 1
