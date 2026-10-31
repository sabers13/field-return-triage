"""Factories shared by the rules tests. Plain functions, imported explicitly."""

from __future__ import annotations

from datetime import UTC, date, datetime

from field_return_triage.contracts import (
    Clue,
    Complaint,
    Extraction,
    FaultCode,
    Mileage,
    Neighbour,
    QuoteCheck,
)

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
RECEIVED = date(2026, 1, 15)

DEFAULT_NARRATIVE = "The dashboard went dark intermittently after rain."


def make_complaint(**overrides: object) -> Complaint:
    values: dict[str, object] = {
        "id": "c-1",
        "narrative": DEFAULT_NARRATIVE,
        "received": RECEIVED,
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


def make_fault_code(code: str = "P0562", quote: str = "code P0562") -> FaultCode:
    return FaultCode(code=code, quote=quote)


def make_mileage(value: int = 54_000, quote: str = "54,000 miles") -> Mileage:
    return Mileage(value=value, quote=quote)


def make_neighbour(**overrides: object) -> Neighbour:
    values: dict[str, object] = {
        "complaint_id": "n-1",
        "group": "instrument_cluster",
        "received": RECEIVED,
        "safety_relevant": False,
        "excerpt": "The cluster flickered in the rain.",
        "score": 0.91,
    }
    values.update(overrides)
    return Neighbour.model_validate(values)
