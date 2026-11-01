"""The copied normative files stay byte for byte what scout X0 produced."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from field_return_triage.data.spec import (
    PII_PATTERNS,
    SPLIT_KEY_PREFIX,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    load_spec,
)

#: sha256 of the two files in the X0 snapshot ``2026-10-31``; the copy must not drift.
SPEC_SHA256 = "e1aff0a13d5a8098f0d5437328935c62677d551a8d9d2d5f64a60517630509aa"
GROUPS_SHA256 = "3f32dedd47f7ee8fcd990384161eb4e46638a0b10737f440695f575b0c5c045a"


def test_spec_and_groups_are_the_pinned_copies(repo_root: Path) -> None:
    spec = repo_root / "data" / "nhtsa-spec.toml"
    groups = repo_root / "data" / "groups.toml"
    assert hashlib.sha256(spec.read_bytes()).hexdigest() == SPEC_SHA256
    assert hashlib.sha256(groups.read_bytes()).hexdigest() == GROUPS_SHA256


def test_snapshot_constants_match_the_spec(repo_root: Path) -> None:
    spec = load_spec(repo_root / "data" / "nhtsa-spec.toml")
    split = spec["split"]
    assert split["train_start"] == TRAIN_START.isoformat()
    assert split["train_end"] == TRAIN_END.isoformat()
    assert split["test_start"] == TEST_START.isoformat()
    assert split["halving_key_prefix"] == SPLIT_KEY_PREFIX
    assert spec["sampling"]["frt"]["min_per_group"] == 20
    assert spec["sampling"]["frt"]["min_safety"] == 80
    assert spec["sampling"]["frt"]["n"] == 400
    assert spec["sampling"]["train"]["max_items"] == 20_000


def test_the_pii_patterns_are_the_four_normative_ones(repo_root: Path) -> None:
    spec = load_spec(repo_root / "data" / "nhtsa-spec.toml")
    assert dict(PII_PATTERNS) == spec["pii"]["patterns"]
    assert len(PII_PATTERNS) == 4


def test_a_file_with_the_wrong_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "spec.toml"
    path.write_text('schema = "something-else"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="not a nhtsa-odi-snapshot-spec"):
        load_spec(path)
