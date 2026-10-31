"""Shared pytest setup and the test-suite network guard.

Adapted from which-ai-model (same author, MIT). Every test runs with the network
blocked. The block is switched on by the pytest options in ``pyproject.toml``
(``--disable-socket --allow-unix-socket``); pytest-socket re-arms it before every test,
unlike a one-off call at import time. Unix sockets stay allowed so local IPC and
subprocess pipes still work.

``pytest_configure`` is the second lock on the same door: if someone runs pytest
without the project options, the suite refuses to start rather than run online.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def pytest_configure(config: pytest.Config) -> None:
    """Refuse a test run whose socket block is not armed."""
    try:
        blocked = bool(config.getoption("disable_socket"))
    except ValueError:  # pytest-socket is not installed
        blocked = False
    if not blocked:
        pytest.exit(
            "tests must run with --disable-socket (use `make test` or `uv run pytest`)",
            returncode=2,
        )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The repository root (the worktree this test session runs in)."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Directory for committed test fixtures."""
    return REPO_ROOT / "tests" / "fixtures"
