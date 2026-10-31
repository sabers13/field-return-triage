"""The committed rulebook is the example from PLAN.md section 4, and the loader guards it."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

import pytest

from field_return_triage.rules.rulebook import (
    RULEBOOK_PATH,
    RULEBOOK_VERSION,
    Rule,
    Rulebook,
    load_rulebook,
)

#: The seven mappings fixed by ``PLAN.md`` section 4, with the exact wording there.
PLAN_TABLE: dict[str, tuple[str, tuple[str, ...]]] = {
    "moisture": ("humidity / condensation test", ("connectors and seals",)),
    "cold": ("low-temperature operation and temperature cycling", ()),
    "heat": ("high-temperature operation", ()),
    "vibration_or_road": ("vibration test", ("solder joints and connectors",)),
    "intermittent": ("long-run / power-cycling test with monitoring", ()),
    "after_service": ("check installation, connectors and wiring routing first", ()),
    "charging": ("electrical load and charging-profile test", ()),
}

FALLBACK_REQUEST = ("when it happens", "how often", "under which conditions", "fault codes")


def test_committed_rulebook_has_the_frozen_version(rulebook: Rulebook) -> None:
    assert rulebook.version == RULEBOOK_VERSION == "rb1"


@pytest.mark.parametrize(("kind", "expected"), sorted(PLAN_TABLE.items()))
def test_plan_table_is_mapped_exactly(
    rulebook: Rulebook, kind: str, expected: tuple[str, tuple[str, ...]]
) -> None:
    test, inspect = expected
    rule = rulebook.by_kind[kind]
    assert rule.tests == (test,)
    assert rule.inspect == inspect


def test_standard_test_fallback_matches_the_plan(rulebook: Rulebook) -> None:
    assert rulebook.fallback_test == "standard test"
    assert rulebook.fallback_inspect == ()
    assert rulebook.fallback_request == FALLBACK_REQUEST


def test_every_rule_suggests_at_least_one_test(rulebook: Rulebook) -> None:
    assert rulebook.by_kind
    for kind, rule in rulebook.by_kind.items():
        assert rule.tests, kind
        assert all(test.strip() for test in rule.tests), kind


def test_rulebook_is_immutable(rulebook: Rulebook) -> None:
    assert isinstance(rulebook.by_kind, MappingProxyType)
    with pytest.raises(TypeError):
        rulebook.by_kind["moisture"] = Rule(tests=("changed",))  # type: ignore[index]
    with pytest.raises(AttributeError):
        rulebook.version = "other"  # type: ignore[misc]


def test_default_path_is_the_committed_config() -> None:
    assert Path("config/rulebook.toml") == RULEBOOK_PATH


def write_rulebook(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "rulebook.toml"
    path.write_text(body, encoding="utf-8")
    return path


MINIMAL = """
version = "rb1"
[fallback]
test = "standard test"
request = []
[kinds.moisture]
tests = ["humidity / condensation test"]
"""


def test_minimal_rulebook_loads(tmp_path: Path) -> None:
    loaded = load_rulebook(write_rulebook(tmp_path, MINIMAL))
    assert loaded.fallback_request == ()
    assert loaded.by_kind["moisture"].inspect == ()


def test_wrong_version_is_rejected(tmp_path: Path) -> None:
    path = write_rulebook(tmp_path, MINIMAL.replace('version = "rb1"', 'version = "rb2"'))
    with pytest.raises(ValueError, match="version must be 'rb1'"):
        load_rulebook(path)


def test_unknown_kind_is_rejected(tmp_path: Path) -> None:
    body = MINIMAL.replace("[kinds.moisture]", "[kinds.moisturee]")
    with pytest.raises(ValueError, match="unknown kinds"):
        load_rulebook(write_rulebook(tmp_path, body))


def test_rule_without_a_test_is_rejected(tmp_path: Path) -> None:
    body = MINIMAL.replace('tests = ["humidity / condensation test"]', "tests = []")
    with pytest.raises(ValueError, match="at least one suggested test"):
        load_rulebook(write_rulebook(tmp_path, body))


def test_empty_string_in_a_list_is_rejected(tmp_path: Path) -> None:
    body = MINIMAL.replace("request = []", 'request = ["when it happens", " "]')
    with pytest.raises(ValueError, match="non-empty strings"):
        load_rulebook(write_rulebook(tmp_path, body))


def test_missing_fallback_test_is_rejected(tmp_path: Path) -> None:
    body = MINIMAL.replace('test = "standard test"', 'test = ""')
    with pytest.raises(ValueError, match=r"fallback\.test"):
        load_rulebook(write_rulebook(tmp_path, body))
