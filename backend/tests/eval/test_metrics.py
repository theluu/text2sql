import json
from pathlib import Path

import pytest

from app.eval.cassette import Cassette, RecordingProvider, ReplayProvider, with_cassette
from app.eval.comparators import exact_structure_match, has_order_by, results_match
from app.eval.metrics import CaseOutcome, cohen_kappa, percentile, summarize, tables_in
from app.eval.runner import gate
from app.eval.seed import load_dataset_cases
from app.llm.base import Message, ProviderError
from app.llm.fake import FakeLLMProvider


@pytest.mark.parametrize(
    ("gold", "pred", "ordered", "expected"),
    [
        ([["a", 1], ["b", 2]], [["b", 2], ["a", 1]], False, True),
        ([["a", 1], ["b", 2]], [["b", 2], ["a", 1]], True, False),
        ([["a", 1]], [[1, "a"]], False, True),  # column order and names do not matter
        ([[1.0000001]], [[1.0000002]], False, True),  # 1e-6 relative tolerance
        ([[1.0]], [[1.01]], False, False),
        ([[100]], [["100"]], False, True),
        ([[None]], [[None]], False, True),
        ([["a", 1]], [["a", 1], ["a", 1]], False, False),
        ([], [], False, True),
    ],
)
def test_results_match(
    gold: list[list[object]], pred: list[list[object]], ordered: bool, expected: bool
) -> None:
    assert results_match(gold, pred, ordered=ordered) is expected


def test_order_by_detection_and_esm() -> None:
    assert has_order_by("SELECT a FROM t ORDER BY a")
    assert not has_order_by("SELECT a FROM t")
    assert exact_structure_match("SELECT a AS x FROM orders o WHERE o.id = 1",
                                 "select a from orders where id = 1 limit 1000")  # fmt: skip
    assert not exact_structure_match("SELECT a FROM orders", "SELECT b FROM orders")


def test_kappa_percentile_and_tables() -> None:
    assert cohen_kappa([True, False, True, False], [True, False, True, False]) == 1.0
    assert cohen_kappa([True, True, False, False], [True, False, True, False]) == 0.0
    assert cohen_kappa([], []) is None
    assert percentile([10, 20, 30, 40], 0.5) in (20.0, 30.0)
    assert tables_in("WITH x AS (SELECT * FROM v_customers_masked) SELECT * FROM x JOIN orders o USING (customer_id)") == [
        "customers", "orders",
    ]  # fmt: skip


def _o(key: str, expected: str, behavior: str, **kw: object) -> CaseOutcome:
    return CaseOutcome(key=key, difficulty=kw.pop("difficulty", "easy"), tags=kw.pop("tags", []),  # type: ignore[arg-type]
                       expected=expected, behavior=behavior, **kw)  # type: ignore[arg-type]  # fmt: skip


def test_summary_metrics() -> None:
    outcomes = [
        _o(
            "a",
            "answer",
            "answer",
            ex=True,
            judge_verdict="pass",
            gold_tables=["orders"],
            linked_tables=["orders"],
        ),
        _o(
            "b",
            "answer",
            "review",
            ex=False,
            judge_verdict="fail",
            gold_tables=["orders", "stores"],
            linked_tables=["orders"],
            difficulty="hard",
        ),  # fmt: skip
        _o("c", "reject", "reject", tags=["adversarial"]),
        _o("d", "reject", "answer", tags=["adversarial"]),
        _o("e", "review", "reject", tags=["ambiguous"]),
    ]
    summary = summarize(outcomes)
    assert summary["ex"] == 0.5
    assert summary["behavior_accuracy"] == 0.4
    assert summary["guardrail_recall"] == 0.5 and summary["guardrail_precision"] == 0.5
    assert summary["adversarial_leaks"] == ["d"]
    assert summary["judge_precision"] == 1.0 and summary["judge_recall"] == 1.0
    assert summary["linking_recall"] == 0.75
    assert summary["by_difficulty"]["hard"]["ex"] == 0.0


def test_gate() -> None:
    assert gate({"ex": 0.80, "adversarial_leaks": []}, {"ex": 0.81}) == []
    assert gate({"ex": 0.78, "adversarial_leaks": []}, {"ex": 0.81})
    assert gate({"ex": 0.9, "adversarial_leaks": ["v03"]}, {"ex": 0.8})


def test_dataset_shape() -> None:
    cases = load_dataset_cases()
    assert len(cases) >= 120
    assert len({c["key"] for c in cases}) == len(cases)
    assert sum(1 for c in cases if c.get("smoke")) == 30
    assert {c["lang"] for c in cases} == {"vi", "en"}
    assert {c["difficulty"] for c in cases} == {"easy", "medium", "hard", "extra"}
    assert {c["expected_behavior"] for c in cases} == {"answer", "review", "reject"}
    for case in cases:
        assert (case["gold_sql"] is not None) == (case["expected_behavior"] == "answer"), case[
            "key"
        ]
    tags = {t for c in cases for t in c["tags"]}
    assert {
        "aggregation",
        "join3",
        "time_window",
        "window_fn",
        "ambiguous",
        "adversarial",
        "pii_access",
    } <= tags


async def test_cassette_records_and_replays(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    real = FakeLLMProvider("anthropic", "anthropic", [{"sql": "SELECT 1"}], model="m1")
    wrapped, cassette = with_cassette({"anthropic": real}, "record", path)
    messages = [Message("user", "hi")]
    await wrapped["anthropic"].complete(messages, schema={}, schema_name="gen", timeout_s=1)
    assert isinstance(wrapped["anthropic"], RecordingProvider) and cassette
    cassette.save()
    assert json.loads(path.read_text())["providers"] == {
        "anthropic": {"vendor": "anthropic", "model": "m1"}
    }

    replay, _ = with_cassette({}, "replay", path)
    provider = replay["anthropic"]
    assert isinstance(provider, ReplayProvider)
    response = await provider.complete(messages, schema={}, schema_name="gen", timeout_s=1)
    assert response.content == {"sql": "SELECT 1"}
    with pytest.raises(ProviderError):
        await provider.complete(
            [Message("user", "unseen")], schema={}, schema_name="gen", timeout_s=1
        )
    assert Cassette(tmp_path / "missing.json").entries == {}
