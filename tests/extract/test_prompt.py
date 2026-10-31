"""Prompt e1: the groups, the vocabularies and the verbatim-quote rule."""

from __future__ import annotations

from datetime import date

from field_return_triage.contracts import Complaint, ConditionKind, SymptomKind
from field_return_triage.extract.prompt import PROMPT_VERSION, build_messages

COMPLAINT = Complaint(
    id="c-1",
    narrative="The dashboard went dark intermittently after rain.",
    received=date(2026, 1, 15),
)


def test_prompt_version_matches_the_contract() -> None:
    assert PROMPT_VERSION == "e1"


def test_messages_are_a_system_brief_and_the_narrative() -> None:
    messages = build_messages(
        COMPLAINT,
        {"b_group": "Brakes and stability", "a_group": "First\nthing"},
    )
    assert [message["role"] for message in messages] == ["system", "user"]
    assert COMPLAINT.narrative in messages[1]["content"]


def test_groups_are_sorted_with_one_line_descriptions() -> None:
    system = build_messages(
        COMPLAINT,
        {"b_group": "Brakes and stability", "a_group": "First\nthing"},
    )[0]["content"]
    assert "- a_group: First thing" in system
    assert "- b_group: Brakes and stability" in system
    assert system.index("- a_group") < system.index("- b_group")
    assert "- unclear:" in system


def test_every_kind_and_the_quote_rule_are_named() -> None:
    system = build_messages(COMPLAINT, {})[0]["content"]
    for kind in SymptomKind:
        assert kind.value in system
    for kind in ConditionKind:
        assert kind.value in system
    assert "Quote the exact words" in system
    assert "never paraphrase" in system
    assert "Do not add keys" in system
    assert "safety_quote must be null" in system
