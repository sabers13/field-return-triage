"""Budget and model-setting loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from field_return_triage.llm.errors import ConfigurationError
from field_return_triage.llm.settings import Budget, load_budget, load_model_settings


def test_budget_defaults_and_file(tmp_path: Path) -> None:
    assert Budget().max_concurrency == 2
    assert Budget().requests_per_minute == 30

    path = tmp_path / "budget.toml"
    path.write_text(
        "hard_cap_usd = 3.0\nmax_concurrency = 2\nrequests_per_minute = 30\n",
        encoding="utf-8",
    )
    budget = load_budget(path)
    assert budget.hard_cap_usd == 3.0
    assert budget.max_attempts == 4


def test_budget_rejects_nonsense(tmp_path: Path) -> None:
    path = tmp_path / "budget.toml"
    path.write_text("max_concurrency = 0\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_budget(path)


def test_missing_budget_file_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        load_budget(tmp_path / "absent.toml")


def test_model_settings_are_validated(tmp_path: Path) -> None:
    path = tmp_path / "models.lock.toml"
    path.write_text(
        """
[[models]]
role = "primary"
model_id = "deepseek-v4.1-flash"

[[models]]
role = "comparison"
model_id = "glm-5.3"
max_output_tokens = 2048
""",
        encoding="utf-8",
    )
    settings = load_model_settings(path)
    assert [entry.role for entry in settings] == ["primary", "comparison"]
    assert settings[0].base_url == "https://opencode.ai/inference/go/openai/v1"
    assert settings[1].max_output_tokens == 2048


def test_empty_model_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "models.lock.toml"
    path.write_text("models = []\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_model_settings(path)
