"""Fixtures for the extraction tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from extract_support import REPO_ROOT


@pytest.fixture
def budget_path(tmp_path: Path) -> Path:
    path = tmp_path / "budget.toml"
    path.write_text(
        "hard_cap_usd = 3.0\n"
        "max_concurrency = 2\n"
        "requests_per_minute = 30\n"
        "max_attempts = 3\n"
        "backoff_seconds = 0.0\n"
        "request_timeout_seconds = 5.0\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def prices_path() -> Path:
    return REPO_ROOT / "config" / "prices.toml"
