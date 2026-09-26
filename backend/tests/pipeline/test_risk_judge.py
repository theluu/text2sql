import pytest

from app.llm.circuit import CircuitBreaker, MemoryStore
from app.llm.fake import FakeLLMProvider
from app.llm.router import LLMRouter
from app.pipeline.judge import judge, normalize_verdict
from app.pipeline.risk import RiskInputs, RiskSettings, confidence, decide

S = RiskSettings()


@pytest.mark.parametrize(
    ("inputs", "decision", "reasons"),
    [
        (RiskInputs("analyst", 0.9, judge_verdict="pass"), "AUTO_EXECUTE", []),
        (RiskInputs("analyst", 0.9, hard_block_code="NON_SELECT"), "REJECT", ["NON_SELECT"]),
        (RiskInputs("analyst", 0.9, cost=9e9), "REJECT", ["COST_TOO_HIGH"]),
        (RiskInputs("analyst", 0.9, judge_verdict="fail"), "NEEDS_REVIEW", ["JUDGE_FAIL"]),
        (
            RiskInputs("analyst", 0.9, judge_verdict="uncertain"),
            "NEEDS_REVIEW",
            ["JUDGE_UNCERTAIN"],
        ),
        (RiskInputs("analyst", 0.69, judge_verdict="pass"), "NEEDS_REVIEW", ["LOW_CONFIDENCE"]),
        (RiskInputs("analyst", 0.7, judge_verdict="pass"), "AUTO_EXECUTE", []),
        (
            RiskInputs("viewer", 0.95, pii_columns=["v_customers_masked.email"]),
            "NEEDS_REVIEW",
            ["PII_ACCESS"],
        ),
        (RiskInputs("analyst", 0.95, pii_columns=["customers.email"]), "AUTO_EXECUTE", []),
        (
            RiskInputs("viewer", 0.75, used_fallback=True),
            "NEEDS_REVIEW",
            ["FALLBACK_LOW_CONFIDENCE"],
        ),
        (RiskInputs("viewer", 0.9, used_fallback=True), "AUTO_EXECUTE", []),
        (RiskInputs("viewer", 0.9, cost=1e6), "NEEDS_REVIEW", ["COST_GRAY"]),
        (RiskInputs("viewer", 0.9, judge_verdict=None), "AUTO_EXECUTE", []),
        (
            RiskInputs("viewer", 0.5, judge_verdict="fail", pii_columns=["x"], cost=1e6),
            "NEEDS_REVIEW",
            ["JUDGE_FAIL", "LOW_CONFIDENCE", "PII_ACCESS", "COST_GRAY"],
        ),
    ],
)
def test_risk_gate_decision_table(inputs: RiskInputs, decision: str, reasons: list[str]) -> None:
    result = decide(inputs, S)
    assert (result.decision, result.reasons) == (decision, reasons)


def test_priority_weight_uses_the_riskiest_reason() -> None:
    result = decide(RiskInputs("viewer", 0.5, pii_columns=["x"]), S)
    assert result.weight == 3.0


def test_confidence_formula() -> None:
    assert confidence(1.0, 1.0, 1.0, S) == 1.0
    assert confidence(0.5, 0.8, 1.0, S) == pytest.approx(0.2 * 0.5 + 0.5 * 0.8 + 0.3 * 1.0)
    # No self-consistency run: weights renormalize over self + judge.
    assert confidence(0.5, 0.8, None, S) == pytest.approx((0.2 * 0.5 + 0.5 * 0.8) / 0.7, abs=1e-3)
    assert confidence(0.85, None, None, S) == 0.85
    assert RiskSettings.from_dict({"review_confidence": "0.6", "junk": 1}).review_confidence == 0.6


def _verdict(verdict: str, score: float, rubric_score: int = 5) -> dict[str, object]:
    return {
        "verdict": verdict,
        "score": score,
        "rubric": {k: {"score": rubric_score, "reason": "ok"} for k in
                   ("intent", "schema_selection", "joins_filters", "aggregation", "result_sanity")},
        "issues": [],
        "suggested_fix": "",
    }  # fmt: skip


def test_weak_pass_is_downgraded_to_uncertain() -> None:
    assert normalize_verdict(_verdict("pass", 0.9))[0] == "pass"
    assert normalize_verdict(_verdict("pass", 0.4))[0] == "uncertain"
    assert normalize_verdict(_verdict("pass", 0.9, rubric_score=2))[0] == "uncertain"
    assert normalize_verdict({"verdict": "maybe"})[0] == "uncertain"


async def test_judge_prefers_another_vendor() -> None:
    claude = FakeLLMProvider("anthropic", "anthropic", [_verdict("fail", 0.2)])
    gpt = FakeLLMProvider("openai", "openai", [_verdict("pass", 0.9)])
    router = LLMRouter([claude, gpt], CircuitBreaker(MemoryStore()))
    result = await judge(router, question="q", schema_text="s", sql="SELECT 1",
                         preview={"columns": ["a"], "rows": [[1]]}, generator_vendor="anthropic")  # fmt: skip
    assert (result.provider, result.verdict, result.same_vendor) == ("openai", "pass", False)
    assert claude.calls == []
    assert "<result>" in gpt.calls[0][1][1].content


async def test_judge_labels_same_vendor_when_only_one_is_left() -> None:
    claude = FakeLLMProvider("anthropic", "anthropic", [_verdict("pass", 0.9)])
    router = LLMRouter([claude], CircuitBreaker(MemoryStore()))
    result = await judge(router, question="q", schema_text="s", sql="SELECT 1",
                         preview={"columns": [], "rows": []}, generator_vendor="anthropic")  # fmt: skip
    assert result.same_vendor
