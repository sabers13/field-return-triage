"""Shared fixtures for the model-client tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from llm_support import API_KEY

from field_return_triage.contracts import ModelSetting
from field_return_triage.llm import policy

REPO_ROOT = Path(__file__).resolve().parents[2]

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def isolated_policy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Never write the real reports/STOP.md, and never leak a latch between tests."""
    policy.reset()
    monkeypatch.setattr(policy, "STOP_PATH", tmp_path / "reports" / "STOP.md")
    yield
    policy.reset()


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


@pytest.fixture
def settings() -> ModelSetting:
    return ModelSetting(role="primary", model_id="deepseek-v4.1-flash")


@pytest.fixture
def api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("FRT_API_KEY", API_KEY)
    monkeypatch.delenv("FRT_ENV_FILE", raising=False)
    monkeypatch.delenv("OPENCODE_GO_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    return API_KEY
