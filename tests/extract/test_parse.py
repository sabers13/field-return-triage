"""Parse: valid answers become the contract; bad answers become a reason, once."""

from __future__ import annotations

import json

from field_return_triage.contracts import Extraction, SymptomKind
from field_return_triage.extract.parse import parse_extraction

VALID = {
    "component_group": "body_control",
    "safety_relevant": False,
    "safety_quote": None,
    "symptoms": [{"kind": "noise", "quote": "loud rattle"}],
    "conditions": [{"kind": "moisture", "quote": "after rain"}],
    "fault_codes": [{"code": "U0121", "quote": "U0121"}],
    "mileage": {"value": 42_000, "quote": "42,000 miles"},
}


def test_valid_json_becomes_the_frozen_contract() -> None:
    extraction, reason = parse_extraction(json.dumps(VALID))
    assert reason is None
    assert isinstance(extraction, Extraction)
    assert extraction.component_group == "body_control"
    assert extraction.symptoms[0].kind == SymptomKind.NOISE
    assert extraction.mileage is not None
    assert extraction.mileage.value == 42_000


def test_a_fenced_answer_is_accepted() -> None:
    extraction, reason = parse_extraction(f"```json\n{json.dumps(VALID)}\n```")
    assert reason is None
    assert extraction is not None


def test_empty_answers_are_schema_invalid_with_a_reason() -> None:
    for raw in ("", "   ", "```json\n```"):
        extraction, reason = parse_extraction(raw)
        assert extraction is None
        assert reason == "schema-invalid: empty answer"


def test_a_cut_off_answer_says_so() -> None:
    extraction, reason = parse_extraction('{"component_group": "body_control", "symptoms": [')
    assert extraction is None
    assert reason is not None
    assert reason.startswith("schema-invalid: cut-off answer")


def test_unparseable_text_says_so() -> None:
    extraction, reason = parse_extraction("I cannot help with that.")
    assert extraction is None
    assert reason is not None
    assert reason.startswith("schema-invalid: unparseable answer")


def test_non_object_json_is_schema_invalid() -> None:
    extraction, reason = parse_extraction("[]")
    assert extraction is None
    assert reason == "schema-invalid: answer is not a JSON object"


def test_unknown_kind_is_schema_invalid() -> None:
    answer = dict(VALID)
    answer["symptoms"] = [{"kind": "spooky", "quote": "loud rattle"}]
    extraction, reason = parse_extraction(json.dumps(answer))
    assert extraction is None
    assert reason is not None
    assert reason.startswith("schema-invalid: symptoms.0.kind")


def test_safety_without_a_quote_is_schema_invalid() -> None:
    answer = dict(VALID)
    answer["safety_relevant"] = True
    answer["safety_quote"] = None
    extraction, reason = parse_extraction(json.dumps(answer))
    assert extraction is None
    assert reason is not None
    assert reason.startswith("schema-invalid")
    assert "safety_quote" in reason
