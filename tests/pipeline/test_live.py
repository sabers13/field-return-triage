"""The R7 live entry points: the fixture refusal, the probe, and the cap's scope."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pipeline_support import FIXTURE_DIR, fake_clock, fixture_paths, valid_answer
from typer.testing import CliRunner

from field_return_triage.contracts import Complaint, ModelSetting, RunMode
from field_return_triage.data.io import write_eval
from field_return_triage.llm.reply import ModelReply
from field_return_triage.pipeline import cli
from field_return_triage.pipeline.cli import app
from field_return_triage.pipeline.run import BudgetExceededError, run_eval

runner = CliRunner()

LOCK = """\
[[models]]
role = "primary"
model_id = "muse-spark-1.3-contributor"
provider = "opencode-go"

[[models]]
role = "comparison"
model_id = "gemini-4-argon"
provider = "opencode-go"
"""

PRICES = """\
[models."fixture-primary"]
input = 0.10
output = 0.10

[models."fixture-comparison"]
input = 5.00
output = 5.00
"""

MODELS = """\
[[models]]
role = "primary"
model_id = "fixture-primary"
provider = "fixture"

[[models]]
role = "comparison"
model_id = "fixture-comparison"
provider = "fixture"
"""


class ProbeClient:
    """A ChatClient stand-in for the probe: one valid answer, no network."""

    def __init__(self, settings: ModelSetting, **_: object) -> None:
        self.settings = settings

    def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        schema: object | None = None,
    ) -> ModelReply:
        return ModelReply(
            content=valid_answer(),
            input_tokens=10,
            output_tokens=20,
            cost_usd=0.001,
            model_id=self.settings.model_id,
            prompt_version="e1",
        )

    def close(self) -> None:
        return None


class FakeClient:
    def __init__(self, settings: ModelSetting) -> None:
        self.settings = settings
        self.calls = 0

    def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        schema: object | None = None,
    ) -> ModelReply:
        self.calls += 1
        return ModelReply(
            content=valid_answer(),
            input_tokens=10,
            output_tokens=20,
            cost_usd=0.0001,
            model_id=self.settings.model_id,
            prompt_version="e1",
        )

    def close(self) -> None:
        return None


def _synthetic_items(path: Path, count: int = 400) -> None:
    items = [
        Complaint(
            id=f"syn-{index:03d}",
            narrative="The dashboard went dark after rain and the wipers stopped.",
            received="2025-06-01",
            make="Example",
            model="One",
            model_year=2021,
            component="ELECTRICAL SYSTEM:INSTRUMENT CLUSTER/PANEL",
            group="instrument_panel_displays",
        )
        for index in range(count)
    ]
    write_eval(items, path)


def test_live_refuses_fixture_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRT_MODELS", str(FIXTURE_DIR / "models.lock.toml"))
    result = runner.invoke(app, ["live"])
    assert result.exit_code == 1, result.output
    assert "fixture" in result.output


def test_probe_writes_one_outcome_per_locked_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / "models.lock.toml"
    lock.write_text(LOCK, encoding="utf-8")
    recordings = tmp_path / "recordings"
    monkeypatch.setenv("FRT_MODELS", str(lock))
    monkeypatch.setenv("FRT_RECORDINGS", str(recordings))
    monkeypatch.setattr(cli, "ChatClient", ProbeClient)

    result = runner.invoke(app, ["probe"])
    assert result.exit_code == 0, result.output

    payload = json.loads((recordings / "probes.json").read_text(encoding="utf-8"))
    assert [row["model_id"] for row in payload["models"]] == [
        "muse-spark-1.3-contributor",
        "gemini-4-argon",
    ]
    assert all(row["ok"] for row in payload["models"])
    assert payload["endpoint"].endswith("/chat/completions")

    calls = (recordings / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in calls]
    assert {row["run_id"] for row in rows} == {"probe"}
    assert {row["model_id"] for row in rows} == {"muse-spark-1.3-contributor", "gemini-4-argon"}


def test_the_cap_counts_paid_calls_from_other_run_ids(tmp_path: Path) -> None:
    """A probe or smoke call is paid, so the live guard must count it too."""
    paths = fixture_paths()
    items = tmp_path / "items.jsonl"
    _synthetic_items(items)
    lock = tmp_path / "models.lock.toml"
    lock.write_text(MODELS, encoding="utf-8")
    prices = tmp_path / "prices.toml"
    prices.write_text(PRICES, encoding="utf-8")
    budget = tmp_path / "budget.toml"
    budget.write_text("hard_cap_usd = 3.0\n", encoding="utf-8")
    recordings = tmp_path / "recordings"
    recordings.mkdir()
    earlier = {
        "run_id": "probe",
        "model_id": "fixture-comparison",
        "complaint_id": "__probe__",
        "cost_usd": 1.5,
    }
    (recordings / "calls.jsonl").write_text(json.dumps(earlier) + "\n", encoding="utf-8")

    with pytest.raises(BudgetExceededError, match="budget guard"):
        run_eval(
            mode=RunMode.RECORD,
            models_path=lock,
            run_id="live",
            items_path=items,
            out_dir=tmp_path / "runs",
            budget_path=budget,
            library_path=paths.library,
            groups_path=paths.groups,
            recordings_path=recordings,
            prices_path=prices,
            index=([], None),  # type: ignore[arg-type]
            clock=fake_clock(0.5),
            client_factory=FakeClient,  # type: ignore[arg-type]
        )
