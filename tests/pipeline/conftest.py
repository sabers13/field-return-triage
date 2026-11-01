"""Pipeline-lane fixtures: an isolated policy latch and the committed rulebook."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from field_return_triage.llm import policy
from field_return_triage.rules.rulebook import Rulebook, load_rulebook


@pytest.fixture(autouse=True)
def isolated_policy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """A STOP test writes into its own directory, and the latch never leaks."""
    policy.reset()
    monkeypatch.setattr(policy, "STOP_PATH", tmp_path / "reports" / "STOP.md")
    yield
    policy.reset()


@pytest.fixture(scope="session")
def rulebook(repo_root: Path) -> Rulebook:
    return load_rulebook(repo_root / "config" / "rulebook.toml")
