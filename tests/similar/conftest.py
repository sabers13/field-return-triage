"""Similar-lane fixtures: an isolated cache directory and a fake embedder."""

from __future__ import annotations

from pathlib import Path

import pytest
from support import FakeEmbedder


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Never write the real ``~/.cache/field-return-triage`` during tests."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))


@pytest.fixture
def checksums(tmp_path: Path) -> Path:
    """A small stand-in for ``data/CHECKSUMS.txt``."""
    path = tmp_path / "CHECKSUMS.txt"
    path.write_text("library.jsonl.gz  3f2a\n", encoding="utf-8")
    return path


@pytest.fixture
def embedder() -> FakeEmbedder:
    """A fresh fake embedder for each test."""
    return FakeEmbedder()
