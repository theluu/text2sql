"""AI-as-a-Judge: a different vendor than the generator grades SQL + preview on a rubric."""

import json
from dataclasses import dataclass, field
from typing import Any

from app.llm.base import Message
from app.llm.router import Attempt, LLMRouter
from app.pipeline.prompts import JUDGE_SCHEMA, JUDGE_SYSTEM, RUBRIC


@dataclass
class JudgeResult:
    verdict: str  # pass | fail | uncertain
    score: float
    rubric: dict[str, Any]
    issues: list[str]
    suggested_fix: str
    provider: str
    model: str
    same_vendor: bool
    attempts: list[Attempt] = field(default_factory=list)

    def to_detail(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "score": self.score,
            "rubric": self.rubric,
            "issues": self.issues,
            "provider": self.provider,
            "model": self.model,
            "same_vendor": self.same_vendor,
        }


def normalize_verdict(raw: dict[str, Any]) -> tuple[str, float, dict[str, Any], list[str], str]:
    rubric = {k: raw.get("rubric", {}).get(k, {"score": 3, "reason": ""}) for k in RUBRIC}
    scores = [min(max(int(v.get("score", 3)), 1), 5) for v in rubric.values()]
    rubric_score = (sum(scores) / len(scores) - 1) / 4
    try:
        score = float(raw.get("score", rubric_score))
    except (TypeError, ValueError):
        score = rubric_score
    score = round(min(max(score, 0.0), 1.0), 3)
    verdict = (
        raw.get("verdict") if raw.get("verdict") in ("pass", "fail", "uncertain") else "uncertain"
    )
    # A "pass" with a weak rubric is not a pass.
    if verdict == "pass" and (min(scores) <= 2 or score < 0.6):
        verdict = "uncertain"
    issues = [str(i) for i in raw.get("issues", []) if str(i).strip()][:10]
    return str(verdict), score, rubric, issues, str(raw.get("suggested_fix") or "")


async def judge(
    router: LLMRouter,
    *,
    question: str,
    schema_text: str,
    sql: str,
    preview: dict[str, Any],
    generator_vendor: str | None,
) -> JudgeResult:
    rows = preview.get("rows", [])[:20]
    user = (
        f"<question>{question}</question>\n<schema>\n{schema_text}\n</schema>\n"
        f"<sql>\n{sql}\n</sql>\n<result>\ncolumns: {json.dumps(preview.get('columns', []), ensure_ascii=False)}\n"
        f"rows (first {len(rows)} of {preview.get('row_count', len(rows))}): "
        f"{json.dumps(rows, ensure_ascii=False, default=str)}\n</result>"
    )
    routed = await router.complete(
        "judge",
        [Message("system", JUDGE_SYSTEM), Message("user", user)],
        schema=JUDGE_SCHEMA,
        schema_name="judge_verdict",
        avoid_vendor=generator_vendor,
    )
    verdict, score, rubric, issues, fix = normalize_verdict(routed.response.content)
    return JudgeResult(
        verdict=verdict,
        score=score,
        rubric=rubric,
        issues=issues,
        suggested_fix=fix,
        provider=routed.response.provider,
        model=routed.response.model,
        same_vendor=generator_vendor is not None and routed.response.vendor == generator_vendor,
        attempts=routed.attempts,
    )
