"""Rules-lane fixtures: the real rulebook under the repository root."""

from __future__ import annotations

from pathlib import Path

import pytest

from field_return_triage.rules.rulebook import Rulebook, load_rulebook


@pytest.fixture(scope="session")
def rulebook(repo_root: Path) -> Rulebook:
    """The committed rulebook, loaded exactly as the product loads it."""
    return load_rulebook(repo_root / "config" / "rulebook.toml")
