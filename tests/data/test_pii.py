"""The PII screen: every normative pattern from the spec, and the committed copy."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from field_return_triage.data.pii import PII_PATTERN_NAMES, pii_matches, pii_reason
from field_return_triage.data.spec import PII_PATTERNS


@pytest.mark.parametrize(
    ("narrative", "expected"),
    [
        (
            "NHTSA already redacts some text, but the VIN 1HGCM82633A004352 is still here.",
            "vin17",
        ),
        ("Reach me at owner.name+triage@example.co.uk about the claim.", "email"),
        ("Call 555-123-4567 or (555) 123-4567 before noon.", "phone_us"),
        ("It failed at 123 Main STREET while parked uphill.", "street"),
        ("It failed at 45 North Oak AVENUE on the way home.", "street"),
        ("The dashboard went dark after rain and the dealer could not reproduce it.", None),
    ],
)
def test_each_pattern_drops_its_narrative(narrative: str, expected: str | None) -> None:
    assert pii_reason(narrative) == expected


def test_overlapping_patterns_are_all_reported() -> None:
    narrative = "Mail 1HGCM82633A004352@example.com or call 555-123-4567."
    matches = pii_matches(narrative)
    assert matches == ("vin17", "email", "phone_us")
    assert pii_reason(narrative) == "vin17"


def test_a_dropped_narrative_is_never_redacted_in_place() -> None:
    narrative = "My email is owner@example.com and that is the whole report."
    assert pii_reason(narrative) == "email"
    assert "owner@example.com" in narrative


def test_pattern_constants_match_the_committed_spec(repo_root: Path) -> None:
    spec = tomllib.loads((repo_root / "data" / "nhtsa-spec.toml").read_text(encoding="utf-8"))
    assert dict(PII_PATTERNS) == spec["pii"]["patterns"]
    assert PII_PATTERN_NAMES == tuple(spec["pii"]["patterns"])
