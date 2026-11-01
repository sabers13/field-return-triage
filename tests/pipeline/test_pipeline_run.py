"""The resumable runner, determinism, the budget guard and the STOP path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pipeline_support import (
    FakeClient,
    fake_clock,
    fixture_paths,
    valid_answer,
)

from field_return_triage.contracts import Complaint, ModelSetting, RunMode
from field_return_triage.data.io import write_eval
from field_return_triage.llm import policy
from field_return_triage.llm.errors import PolicyStopError, ReplayMissError
from field_return_triage.pipeline.run import (
    BudgetExceededError,
    calls_path,
    load_cards,
    run_eval,
)

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


def _replay_run(tmp_path: Path, *, limit: int | None = None) -> Path:
    paths = fixture_paths()
    out = tmp_path / "runs"
    run_eval(
        mode=RunMode.REPLAY,
        models_path=paths.models,
        run_id="fixture",
        items_path=paths.items,
        out_dir=out,
        library_path=paths.library,
        groups_path=paths.groups,
        recordings_path=paths.recordings,
        prices_path=paths.prices,
        checksums_path=paths.checksums,
        limit=limit,
    )
    return out / "fixture"


def _write_lock(directory: Path) -> Path:
    path = directory / "models.lock.toml"
    path.write_text(MODELS, encoding="utf-8")
    return path


def _write_prices(directory: Path) -> Path:
    path = directory / "prices.toml"
    path.write_text(PRICES, encoding="utf-8")
    return path


def _write_budget(directory: Path, cap: float = 3.0) -> Path:
    path = directory / "budget.toml"
    path.write_text(f"hard_cap_usd = {cap}\nmax_attempts = 1\n", encoding="utf-8")
    return path


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


def test_replay_run_writes_cards_manifest_and_metrics(tmp_path: Path) -> None:
    run = _replay_run(tmp_path)
    cards = load_cards(run / "cards.jsonl")
    assert len(cards) == 40
    assert {card.model_id for card in cards} == {"fixture-primary", "fixture-comparison"}
    metrics = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["fixture"] is True
    assert metrics["item_count"] == 20
    assert set(metrics["models"]) == {"fixture-primary", "fixture-comparison"}
    primary = metrics["models"]["fixture-primary"]
    assert primary["group"]["macro_f1"]["value"] is not None
    assert primary["latency_ms"]["p50"]["value"] is not None
    assert metrics["budget"]["note"] == "every model ran on every item"
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["item_count"] == 20
    assert manifest["mode"] == "replay"
    assert manifest["cost_usd"] > 0


def test_replay_is_byte_identical_twice(tmp_path: Path) -> None:
    first = _replay_run(tmp_path / "one")
    second = _replay_run(tmp_path / "two")
    for name in ("cards.jsonl", "metrics.json", "manifest.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_replay_resumes_without_duplicates(tmp_path: Path) -> None:
    run = _replay_run(tmp_path, limit=5)
    assert len(load_cards(run / "cards.jsonl")) == 10
    full = _replay_run(tmp_path)
    cards = load_cards(full / "cards.jsonl")
    assert len(cards) == 40
    assert len({card.card_id for card in cards}) == 40


def test_budget_guard_reduces_the_comparison_model(tmp_path: Path) -> None:
    paths = fixture_paths()
    items = tmp_path / "items.jsonl"
    _synthetic_items(items)
    lock = _write_lock(tmp_path)
    prices = _write_prices(tmp_path)
    budget = _write_budget(tmp_path)
    recordings = tmp_path / "recordings"
    created: list[FakeClient] = []

    def factory(settings: ModelSetting) -> FakeClient:
        client = FakeClient(settings, content=valid_answer(), cost_usd=0.0001)
        created.append(client)
        return client

    run_eval(
        mode=RunMode.RECORD,
        models_path=lock,
        run_id="budget",
        items_path=items,
        out_dir=tmp_path / "runs",
        budget_path=budget,
        library_path=paths.library,
        groups_path=paths.groups,
        recordings_path=recordings,
        prices_path=prices,
        index=([], None),  # type: ignore[arg-type]
        clock=fake_clock(0.5),
        client_factory=factory,  # type: ignore[arg-type]
    )

    cards = load_cards(tmp_path / "runs" / "budget" / "cards.jsonl")
    by_model = {
        model: sum(1 for card in cards if card.model_id == model)
        for model in ("fixture-primary", "fixture-comparison")
    }
    assert by_model == {"fixture-primary": 400, "fixture-comparison": 200}
    assert created[0].calls == 400
    assert created[1].calls == 200

    metrics = json.loads((tmp_path / "runs" / "budget" / "metrics.json").read_text())
    assert metrics["budget"]["models"][1]["reduced"] is True
    assert "budget cut" in metrics["budget"]["note"]
    assert metrics["models"]["fixture-comparison"]["latency_ms"]["p50"]["value"] == pytest.approx(
        500.0
    )
    calls = calls_path(recordings).read_text(encoding="utf-8").splitlines()
    assert len(calls) == 600


def test_budget_guard_stops_before_the_cap(tmp_path: Path) -> None:
    paths = fixture_paths()
    items = tmp_path / "items.jsonl"
    _synthetic_items(items, count=400)
    lock = _write_lock(tmp_path)
    prices = _write_prices(tmp_path)
    budget = _write_budget(tmp_path, cap=0.0001)
    created: list[FakeClient] = []

    def factory(settings: ModelSetting) -> FakeClient:
        client = FakeClient(settings, content=valid_answer())
        created.append(client)
        return client

    with pytest.raises(BudgetExceededError, match="budget guard"):
        run_eval(
            mode=RunMode.RECORD,
            models_path=lock,
            run_id="stop",
            items_path=items,
            out_dir=tmp_path / "runs",
            budget_path=budget,
            library_path=paths.library,
            groups_path=paths.groups,
            recordings_path=tmp_path / "recordings",
            prices_path=prices,
            index=([], None),  # type: ignore[arg-type]
            client_factory=factory,  # type: ignore[arg-type]
        )
    assert created == []
    manifest = json.loads((tmp_path / "runs" / "stop" / "manifest.json").read_text())
    assert manifest["incomplete"] is True
    assert manifest["finished_at"] is None


def test_policy_stop_keeps_partial_cards_and_writes_the_notice(tmp_path: Path) -> None:
    paths = fixture_paths()
    prices = _write_prices(tmp_path)
    budget = _write_budget(tmp_path)

    def factory(settings: ModelSetting) -> FakeClient:
        def on_call(number: int) -> None:
            if number == 3:
                policy.trigger("HTTP 403: test stop")
                raise PolicyStopError("gateway policy stop")

        return FakeClient(settings, content=valid_answer(), on_call=on_call)

    with pytest.raises(PolicyStopError):
        run_eval(
            mode=RunMode.RECORD,
            models_path=paths.models,
            run_id="stop-policy",
            items_path=paths.items,
            out_dir=tmp_path / "runs",
            budget_path=budget,
            library_path=paths.library,
            groups_path=paths.groups,
            recordings_path=tmp_path / "recordings",
            prices_path=prices,
            index=([], None),  # type: ignore[arg-type]
            client_factory=factory,  # type: ignore[arg-type]
        )

    assert Path(policy.STOP_PATH).is_file()  # type: ignore[arg-type]
    cards = load_cards(tmp_path / "runs" / "stop-policy" / "cards.jsonl")
    assert len(cards) == 2
    manifest = json.loads((tmp_path / "runs" / "stop-policy" / "manifest.json").read_text())
    assert manifest["incomplete"] is True
    assert len(calls_path(tmp_path / "recordings").read_text().splitlines()) == 2


def test_missing_recordings_raise_a_replay_miss(tmp_path: Path) -> None:
    paths = fixture_paths()
    empty = tmp_path / "recordings"
    empty.mkdir()
    with pytest.raises(ReplayMissError, match="no recording"):
        run_eval(
            mode=RunMode.REPLAY,
            models_path=paths.models,
            run_id="miss",
            items_path=paths.items,
            out_dir=tmp_path / "runs",
            library_path=paths.library,
            groups_path=paths.groups,
            recordings_path=empty,
            prices_path=paths.prices,
            index=([], None),  # type: ignore[arg-type]
        )
