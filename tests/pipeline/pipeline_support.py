"""Shared helpers for the pipeline tests."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from field_return_triage.contracts import Complaint, ModelSetting
from field_return_triage.llm.reply import ModelReply
from field_return_triage.pipeline.config import Paths, resolve_paths

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "recordings"
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXED_NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
RECEIVED = date(2025, 2, 14)


def fixture_paths(**overrides: object) -> Paths:
    """Resolve the committed fixture inputs through the normal resolver."""
    values: dict[str, object] = {
        "models": FIXTURE_DIR / "models.lock.toml",
        "items": FIXTURE_DIR / "items.jsonl",
        "library": FIXTURE_DIR / "library.jsonl.gz",
        "recordings": FIXTURE_DIR,
        "groups": REPO_ROOT / "data" / "groups.toml",
        "prices": REPO_ROOT / "config" / "prices.toml",
        "checksums": REPO_ROOT / "data" / "CHECKSUMS.txt",
    }
    values.update(overrides)
    return resolve_paths(**values)  # type: ignore[arg-type]


def fixture_items() -> list[Complaint]:
    from field_return_triage.data.io import load_eval

    return load_eval(FIXTURE_DIR / "items.jsonl")


def fixture_library() -> list[Complaint]:
    from field_return_triage.data.io import load_library

    return load_library(FIXTURE_DIR / "library.jsonl.gz")


def fake_clock(step: float = 0.25) -> Callable[[], float]:
    """A monotonic fake clock: every call advances by ``step`` seconds."""
    state = {"now": 0.0}

    def clock() -> float:
        value = state["now"]
        state["now"] += step
        return value

    return clock


def make_complaint(**overrides: object) -> Complaint:
    values: dict[str, object] = {
        "id": "c-1",
        "narrative": "The dashboard went dark after rain and the wipers stopped.",
        "received": RECEIVED,
        "make": "Example",
        "model": "One",
        "model_year": 2021,
        "component": "ELECTRICAL SYSTEM",
        "group": "instrument_panel_displays",
    }
    values.update(overrides)
    return Complaint.model_validate(values)


def setting(role: str, model_id: str) -> ModelSetting:
    return ModelSetting(role=role, model_id=model_id, provider="fixture")


class FakeClient:
    """A ChatClient stand-in: deterministic content, cost and latency, no network."""

    def __init__(
        self,
        settings: ModelSetting,
        *,
        content: str | Callable[[], str] = "{}",
        cost_usd: float | None = 0.0001,
        input_tokens: int | None = 10,
        output_tokens: int | None = 20,
        on_call: Callable[[int], None] | None = None,
    ) -> None:
        self.settings = settings
        self._content = content
        self.cost_usd = cost_usd
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self._on_call = on_call
        self.calls = 0
        self.messages: list[Sequence[Mapping[str, str]]] = []

    def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        schema: object | None = None,
    ) -> ModelReply:
        self.calls += 1
        self.messages.append(messages)
        if self._on_call is not None:
            self._on_call(self.calls)
        content = self._content() if callable(self._content) else self._content
        return ModelReply(
            content=content,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cost_usd=self.cost_usd,
            model_id=self.settings.model_id,
            prompt_version="e1",
        )

    def close(self) -> None:
        return None


def valid_answer(group: str = "instrument_panel_displays") -> str:
    return json.dumps(
        {
            "component_group": group,
            "safety_relevant": False,
            "safety_quote": None,
            "symptoms": [{"kind": "display_fault", "quote": "went dark"}],
            "conditions": [{"kind": "moisture", "quote": "after rain"}],
            "fault_codes": [],
            "mileage": None,
        }
    )


def run_setting() -> ModelSetting:
    return ModelSetting(
        role="primary",
        model_id="fake-model",
        provider="fixture",
    )


def write_item_rows(path: Path, rows: Sequence[Complaint]) -> None:
    path.write_text(
        "\n".join(json.dumps(row.model_dump(mode="json"), sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )


def identity_index(items: Sequence[Complaint]) -> tuple[list[str], NDArray[np.float32]]:
    """A 4-dimensional index that makes every item its own nearest neighbour."""
    vectors = np.zeros((len(items), 4), dtype=np.float32)
    for position in range(len(items)):
        vectors[position, position % 4] = 1.0
    return [item.id for item in items], vectors
