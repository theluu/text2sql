"""Risk gate: AUTO_EXECUTE | NEEDS_REVIEW | REJECT, plus the confidence blend."""

from dataclasses import dataclass, field
from typing import Any, Literal

Decision = Literal["AUTO_EXECUTE", "NEEDS_REVIEW", "REJECT"]

# Review-queue priority weight per reason (priority = weight × age).
REASON_WEIGHTS: dict[str, float] = {
    "PII_ACCESS": 3.0,
    "JUDGE_FAIL": 2.5,
    "USER_DOWNVOTE": 2.0,
    "COST_GRAY": 2.0,
    "JUDGE_UNCERTAIN": 1.5,
    "LOW_CONFIDENCE": 1.5,
    "FALLBACK_LOW_CONFIDENCE": 1.0,
}


@dataclass
class RiskSettings:
    review_confidence: float = 0.7
    fallback_confidence: float = 0.8
    gray_cost: float = 500_000.0
    max_cost: float = 50_000_000.0
    w_self: float = 0.2
    w_judge: float = 0.5
    w_agreement: float = 0.3

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RiskSettings":
        known = {k: float(v) for k, v in raw.items() if k in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class RiskInputs:
    role: str
    confidence: float
    hard_block_code: str | None = None
    judge_verdict: str | None = None  # pass | fail | uncertain | None (judge unavailable)
    pii_columns: list[str] = field(default_factory=list)
    used_fallback: bool = False
    cost: float | None = None


@dataclass
class RiskDecision:
    decision: Decision
    reasons: list[str]

    @property
    def weight(self) -> float:
        return max((REASON_WEIGHTS.get(r, 1.0) for r in self.reasons), default=1.0)


def confidence(
    self_confidence: float,
    judge_score: float | None,
    agreement: float | None,
    settings: RiskSettings,
) -> float:
    """0.2·self + 0.5·judge + 0.3·agreement; missing parts drop out and weights renormalize."""
    parts = [(settings.w_self, self_confidence)]
    if judge_score is not None:
        parts.append((settings.w_judge, judge_score))
    if agreement is not None:
        parts.append((settings.w_agreement, agreement))
    total = sum(w for w, _ in parts)
    value = sum(w * v for w, v in parts) / total if total else 0.0
    return round(min(max(value, 0.0), 1.0), 3)


def decide(inputs: RiskInputs, settings: RiskSettings) -> RiskDecision:
    if inputs.hard_block_code:
        return RiskDecision("REJECT", [inputs.hard_block_code])
    if inputs.cost is not None and inputs.cost > settings.max_cost:
        return RiskDecision("REJECT", ["COST_TOO_HIGH"])
    reasons: list[str] = []
    if inputs.judge_verdict == "fail":
        reasons.append("JUDGE_FAIL")
    elif inputs.judge_verdict == "uncertain":
        reasons.append("JUDGE_UNCERTAIN")
    if inputs.used_fallback:
        if inputs.confidence < settings.fallback_confidence:
            reasons.append("FALLBACK_LOW_CONFIDENCE")
    elif inputs.confidence < settings.review_confidence:
        reasons.append("LOW_CONFIDENCE")
    if inputs.role == "viewer" and inputs.pii_columns:
        reasons.append("PII_ACCESS")
    if inputs.cost is not None and inputs.cost >= settings.gray_cost:
        reasons.append("COST_GRAY")
    return RiskDecision("NEEDS_REVIEW" if reasons else "AUTO_EXECUTE", reasons)
