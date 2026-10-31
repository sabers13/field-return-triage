"""Load model settings and the pacing/budget configuration from TOML.

``config/models.lock.toml`` is written by lane R7; this module only parses it through
the frozen :class:`~field_return_triage.contracts.ModelSetting` contract. The budget
and pacing numbers come from ``config/budget.toml`` (PLAN §8: 2 concurrent requests,
30 requests/minute per model).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from field_return_triage.contracts import ModelSetting
from field_return_triage.llm.errors import ConfigurationError

__all__ = ["BUDGET_PATH", "MODELS_PATH", "Budget", "load_budget", "load_model_settings"]

MODELS_PATH: Path = Path("config/models.lock.toml")
BUDGET_PATH: Path = Path("config/budget.toml")


@dataclass(frozen=True, slots=True)
class Budget:
    """The run-level limits from ``config/budget.toml`` (PLAN §8)."""

    hard_cap_usd: float = 3.0
    max_concurrency: int = 2
    requests_per_minute: int = 30
    max_attempts: int = 4
    backoff_seconds: float = 0.5
    request_timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.hard_cap_usd <= 0:
            msg = "hard_cap_usd must be greater than zero"
            raise ConfigurationError(msg)
        if self.max_concurrency < 1:
            msg = "max_concurrency must be at least 1"
            raise ConfigurationError(msg)
        if self.requests_per_minute < 1:
            msg = "requests_per_minute must be at least 1"
            raise ConfigurationError(msg)
        if self.max_attempts < 1:
            msg = "max_attempts must be at least 1"
            raise ConfigurationError(msg)
        if self.backoff_seconds < 0:
            msg = "backoff_seconds must not be negative"
            raise ConfigurationError(msg)
        if self.request_timeout_seconds <= 0:
            msg = "request_timeout_seconds must be greater than zero"
            raise ConfigurationError(msg)


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        msg = f"configuration file not found: {path}"
        raise ConfigurationError(msg) from None
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = f"cannot read {path}: {exc.__class__.__name__}"
        raise ConfigurationError(msg) from None


def load_budget(path: Path = BUDGET_PATH) -> Budget:
    """Read the budget file; absent keys keep the documented defaults."""
    raw = _read_toml(path)

    def number(key: str, default: float) -> float:
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            msg = f"budget.{key} must be a number"
            raise ConfigurationError(msg)
        return float(value)

    def integer(key: str, default: int) -> int:
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            msg = f"budget.{key} must be an integer"
            raise ConfigurationError(msg)
        return value

    return Budget(
        hard_cap_usd=number("hard_cap_usd", 3.0),
        max_concurrency=integer("max_concurrency", 2),
        requests_per_minute=integer("requests_per_minute", 30),
        max_attempts=integer("max_attempts", 4),
        backoff_seconds=number("backoff_seconds", 0.5),
        request_timeout_seconds=number("request_timeout_seconds", 60.0),
    )


def load_model_settings(path: Path = MODELS_PATH) -> tuple[ModelSetting, ...]:
    """Read the locked models; the file is owned by lane R7.

    Accepts both a ``[[models]]`` table array and a top-level ``models`` array so the
    lock can record its provenance next to the entries.
    """
    raw = _read_toml(path)
    entries = raw.get("models", [])
    if not isinstance(entries, list) or not entries:
        msg = f"{path} must contain a non-empty [[models]] table array"
        raise ConfigurationError(msg)

    settings: list[ModelSetting] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            msg = f"models[{index}] must be a table"
            raise ConfigurationError(msg)
        try:
            settings.append(ModelSetting.model_validate(entry))
        except ValueError as exc:
            msg = f"models[{index}] is not a valid ModelSetting: {exc}"
            raise ConfigurationError(msg) from None
    return tuple(settings)
