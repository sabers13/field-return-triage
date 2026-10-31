"""The contracts are the Wave 0 interface: prove the frozen shape behaves as documented."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from field_return_triage.contracts import (
    HARD_RULE_VERSION,
    PROMPT_VERSION,
    RULEBOOK_VERSION,
    SCHEMA_VERSION,
    UNCLEAR_GROUP,
    Clue,
    Complaint,
    ConditionKind,
    Decision,
    DecisionAction,
    DroppedClue,
    Extraction,
    FaultCode,
    Mileage,
    ModelSetting,
    Neighbour,
    Priority,
    QuoteCheck,
    Reason,
    Recall,
    RunManifest,
    RunMode,
    SeriesKey,
    Suggestion,
    SymptomKind,
    TrendAlert,
    TriageCard,
    WeeklyCount,
)

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
MONDAY = date(2026, 10, 26)
FAKE_HASH = "a" * 64


def make_complaint(**overrides: object) -> Complaint:
    values: dict[str, object] = {
        "id": "c-1",
        "narrative": "The dashboard went dark intermittently after rain.",
        "received": date(2026, 1, 15),
        "make": "Example",
        "model": "One",
        "model_year": 2021,
        "component": "ELECTRICAL SYSTEM",
        "group": "instrument_cluster",
    }
    values.update(overrides)
    return Complaint.model_validate(values)


def make_extraction(**overrides: object) -> Extraction:
    values: dict[str, object] = {
        "component_group": "instrument_cluster",
        "safety_relevant": False,
        "symptoms": (Clue(kind="display_fault", quote="went dark"),),
        "conditions": (Clue(kind="moisture", quote="after rain"),),
    }
    values.update(overrides)
    return Extraction.model_validate(values)


def make_quote_check(**overrides: object) -> QuoteCheck:
    values: dict[str, object] = {"checked": 2, "passed": 2, "dropped": ()}
    values.update(overrides)
    return QuoteCheck.model_validate(values)


def make_card(**overrides: object) -> TriageCard:
    values: dict[str, object] = {
        "card_id": "card-1",
        "complaint": make_complaint(),
        "extraction": make_extraction(),
        "quote_check": make_quote_check(),
        "priority": Priority.CLEAR_CLUES,
        "needs_human_review": False,
        "reasons": (Reason(text="moisture clue", quotes=("after rain",)),),
        "quotes": ("went dark", "after rain"),
        "suggestion": Suggestion(tests=("humidity / condensation test",)),
        "model_id": "fake-model",
        "created_at": NOW,
    }
    values.update(overrides)
    return TriageCard.model_validate(values)


def test_enum_vocabularies_are_exact() -> None:
    assert [kind.value for kind in SymptomKind] == [
        "no_function",
        "intermittent",
        "warning_light",
        "smoke_or_burn",
        "noise",
        "display_fault",
        "battery_drain",
        "other",
    ]
    assert [kind.value for kind in ConditionKind] == [
        "moisture",
        "cold",
        "heat",
        "vibration_or_road",
        "after_service",
        "charging",
        "speed_or_load",
        "startup",
        "other",
    ]
    assert {priority.name: int(priority) for priority in Priority} == {
        "SAFETY": 1,
        "CLEAR_CLUES": 2,
        "HUMAN_READING": 3,
    }
    assert [action.value for action in DecisionAction] == ["accept", "change"]
    assert [mode.value for mode in RunMode] == ["replay", "record"]


def test_frozen_versions_are_exact() -> None:
    assert SCHEMA_VERSION == "1.0.0"
    assert PROMPT_VERSION == "e1"
    assert RULEBOOK_VERSION == "rb1"
    assert HARD_RULE_VERSION == "hr1"
    assert UNCLEAR_GROUP == "unclear"


def test_complaint_is_frozen_and_closed_to_unknown_fields() -> None:
    complaint = make_complaint()
    with pytest.raises(ValidationError):
        complaint.narrative = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Complaint.model_validate({**complaint.model_dump(), "extra": 1})


def test_complaint_coded_safety_is_the_or_of_the_three_flags() -> None:
    assert make_complaint().coded_safety is False
    assert make_complaint(crash=True).coded_safety is True
    assert make_complaint(fire=True).coded_safety is True
    assert make_complaint(injury=True).coded_safety is True


def test_complaint_validates_dates_years_and_group_ids() -> None:
    with pytest.raises(ValidationError):
        make_complaint(model_year=1800)
    with pytest.raises(ValidationError):
        make_complaint(group="Not A Group")
    with pytest.raises(ValidationError):
        make_complaint(narrative="")


def test_clues_and_fault_codes_need_text() -> None:
    with pytest.raises(ValidationError):
        Clue(kind="", quote="x")
    with pytest.raises(ValidationError):
        Clue(kind="noise", quote="")
    with pytest.raises(ValidationError):
        FaultCode(code="P0", quote="")
    with pytest.raises(ValidationError):
        Mileage(value=-1, quote="minus one")


def test_extraction_defaults_are_unclear_and_clean() -> None:
    extraction = Extraction()
    assert extraction.component_group == UNCLEAR_GROUP
    assert extraction.safety_relevant is False
    assert extraction.safety_quote is None
    assert extraction.symptoms == ()
    assert extraction.conditions == ()
    assert extraction.fault_codes == ()
    assert extraction.mileage is None


def test_extraction_rejects_kinds_outside_the_fixed_vocabulary() -> None:
    with pytest.raises(ValidationError, match="symptom kind"):
        make_extraction(symptoms=(Clue(kind="ghost", quote="a"),))
    with pytest.raises(ValidationError, match="condition kind"):
        make_extraction(conditions=(Clue(kind="ghost", quote="a"),))


def test_safety_quote_must_accompany_the_flag_in_both_directions() -> None:
    flagged = make_extraction(safety_relevant=True, safety_quote="smoke")
    assert flagged.safety_quote == "smoke"
    with pytest.raises(ValidationError, match="requires the safety_quote"):
        make_extraction(safety_relevant=True)
    with pytest.raises(ValidationError, match="must be null"):
        make_extraction(safety_relevant=False, safety_quote="smoke")


def test_extraction_round_trips_through_json() -> None:
    extraction = make_extraction(
        safety_relevant=True,
        safety_quote="smoke",
        symptoms=(Clue(kind="smoke_or_burn", quote="smoke"),),
        fault_codes=(FaultCode(code="P0562", quote="P0562"),),
        mileage=Mileage(value=41000, quote="41,000 miles"),
    )
    assert Extraction.model_validate_json(extraction.model_dump_json()) == extraction


def test_quote_check_counts_must_add_up() -> None:
    with pytest.raises(ValidationError, match="checked must equal"):
        make_quote_check(checked=2, passed=1, dropped=())


def test_quote_check_flags_all_passed_and_none_passed() -> None:
    assert make_quote_check().all_passed is True
    assert make_quote_check().none_passed is False
    dropped = (DroppedClue(field="conditions", kind="moisture", quote="paraphrased"),)
    failed = make_quote_check(checked=1, passed=0, dropped=dropped)
    assert failed.all_passed is False
    assert failed.none_passed is True
    empty = make_quote_check(checked=0, passed=0)
    assert empty.all_passed is False
    assert empty.none_passed is False


def test_neighbour_excerpt_is_at_most_200_characters() -> None:
    short = Neighbour(
        complaint_id="c-0",
        group="instrument_cluster",
        received=date(2025, 5, 1),
        safety_relevant=False,
        excerpt="x" * 200,
        score=0.9123,
    )
    assert len(short.excerpt) == 200
    with pytest.raises(ValidationError):
        Neighbour(
            complaint_id="c-0",
            group="instrument_cluster",
            received=date(2025, 5, 1),
            safety_relevant=False,
            excerpt="x" * 201,
            score=0.5,
        )
    with pytest.raises(ValidationError):
        Neighbour(
            complaint_id="c-0",
            group="instrument_cluster",
            received=date(2025, 5, 1),
            safety_relevant=False,
            excerpt="x",
            score=1.5,
        )


def test_suggestion_needs_at_least_one_test_and_can_carry_reasons() -> None:
    with pytest.raises(ValidationError):
        Suggestion(tests=())
    suggestion = Suggestion(
        tests=("vibration test",),
        inspect=("solder joints",),
        request=("when it happens",),
        reasons=(Reason(text="vibration clue", quotes=("on rough roads",)),),
    )
    assert suggestion.reasons[0].quotes == ("on rough roads",)


def test_card_carries_priority_versions_and_reasons() -> None:
    card = make_card()
    assert card.priority is Priority.CLEAR_CLUES
    assert card.prompt_version == "e1"
    assert card.rulebook_version == "rb1"
    assert card.hard_rule_version == "hr1"
    assert card.schema_version == "1.0.0"
    assert card.reasons[0].text == "moisture clue"


def test_card_timestamp_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_card(created_at=datetime(2026, 10, 31, 12, 0))  # noqa: DTZ001 - deliberately naive


def test_card_has_no_field_that_can_close_scrap_or_return_a_case() -> None:
    closure_words = {
        "close",
        "closed",
        "closes",
        "scrap",
        "scrapped",
        "return",
        "returned",
        "disposition",
        "outcome",
        "status",
        "state",
        "resolution",
        "resolved",
    }
    fields = set(TriageCard.model_fields)
    assert fields.isdisjoint(closure_words)
    assert set(DecisionAction) == {DecisionAction.ACCEPT, DecisionAction.CHANGE}


def test_decision_change_requires_a_reason() -> None:
    accepted = Decision(
        card_id="card-1",
        complaint_id="c-1",
        action=DecisionAction.ACCEPT,
        decided_at=NOW,
        time_to_decision_s=12.5,
    )
    assert accepted.reason is None
    with pytest.raises(ValidationError, match="requires the technician's reason"):
        Decision(
            card_id="card-1",
            complaint_id="c-1",
            action=DecisionAction.CHANGE,
            reason="   ",
            decided_at=NOW,
        )
    changed = Decision(
        card_id="card-1",
        complaint_id="c-1",
        action=DecisionAction.CHANGE,
        reason="corroded connector",
        decided_at=NOW,
    )
    assert changed.action is DecisionAction.CHANGE


def test_decision_timestamp_must_be_aware() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Decision(
            card_id="card-1",
            complaint_id="c-1",
            action=DecisionAction.ACCEPT,
            decided_at=datetime(2026, 10, 31, 12, 0),  # noqa: DTZ001 - deliberately naive
        )


def test_weekly_counts_and_alerts_start_on_monday() -> None:
    series = SeriesKey(make="Example", model="One", model_year=2021, group="charging")
    week = WeeklyCount(series=series, week=MONDAY, count=2)
    assert week.count == 2
    with pytest.raises(ValidationError, match="Monday"):
        WeeklyCount(series=series, week=date(2026, 10, 27), count=2)
    alert = TrendAlert(series=series, week=MONDAY, count=4, trailing_mean=1.5, threshold=3.2)
    assert alert.count == 4
    with pytest.raises(ValidationError):
        TrendAlert(series=series, week=MONDAY, count=2, trailing_mean=1.5, threshold=3.2)
    with pytest.raises(ValidationError):
        TrendAlert(series=series, week=MONDAY, count=4, trailing_mean=0.4, threshold=3.2)


def test_recall_maps_one_report_to_one_group() -> None:
    recall = Recall(
        recall_id="24V-001",
        make="Example",
        model="One",
        model_year=2021,
        group="charging",
        report_date=date(2026, 3, 1),
    )
    assert recall.group == "charging"


def test_model_setting_rejects_credentials_in_the_url() -> None:
    setting = ModelSetting(role="primary", model_id="fake-model")
    assert setting.base_url == "https://opencode.ai/inference/go/openai/v1"
    assert setting.temperature == 0.0
    with pytest.raises(ValidationError, match="must not carry credentials"):
        ModelSetting(
            role="primary",
            model_id="fake-model",
            base_url="https://user:pass@example.invalid/v1",
        )


def make_manifest(**overrides: object) -> RunManifest:
    values: dict[str, object] = {
        "run_id": "replay-demo",
        "mode": RunMode.REPLAY,
        "models": (ModelSetting(role="primary", model_id="fake-model"),),
        "sample_hash": FAKE_HASH,
        "item_count": 400,
        "started_at": NOW,
        "finished_at": NOW + timedelta(minutes=2),
        "cost_usd": 0.0,
    }
    values.update(overrides)
    return RunManifest.model_validate(values)


def test_run_manifest_records_settings_versions_and_sample_hash() -> None:
    manifest = make_manifest()
    assert manifest.prompt_version == "e1"
    assert manifest.rulebook_version == "rb1"
    assert manifest.hard_rule_version == "hr1"
    assert manifest.models[0].role == "primary"


def test_run_manifest_validates_hash_order_and_mode() -> None:
    with pytest.raises(ValidationError):
        make_manifest(sample_hash="not-a-hash")
    with pytest.raises(ValidationError, match="finished_at"):
        make_manifest(finished_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValidationError):
        make_manifest(mode="live")
