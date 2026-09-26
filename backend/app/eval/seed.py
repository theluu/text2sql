"""Load eval datasets (YAML) into `eval_cases`. Idempotent: upsert by key."""

from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EvalCase

DATASET_DIR = Path(__file__).resolve().parents[2] / "eval" / "datasets"


def load_dataset_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted(DATASET_DIR.glob("*.yaml")):
        cases += yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]
    return cases


async def seed_eval_cases(session: AsyncSession) -> int:
    rows = []
    for case in load_dataset_cases():
        tags = list(case.get("tags", [])) + (["smoke"] if case.get("smoke") else [])
        rows.append({
            "key": case["key"], "suite": "full", "question": case["question"], "lang": case["lang"],
            "role": case["role"], "gold_sql": case.get("gold_sql"), "expected_behavior": case["expected_behavior"],
            "difficulty": case["difficulty"], "tags": tags, "source": "seed", "active": True,
        })  # fmt: skip
    if not rows:
        return 0
    statement = insert(EvalCase).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["key"],
        set_={col: statement.excluded[col] for col in
              ("question", "lang", "role", "gold_sql", "expected_behavior", "difficulty", "tags", "active")},
    )  # fmt: skip
    await session.execute(statement)
    await session.commit()
    return len(rows)
