"""The PLAN section 6 metrics: known values, intervals and determinism."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pipeline_support import make_complaint

from field_return_triage.contracts import (
    Clue,
    DroppedClue,
    Extraction,
    Neighbour,
    QuoteCheck,
    TriageCard,
)
from field_return_triage.pipeline import metrics
from field_return_triage.rules.hard_rules import build_card
from field_return_triage.rules.rulebook import Rulebook

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def _card(
    rulebook: Rulebook,
    *,
    complaint_id: str = "c-1",
    group: str = "instrument_panel_displays",
    predicted_group: str = "instrument_panel_displays",
    symptoms: tuple[Clue, ...] = (),
    conditions: tuple[Clue, ...] = (),
    safety: bool = False,
    coded: tuple[bool, bool, bool] = (False, False, False),
    checked: int = 1,
    passed: int = 1,
    neighbours: tuple[Neighbour, ...] = (),
) -> TriageCard:
    complaint = make_complaint(
        id=complaint_id,
        group=group,
        crash=coded[0],
        fire=coded[1],
        injury=coded[2],
    )
    extraction = Extraction(
        component_group=predicted_group,
        safety_relevant=safety,
        safety_quote="smoke" if safety else None,
        symptoms=symptoms,
        conditions=conditions,
    )
    dropped = tuple(
        DroppedClue(field="symptoms", kind="other", quote=f"q{index}")
        for index in range(max(0, checked - passed))
    )
    check = QuoteCheck(checked=checked, passed=passed, dropped=dropped)
    return build_card(
        complaint,
        extraction,
        check,
        neighbours=neighbours,
        rulebook=rulebook,
        model_id="fake-model",
        keywords=("smoke",),
        now=NOW,
    )


def test_bootstrap_ci_is_deterministic_and_contains_the_mean() -> None:
    values = [0.0, 0.5, 1.0, 0.25, 0.75]
    first = metrics.bootstrap_ci(values)
    second = metrics.bootstrap_ci(values)
    assert first == second
    assert first[0] <= 0.5 <= first[1]


def test_bootstrap_ci_rejects_an_empty_sample() -> None:
    with pytest.raises(ValueError, match="at least one value"):
        metrics.bootstrap_ci([])


def test_wilson_interval_edges_and_bounds() -> None:
    low, high = metrics.wilson_interval(0, 10)
    assert low == 0.0
    assert 0.0 < high < 0.5
    low, high = metrics.wilson_interval(10, 10)
    assert 0.5 < low < 1.0
    assert high == pytest.approx(1.0)
    assert metrics.wilson_interval(0, 0) == (None, None)
    with pytest.raises(ValueError, match="between 0 and trials"):
        metrics.wilson_interval(11, 10)


def test_macro_f1_perfect_and_unclear_counts_as_wrong() -> None:
    perfect = metrics.macro_f1(["a", "b"], ["a", "b"])
    assert perfect.value == 1.0
    unclear = metrics.macro_f1(["a", "b"], ["a", "unclear"])
    assert unclear.value is not None
    assert 0.0 < unclear.value < 1.0
    # Predicting "unclear" never earns credit for the true group b.
    assert unclear.value == pytest.approx(0.5)


def test_accuracy_coverage_and_answered_accuracy() -> None:
    gold = ["a", "a", "b", "b"]
    predicted = ["a", "unclear", "b", "unclear"]
    assert metrics.accuracy(gold, predicted).value == 0.5
    assert metrics.coverage(predicted).value == 0.5
    assert metrics.answered_accuracy(gold, predicted).value == 1.0


def test_undefined_scores_are_none_not_zero() -> None:
    assert metrics.macro_f1([], []).value is None
    assert metrics.coverage([]).value is None
    assert metrics.quote_grounding([]).value is None
    assert metrics.routing([])["priority_1_share"].value is None


def test_safety_scores_final_and_model_only(rulebook: Rulebook) -> None:
    coded = (True, False, False)
    cards = [
        _card(
            rulebook,
            complaint_id="hit",
            group="airbags",
            predicted_group="airbags",
            safety=True,
            coded=coded,
        ),
        _card(
            rulebook,
            complaint_id="quiet",
            group="airbags",
            predicted_group="airbags",
            safety=False,
            coded=coded,
        ),
        _card(
            rulebook,
            complaint_id="false-alarm",
            group="airbags",
            predicted_group="airbags",
            safety=True,
            coded=(False, False, False),
        ),
    ]
    scores = metrics.safety_scores(cards, None)
    # The final decision includes the coded field, so both coded items are found.
    assert scores["final_recall"].value == 1.0
    assert scores["final_precision"].value == pytest.approx(2 / 3)
    # The model's own flag alone finds one of the two coded items.
    assert scores["model_recall"].value == 0.5
    assert scores["model_precision"].value == 0.5


def test_quote_grounding_aggregates_checked_and_passed(rulebook: Rulebook) -> None:
    first = _card(rulebook, complaint_id="a", checked=3, passed=2)
    second = _card(rulebook, complaint_id="b", checked=2, passed=2)
    metric = metrics.quote_grounding([first, second])
    assert metric.value == pytest.approx(4 / 5)


def test_condition_agreement_is_one_when_both_sides_agree(rulebook: Rulebook) -> None:
    card = _card(
        rulebook,
        conditions=(Clue(kind="moisture", quote="after rain"),),
        checked=1,
        passed=1,
    )
    metric = metrics.condition_agreement(
        [card],
        {"moisture": ("rain",), "heat": ("hot",)},
    )
    assert metric.value == 1.0


def test_condition_agreement_counts_a_miss(rulebook: Rulebook) -> None:
    card = _card(rulebook, conditions=(), checked=1, passed=1)
    metric = metrics.condition_agreement(
        [card],
        {"moisture": ("rain",), "heat": ("hot",)},
    )
    assert metric.value == 0.0


def test_routing_shares(rulebook: Rulebook) -> None:
    safety = _card(rulebook, complaint_id="s", safety=True)
    unclear = _card(rulebook, complaint_id="u", predicted_group="unclear")
    shares = metrics.routing([safety, unclear])
    assert shares["priority_1_share"].value == 0.5
    assert shares["needs_human_share"].value == 1.0


def test_similar_precision_counts_matching_groups(rulebook: Rulebook) -> None:
    neighbours = (
        Neighbour(
            complaint_id="n-1",
            group="instrument_panel_displays",
            received=make_complaint().received,
            safety_relevant=False,
            excerpt="x",
            score=0.9,
        ),
        Neighbour(
            complaint_id="n-2",
            group="airbags",
            received=make_complaint().received,
            safety_relevant=False,
            excerpt="x",
            score=0.8,
        ),
    )
    card = _card(rulebook, neighbours=neighbours)
    metric = metrics.similar_precision([card])
    assert metric.value == 0.5


def test_latency_and_cost_metrics() -> None:
    latency = metrics.latency_ms([100.0, 200.0, 300.0, 400.0])
    assert latency["p50"].value == pytest.approx(250.0)
    assert latency["p95"].value is not None
    cost = metrics.cost_metrics([0.001, 0.003])
    assert cost["total_usd"].value == pytest.approx(0.004)
    assert cost["per_1000_usd"].value == pytest.approx(2.0)
    assert metrics.latency_ms([])["p50"].value is None
    assert metrics.cost_metrics([])["total_usd"].value is None


def test_metrics_and_labels_must_have_the_same_length() -> None:
    with pytest.raises(ValueError, match="same length"):
        metrics.accuracy(["a"], [])
