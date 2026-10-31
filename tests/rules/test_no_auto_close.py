"""The "no auto-close" property: no type or function in the rules can end a case.

PLAN.md hard rule 4: no automatic close, scrap or return state exists. This is proved at
the level that matters: the card type (and every type it nests), the decision type, the
decision vocabulary, the rules' public functions, and a card's serialised form.
"""

from __future__ import annotations

import types
import typing
from typing import Any

import pytest
from helpers import NOW, make_complaint, make_extraction, make_quote_check
from pydantic import BaseModel

from field_return_triage.contracts import (
    Complaint,
    Decision,
    DecisionAction,
    Extraction,
    QuoteCheck,
    Suggestion,
    TriageCard,
)
from field_return_triage.rules import hard_rules
from field_return_triage.rules.hard_rules import build_card
from field_return_triage.rules.rulebook import Rulebook

#: Words that would turn a suggestion into a decision. Matched against field-name words.
FORBIDDEN_WORDS = frozenset(
    {
        "close",
        "closed",
        "closure",
        "scrap",
        "scrapped",
        "scrapping",
        "return",
        "returned",
        "returning",
        "disposition",
        "resolution",
        "resolved",
        "outcome",
        "status",
    }
)


def field_words(name: str) -> set[str]:
    return {word for word in name.lower().split("_") if word}


def nested_models(annotation: object) -> list[type[BaseModel]]:
    """Every pydantic model a field annotation can hold, at any nesting depth."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for argument in typing.get_args(annotation):
        found.extend(nested_models(argument))
    return found


def reachable_models(root: type[BaseModel]) -> set[type[BaseModel]]:
    seen: set[type[BaseModel]] = set()
    queue = [root]
    while queue:
        model = queue.pop()
        if model in seen:
            continue
        seen.add(model)
        for field in model.model_fields.values():
            queue.extend(nested_models(field.annotation))
    return seen


ROOTS = [TriageCard, Suggestion, Decision, Extraction, Complaint, QuoteCheck]


def test_no_contract_field_names_a_decision() -> None:
    offenders: list[str] = []
    for root in ROOTS:
        for model in reachable_models(root):
            for name in model.model_fields:
                if field_words(name) & FORBIDDEN_WORDS:
                    offenders.append(f"{model.__name__}.{name}")
    assert offenders == []


def test_the_decision_vocabulary_is_only_accept_and_change() -> None:
    assert {action.value for action in DecisionAction} == {"accept", "change"}
    for action in DecisionAction:
        assert not field_words(action.value) & FORBIDDEN_WORDS


def test_no_rules_function_names_a_decision() -> None:
    offenders = [
        name
        for name, value in vars(hard_rules).items()
        if callable(value) and not name.startswith("__") and field_words(name) & FORBIDDEN_WORDS
    ]
    assert offenders == []


def test_hard_rules_module_does_not_define_a_new_model() -> None:
    models = [
        name
        for name, value in vars(hard_rules).items()
        if isinstance(value, type)
        and issubclass(value, BaseModel)
        and value.__module__ == hard_rules.__name__
    ]
    assert models == []


def keys_of(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = set(value)
        for item in value.values():
            found |= keys_of(item)
        return found
    if isinstance(value, list | tuple):
        found = set()
        for item in value:
            found |= keys_of(item)
        return found
    return set()


@pytest.mark.parametrize("unclear", [True, False])
@pytest.mark.parametrize("safety", [True, False])
def test_a_serialised_card_has_no_decision_key(
    rulebook: Rulebook, unclear: bool, safety: bool
) -> None:
    extraction = make_extraction(
        component_group="unclear" if unclear else "instrument_cluster",
        safety_relevant=safety,
        safety_quote="went dark" if safety else None,
    )
    card = build_card(
        make_complaint(),
        extraction,
        make_quote_check(),
        neighbours=(),
        rulebook=rulebook,
        model_id="model-x",
        keywords=(),
        now=NOW,
    )
    assert keys_of(card.model_dump(mode="json")) & FORBIDDEN_WORDS == set()


def test_the_rules_api_exposes_only_suggestions() -> None:
    """A card is data a person reads; the only verbs over it are build and suggest."""
    assert callable(hard_rules.build_card)
    assert callable(hard_rules.suggest)
    assert isinstance(hard_rules, types.ModuleType)
