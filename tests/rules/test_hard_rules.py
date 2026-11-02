"""Hard rules hr1: every branch, with safety winning over everything."""

from __future__ import annotations

import pytest
from helpers import (
    NOW,
    make_complaint,
    make_extraction,
    make_fault_code,
    make_mileage,
    make_neighbour,
    make_quote_check,
)

from field_return_triage.contracts import (
    PROMPT_VERSION,
    UNCLEAR_GROUP,
    Clue,
    DroppedClue,
    Priority,
    Reason,
    TriageCard,
)
from field_return_triage.rules.hard_rules import (
    HARD_RULE_VERSION,
    build_card,
    decides_safety,
    route,
    suggest,
)
from field_return_triage.rules.rulebook import Rulebook

# --- safety: three sources, fixed order ------------------------------------------------


def test_model_flag_is_safety_relevant_with_its_quote() -> None:
    extraction = make_extraction(safety_relevant=True, safety_quote="the unit caught fire")
    safety, reasons = decides_safety(make_complaint(), extraction, None)
    assert safety is True
    assert len(reasons) == 1
    assert "caught fire" in reasons[0]


def test_keyword_rule_alone_is_safety_relevant() -> None:
    safety, reasons = decides_safety(make_complaint(), make_extraction(), "SMOKE")
    assert safety is True
    assert "SMOKE" in reasons[0]


def test_coded_fire_field_alone_is_safety_relevant() -> None:
    safety, reasons = decides_safety(make_complaint(fire=True), make_extraction(), None)
    assert safety is True
    assert "fire" in reasons[0]


@pytest.mark.parametrize("field", ["crash", "fire", "injury"])
def test_each_coded_field_counts_on_its_own(field: str) -> None:
    complaint = make_complaint(**{field: True})
    safety, reasons = decides_safety(complaint, make_extraction(), None)
    assert safety is True
    assert field in reasons[0]


def test_no_source_means_not_safety_relevant() -> None:
    assert decides_safety(make_complaint(), make_extraction(), None) == (False, ())


def test_all_sources_are_reported_in_a_fixed_order() -> None:
    extraction = make_extraction(safety_relevant=True, safety_quote="caught fire")
    complaint = make_complaint(crash=True, injury=True)
    _, reasons = decides_safety(complaint, extraction, "smoke")
    assert len(reasons) == 3
    assert reasons[0].startswith("the model marked")
    assert reasons[1].startswith("a safety keyword")
    assert reasons[2].startswith("the coded fields")


# --- routing: safety first, then human reading, then clear clues -----------------------


def test_safety_routes_to_priority_one_and_human_review() -> None:
    priority, needs_human = route(
        make_complaint(), make_extraction(), make_quote_check(), safety=True
    )
    assert (priority, needs_human) == (Priority.SAFETY, True)


def test_coded_safety_cannot_be_lost_by_passing_safety_false() -> None:
    priority, needs_human = route(
        make_complaint(injury=True), make_extraction(), make_quote_check(), safety=False
    )
    assert (priority, needs_human) == (Priority.SAFETY, True)


def test_unclear_group_needs_human_reading() -> None:
    extraction = make_extraction(component_group=UNCLEAR_GROUP)
    priority, needs_human = route(make_complaint(), extraction, make_quote_check(), safety=False)
    assert (priority, needs_human) == (Priority.HUMAN_READING, True)


def test_no_passing_quote_needs_human_reading() -> None:
    check = make_quote_check(
        checked=2,
        passed=0,
        dropped=(
            DroppedClue(field="symptoms", kind="display_fault", quote="went dark"),
            DroppedClue(field="conditions", kind="moisture", quote="after rain"),
        ),
    )
    priority, needs_human = route(make_complaint(), make_extraction(), check, safety=False)
    assert (priority, needs_human) == (Priority.HUMAN_READING, True)


def test_no_clues_at_all_needs_human_reading() -> None:
    check = make_quote_check(checked=0, passed=0)
    extraction = make_extraction(symptoms=(), conditions=())
    priority, needs_human = route(make_complaint(), extraction, check, safety=False)
    assert (priority, needs_human) == (Priority.HUMAN_READING, True)


def test_clear_clues_route_to_priority_two_without_human_review() -> None:
    priority, needs_human = route(
        make_complaint(), make_extraction(), make_quote_check(), safety=False
    )
    assert (priority, needs_human) == (Priority.CLEAR_CLUES, False)


@pytest.mark.parametrize("unclear", [True, False])
@pytest.mark.parametrize("passed", [0, 2])
def test_safety_wins_over_every_other_branch(unclear: bool, passed: int) -> None:
    dropped = (
        ()
        if passed == 2
        else (
            DroppedClue(field="symptoms", kind="display_fault", quote="went dark"),
            DroppedClue(field="conditions", kind="moisture", quote="after rain"),
        )
    )
    check = make_quote_check(checked=2, passed=passed, dropped=dropped)
    extraction = make_extraction(component_group=UNCLEAR_GROUP if unclear else "instrument_cluster")
    priority, needs_human = route(make_complaint(), extraction, check, safety=True)
    assert (priority, needs_human) == (Priority.SAFETY, True)


# --- suggestions ----------------------------------------------------------------------

MOISTURE_TEST = "humidity / condensation test"
FALLBACK_REQUEST = ("when it happens", "how often", "under which conditions", "fault codes")


def test_a_condition_maps_to_its_rulebook_test_and_quotes(rulebook: Rulebook) -> None:
    suggestion = suggest(make_extraction(), make_quote_check(), rulebook)
    assert MOISTURE_TEST in suggestion.tests
    assert "connectors and seals" in suggestion.inspect
    assert len(suggestion.reasons) == 2
    moisture = next(reason for reason in suggestion.reasons if "moisture" in reason.text)
    assert moisture.quotes == ("after rain",)


def test_conditions_come_before_symptoms_in_the_suggestion(rulebook: Rulebook) -> None:
    extraction = make_extraction(
        conditions=(Clue(kind="heat", quote="after rain"),),
        symptoms=(Clue(kind="warning_light", quote="went dark"),),
    )
    suggestion = suggest(extraction, make_quote_check(), rulebook)
    assert suggestion.tests == (
        "high-temperature operation",
        "fault-code readout and warning-light circuit check",
    )
    assert [reason.text.split(" ")[0] for reason in suggestion.reasons] == ["heat", "warning_light"]


def test_a_fault_code_is_requested_when_none_was_extracted(rulebook: Rulebook) -> None:
    suggestion = suggest(make_extraction(), make_quote_check(), rulebook)
    assert "fault codes" in suggestion.request


def test_a_passing_fault_code_is_not_requested_again(rulebook: Rulebook) -> None:
    extraction = make_extraction(fault_codes=(make_fault_code(),))
    suggestion = suggest(extraction, make_quote_check(), rulebook)
    assert "fault codes" not in suggestion.request


def test_a_dropped_condition_is_not_used(rulebook: Rulebook) -> None:
    check = make_quote_check(
        checked=2,
        passed=0,
        dropped=(
            DroppedClue(field="symptoms", kind="display_fault", quote="went dark"),
            DroppedClue(field="conditions", kind="moisture", quote="after rain"),
        ),
    )
    suggestion = suggest(make_extraction(), check, rulebook)
    assert suggestion.tests == ("standard test",)
    assert suggestion.request == FALLBACK_REQUEST


def test_no_conditions_and_no_specific_symptom_falls_back_exactly(rulebook: Rulebook) -> None:
    extraction = make_extraction(symptoms=(), conditions=())
    suggestion = suggest(extraction, make_quote_check(checked=0, passed=0), rulebook)
    assert suggestion.tests == ("standard test",)
    assert suggestion.inspect == ()
    assert suggestion.request == FALLBACK_REQUEST
    assert len(suggestion.reasons) == 1
    assert "standard test" in suggestion.reasons[0].text
    assert suggestion.reasons[0].quotes == ()


def test_the_other_kind_alone_falls_back(rulebook: Rulebook) -> None:
    extraction = make_extraction(
        symptoms=(Clue(kind="other", quote="went dark"),),
        conditions=(),
    )
    suggestion = suggest(extraction, make_quote_check(), rulebook)
    assert suggestion.tests == ("standard test",)


def test_the_fallback_reason_points_at_the_clues_it_saw(rulebook: Rulebook) -> None:
    extraction = make_extraction(
        symptoms=(Clue(kind="other", quote="went dark"),),
        conditions=(),
    )
    suggestion = suggest(extraction, make_quote_check(), rulebook)
    assert suggestion.reasons[0].quotes == ("went dark",)


def test_shared_kind_intermittent_maps_from_a_symptom(rulebook: Rulebook) -> None:
    extraction = make_extraction(
        symptoms=(Clue(kind="intermittent", quote="intermittently"),),
        conditions=(),
    )
    suggestion = suggest(extraction, make_quote_check(), rulebook)
    assert suggestion.tests == ("long-run / power-cycling test with monitoring",)
    assert suggestion.reasons[0].quotes == ("intermittently",)


def test_two_clues_of_one_kind_share_one_reason_with_both_quotes(rulebook: Rulebook) -> None:
    extraction = make_extraction(
        conditions=(
            Clue(kind="moisture", quote="after rain"),
            Clue(kind="moisture", quote="wet road"),
        ),
        symptoms=(),
    )
    suggestion = suggest(extraction, make_quote_check(), rulebook)
    assert suggestion.tests == (MOISTURE_TEST,)
    assert suggestion.reasons[0].quotes == ("after rain", "wet road")


def test_suggestion_tests_are_deduplicated(rulebook: Rulebook) -> None:
    extraction = make_extraction(
        conditions=(
            Clue(kind="moisture", quote="after rain"),
            Clue(kind="moisture", quote="damp"),
        ),
        symptoms=(),
    )
    suggestion = suggest(extraction, make_quote_check(), rulebook)
    assert suggestion.tests == (MOISTURE_TEST,)


# --- card assembly --------------------------------------------------------------------


def build(
    rulebook: Rulebook,
    *,
    complaint: object | None = None,
    extraction: object | None = None,
    quote_check: object | None = None,
    neighbours: tuple[object, ...] = (),
    keywords: tuple[str, ...] = (),
) -> TriageCard:
    return build_card(
        make_complaint() if complaint is None else complaint,  # type: ignore[arg-type]
        make_extraction() if extraction is None else extraction,  # type: ignore[arg-type]
        make_quote_check() if quote_check is None else quote_check,  # type: ignore[arg-type]
        neighbours=neighbours,  # type: ignore[arg-type]
        rulebook=rulebook,
        model_id="model-x",
        keywords=keywords,
        now=NOW,
    )


def test_card_carries_priority_reasons_quotes_neighbours_and_versions(
    rulebook: Rulebook,
) -> None:
    neighbours = (make_neighbour(), make_neighbour(complaint_id="n-2", score=0.5))
    card = build(rulebook, neighbours=neighbours)
    assert card.priority is Priority.CLEAR_CLUES
    assert card.needs_human_review is False
    assert card.reasons
    assert card.quotes == ("went dark", "after rain")
    assert card.neighbours == neighbours
    assert card.prompt_version == PROMPT_VERSION == "e1"
    assert card.rulebook_version == "rb1"
    assert card.hard_rule_version == HARD_RULE_VERSION == "hr1"
    assert card.model_id == "model-x"
    assert card.created_at == NOW
    assert card.card_id == "c-1:model-x"


def test_a_safety_card_is_priority_one_and_quotes_the_safety_span(rulebook: Rulebook) -> None:
    narrative = "The unit started to smoke, then caught fire."
    complaint = make_complaint(narrative=narrative)
    extraction = make_extraction(safety_relevant=True, safety_quote="caught fire")
    card = build(
        rulebook,
        complaint=complaint,
        extraction=extraction,
        keywords=("smoke",),
    )
    assert card.priority is Priority.SAFETY
    assert card.needs_human_review is True
    assert card.quotes[0] == "caught fire"
    assert "smoke" in card.quotes
    assert any(reason.text.startswith("safety wins") for reason in card.reasons)


def test_an_unclear_card_says_why_it_needs_human_reading(rulebook: Rulebook) -> None:
    extraction = make_extraction(component_group=UNCLEAR_GROUP)
    card = build(rulebook, extraction=extraction)
    assert card.priority is Priority.HUMAN_READING
    assert card.needs_human_review is True
    assert any("component group is unclear" in reason.text for reason in card.reasons)


def test_a_dropped_clue_is_not_quoted_on_the_card(rulebook: Rulebook) -> None:
    check = make_quote_check(
        checked=2,
        passed=1,
        dropped=(DroppedClue(field="conditions", kind="moisture", quote="after rain"),),
    )
    card = build(rulebook, quote_check=check)
    assert card.quotes == ("went dark",)
    assert [clue.quote for clue in card.extraction.conditions] == []


def test_a_mileage_only_card_needs_human_reading(rulebook: Rulebook) -> None:
    extraction = make_extraction(
        symptoms=(),
        conditions=(),
        mileage=make_mileage(),
    )
    check = make_quote_check(checked=1, passed=1)
    card = build(rulebook, extraction=extraction, quote_check=check)
    assert card.priority is Priority.HUMAN_READING
    assert card.needs_human_review is True
    assert card.quotes == ("54,000 miles",)
    assert any("no clue passed the quote check" in reason.text for reason in card.reasons)


def test_a_dropped_safety_quote_is_not_repeated_in_the_reasons(rulebook: Rulebook) -> None:
    extraction = make_extraction(safety_relevant=True, safety_quote="caught fire")
    check = make_quote_check(
        checked=3,
        passed=2,
        dropped=(DroppedClue(field="safety", kind="safety", quote="caught fire"),),
    )
    card = build(rulebook, extraction=extraction, quote_check=check)
    safety_reason = card.reasons[0]
    assert "failed the quote check" in safety_reason.text
    assert "caught fire" not in safety_reason.text
    assert safety_reason.quotes == ()


def test_a_dropped_safety_quote_does_not_demote_a_safety_card(rulebook: Rulebook) -> None:
    extraction = make_extraction(safety_relevant=True, safety_quote="caught fire")
    check = make_quote_check(
        checked=3,
        passed=2,
        dropped=(DroppedClue(field="safety", kind="safety", quote="caught fire"),),
    )
    card = build(rulebook, extraction=extraction, quote_check=check)
    assert card.priority is Priority.SAFETY
    assert "caught fire" not in card.quotes


def test_fault_code_and_mileage_quotes_are_included(rulebook: Rulebook) -> None:
    extraction = make_extraction(
        fault_codes=(make_fault_code(),),
        mileage=make_mileage(),
    )
    card = build(rulebook, extraction=extraction)
    assert "code P0562" in card.quotes
    assert "54,000 miles" in card.quotes


def test_card_building_is_deterministic(rulebook: Rulebook) -> None:
    first = build(rulebook)
    second = build(rulebook)
    assert first == second


def test_neighbours_default_to_empty_and_are_passed_through(rulebook: Rulebook) -> None:
    assert build(rulebook).neighbours == ()


def test_card_reasons_are_reason_objects_with_quotes(rulebook: Rulebook) -> None:
    card = build(rulebook)
    assert all(isinstance(reason, Reason) for reason in card.reasons)
    assert any(reason.quotes for reason in card.reasons)
