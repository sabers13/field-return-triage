"""The evaluation runner and its budget guard (``PLAN.md`` sections 8 and 9).

``run_eval`` puts every evaluation item through :func:`pipeline.triage.triage_item` for
each locked model and writes one run directory:

* ``manifest.json`` - the frozen :class:`~field_return_triage.contracts.RunManifest`;
* ``cards.jsonl`` - one card per item per model, sorted deterministically;
* ``metrics.json`` - every ``PLAN.md`` section 6 metric with its interval, plus the
  budget report.

The run is resumable: a card already in ``cards.jsonl`` is not called again. Record mode
applies the USD cap from ``config/budget.toml`` before each model and before each call,
reduces the comparison model to 200 items first, and raises :class:`BudgetExceededError`
rather than crossing the cap. Replay mode never touches the network.

Per-call cost and duration live in ``<recordings>/calls.jsonl`` (written only in record
mode, and read back in replay), because the frozen card cannot carry them and a replay
must not use the wall clock.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from field_return_triage.contracts import (
    SCHEMA_VERSION,
    Complaint,
    ModelSetting,
    RunManifest,
    RunMode,
    TriageCard,
)
from field_return_triage.data.io import load_eval, load_library
from field_return_triage.llm.client import ChatClient
from field_return_triage.llm.cost import estimate_cost_usd
from field_return_triage.llm.errors import LlmError
from field_return_triage.llm.settings import BUDGET_PATH, load_budget, load_model_settings
from field_return_triage.pipeline import metrics as metric_module
from field_return_triage.pipeline.baseline import load_condition_keywords
from field_return_triage.pipeline.config import (
    Paths,
    empty_index,
    load_group_descriptions,
    resolve_index,
    resolve_paths,
)
from field_return_triage.pipeline.triage import CallStats, triage_item
from field_return_triage.rules.keywords import load_safety_keywords
from field_return_triage.rules.rulebook import load_rulebook

__all__ = [
    "CALLS_FILE",
    "COMPARISON_REDUCED_ITEMS",
    "REPLAY_NOW",
    "BudgetExceededError",
    "calls_path",
    "load_cards",
    "run_eval",
]

#: The fixed clock replay uses, so two `make all` runs are byte-identical. It is the
#: committed data snapshot date, and every replay card and manifest carries it.
REPLAY_NOW: Final = datetime(2026, 10, 31, 0, 0, tzinfo=UTC)

#: PLAN.md section 8: the comparison model is cut to this many items before anything else.
COMPARISON_REDUCED_ITEMS: Final = 200

#: Per-call cost and duration sidecar inside the recordings directory.
CALLS_FILE: Final = "calls.jsonl"

#: The PLAN section 8 plan for one run: how many items each model was scheduled to run.
SCHEDULE_FILE: Final = "schedule.json"


class BudgetExceededError(RuntimeError):
    """The conservative estimate would cross the cap, so no call was made."""


def calls_path(recordings: Path) -> Path:
    """Where per-call cost and duration live for one recordings directory."""
    return recordings / CALLS_FILE


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_cards(path: Path) -> list[TriageCard]:
    """Read ``cards.jsonl``; a missing file is an empty run."""
    if not path.is_file():
        return []
    cards: list[TriageCard] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cards.append(TriageCard.model_validate(json.loads(line)))
        except ValueError as exc:
            msg = f"{path}:{number}: not a triage card: {exc}"
            raise ValueError(msg) from None
    return cards


def _append_card(path: Path, card: TriageCard) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(card.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.write("\n")


def _append_call(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _call_row(
    settings: ModelSetting,
    complaint_id: str,
    stats: CallStats,
    *,
    run_id: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "model_id": settings.model_id,
        "complaint_id": complaint_id,
        "prompt_version": "e1",
        "input_tokens": stats.input_tokens,
        "output_tokens": stats.output_tokens,
        "cost_usd": stats.cost_usd,
        "duration_ms": round(stats.duration_ms, 3),
        "failure": stats.failure,
    }


def read_calls(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Read the calls sidecar, keyed by ``(model id, complaint id)``."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    if not path.is_file():
        return rows
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            key = (str(row["model_id"]), str(row["complaint_id"]))
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            msg = f"{path}:{number}: not a call row: {exc}"
            raise ValueError(msg) from None
        rows[key] = row
    return rows


def _calls_for_run(
    calls: Mapping[tuple[str, str], Mapping[str, Any]],
    run_id: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Rows from this run, plus untagged rows (the committed fixture recordings)."""
    return {key: dict(row) for key, row in calls.items() if row.get("run_id") in (None, run_id)}


def _sample_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sort_cards(
    cards: Sequence[TriageCard], items: Sequence[Complaint], models: Sequence[ModelSetting]
) -> list[TriageCard]:
    item_order = {item.id: position for position, item in enumerate(items)}
    model_order = {model.model_id: position for position, model in enumerate(models)}
    return sorted(
        cards,
        key=lambda card: (
            item_order.get(card.complaint.id, len(items)),
            model_order.get(card.model_id, len(models)),
            card.complaint.id,
        ),
    )


def _rewrite_cards(path: Path, cards: Sequence[TriageCard]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(card.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        for card in cards
    ]
    path.write_text(("\n".join(lines) + ("\n" if lines else "")), encoding="utf-8")


def _metric_dict(metric: metric_module.Metric) -> dict[str, Any]:
    return metric.model_dump()


def _condition_keywords(path: Path) -> dict[str, tuple[str, ...]]:
    return load_condition_keywords(path)


def _model_metrics(
    cards: Sequence[TriageCard],
    items: Sequence[Complaint],
    *,
    calls: Mapping[tuple[str, str], Mapping[str, Any]],
    condition_keywords: Mapping[str, tuple[str, ...]],
    settings: ModelSetting,
    prices_path: Path,
    estimate_items: int,
) -> dict[str, Any]:
    gold = [card.complaint.group or "unclear" for card in cards]
    predicted = [card.extraction.component_group for card in cards]
    rows = [
        calls[(card.model_id, card.complaint.id)]
        for card in cards
        if (card.model_id, card.complaint.id) in calls
    ]
    costs = [
        float(row["cost_usd"]) for row in rows if isinstance(row.get("cost_usd"), (int, float))
    ]
    durations = [
        float(row["duration_ms"])
        for row in rows
        if isinstance(row.get("duration_ms"), (int, float))
    ]
    try:
        estimated = estimate_cost_usd(settings, estimate_items, prices_path)
    except LlmError:
        estimated = None

    return {
        "model_id": settings.model_id,
        "role": settings.role,
        "items_evaluated": len(cards),
        "invalid_answers": sum(1 for row in rows if row.get("failure")),
        "group": {
            "macro_f1": _metric_dict(metric_module.macro_f1(gold, predicted)),
            "accuracy": _metric_dict(metric_module.accuracy(gold, predicted)),
            "coverage": _metric_dict(metric_module.coverage(predicted)),
            "answered_accuracy": _metric_dict(metric_module.answered_accuracy(gold, predicted)),
        },
        "safety": {
            name: _metric_dict(metric)
            for name, metric in metric_module.safety_scores(cards, items).items()
        },
        "quote_grounding": _metric_dict(metric_module.quote_grounding(cards)),
        "condition_agreement": _metric_dict(
            metric_module.condition_agreement(cards, condition_keywords)
        ),
        "similar_precision_at_5": _metric_dict(metric_module.similar_precision(cards)),
        "routing": {
            name: _metric_dict(metric) for name, metric in metric_module.routing(cards).items()
        },
        "cost": {
            name: _metric_dict(metric) for name, metric in metric_module.cost_metrics(costs).items()
        },
        "latency_ms": {
            name: _metric_dict(metric)
            for name, metric in metric_module.latency_ms(durations).items()
        },
        "estimated_cost_usd": estimated,
    }


def _budget_report(
    settings: Sequence[ModelSetting],
    cards: Sequence[TriageCard],
    *,
    items: int,
    cap: float,
    calls: Mapping[tuple[str, str], Mapping[str, Any]],
    prices_path: Path,
) -> dict[str, Any]:
    spent = sum(
        float(row["cost_usd"])
        for row in calls.values()
        if isinstance(row.get("cost_usd"), (int, float))
    )
    models: list[dict[str, Any]] = []
    for model in settings:
        ran = sum(1 for card in cards if card.model_id == model.model_id)
        try:
            estimated = estimate_cost_usd(model, ran, prices_path)
        except LlmError:
            estimated = None
        models.append(
            {
                "model_id": model.model_id,
                "role": model.role,
                "items_available": items,
                "items_run": ran,
                "reduced": ran < items,
                "estimated_cost_usd": estimated,
            }
        )
    return {
        "cap_usd": cap,
        "spent_usd": spent,
        "models": models,
        "note": (
            "a reduced model ran on fewer items after the PLAN section 8 budget cut"
            if any(entry["reduced"] for entry in models)
            else "every model ran on every item"
        ),
    }


@dataclass(frozen=True, slots=True)
class _RunState:
    run_dir: Path
    cards_file: Path
    manifest_file: Path
    metrics_file: Path
    schedule_file: Path


def _run_state(out_dir: Path, run_id: str) -> _RunState:
    run_dir = out_dir / run_id
    return _RunState(
        run_dir=run_dir,
        cards_file=run_dir / "cards.jsonl",
        manifest_file=run_dir / "manifest.json",
        metrics_file=run_dir / "metrics.json",
        schedule_file=run_dir / SCHEDULE_FILE,
    )


def _read_schedule(path: Path) -> dict[str, int]:
    """How many items each model was scheduled to run, or ``{}`` when unrecorded."""
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return {
        str(model): count
        for model, count in loaded.items()
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0
    }


def _write_schedule(path: Path, schedule: Mapping[str, int]) -> None:
    _write_json(path, dict(sorted(schedule.items())))


def run_eval(
    *,
    mode: RunMode,
    models_path: Path | None = None,
    run_id: str = "live",
    items_path: Path | None = None,
    out_dir: Path = Path("results/runs"),
    budget_path: Path = BUDGET_PATH,
    limit: int | None = None,
    library_path: Path | None = None,
    groups_path: Path | None = None,
    recordings_path: Path | None = None,
    prices_path: Path | None = None,
    checksums_path: Path | None = None,
    index: tuple[list[str], NDArray[np.float32]] | None = None,
    embedder: Any | None = None,
    clock: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], datetime] | None = None,
    client_factory: Callable[[ModelSetting], ChatClient] | None = None,
) -> RunManifest:
    """Run the evaluation set through the pipeline; return the run manifest.

    ``run_id`` names ``results/runs/<id>``. ``limit`` keeps the first N items (a smoke
    run). ``clock`` measures call latency and ``wall_clock`` stamps the cards/manifest,
    so tests can pass a fake clock while replay uses the fixed :data:`REPLAY_NOW`.
    """
    paths: Paths = resolve_paths(
        models=models_path,
        items=items_path,
        library=library_path,
        groups=groups_path,
        recordings=recordings_path,
        prices=prices_path,
        checksums=checksums_path,
    )
    settings = load_model_settings(paths.models)
    if not settings:
        msg = f"{paths.models}: no models locked"
        raise ValueError(msg)
    items = load_eval(paths.items)
    if limit is not None:
        if limit < 0:
            msg = "limit must not be negative"
            raise ValueError(msg)
        items = items[:limit]
    library = load_library(paths.library)
    groups = load_group_descriptions(paths.groups)
    keywords = load_safety_keywords()
    rulebook = load_rulebook()
    condition_keywords = _condition_keywords(Path("data/condition_keywords.toml"))

    if index is None:
        resolved_index, resolved_embedder = resolve_index(paths, embedder=embedder)
    else:
        resolved_index, resolved_embedder = index, embedder
    if resolved_index is None:
        resolved_index = empty_index()

    state = _run_state(out_dir, run_id)
    state.run_dir.mkdir(parents=True, exist_ok=True)
    existing = load_cards(state.cards_file)
    done = {(card.model_id, card.complaint.id) for card in existing}
    recorded = read_calls(calls_path(paths.recordings))
    calls = _calls_for_run(recorded, run_id)
    schedule = _read_schedule(state.schedule_file)
    if mode is RunMode.REPLAY and not schedule:
        # A replay regenerates the plan from the committed calls, so `rm -rf results`
        # followed by `make all` writes the same schedule file again.
        schedule = {
            model.model_id: sum(1 for key in calls if key[0] == model.model_id)
            for model in settings
        }
        schedule = {model: count for model, count in schedule.items() if count}

    budget = load_budget(budget_path)
    is_replay = mode is RunMode.REPLAY
    stamp = REPLAY_NOW if is_replay else (wall_clock or (lambda: datetime.now(UTC)))()
    start_stamp = stamp
    factory = client_factory or (
        lambda setting: ChatClient(
            setting,
            mode=mode,
            recordings=paths.recordings,
            budget_path=budget_path,
            prices_path=paths.prices,
        )
    )

    # The cap covers every paid call in the recordings - probes and the smoke run too,
    # not only the rows this run id owns. Replay spends nothing, so it keeps its own run.
    paid = calls if is_replay else recorded
    spent = sum(
        float(row["cost_usd"])
        for row in paid.values()
        if isinstance(row.get("cost_usd"), (int, float))
    )

    try:
        for setting in settings:
            recorded_plan = bool(calls) and is_replay
            planned = schedule.get(setting.model_id)
            # The recorded plan is a prefix of the item list: honour it instead of
            # re-estimating the items the PLAN section 8 cut removed.
            scheduled_items = items[:planned] if planned is not None else items
            remaining = [
                item
                for item in scheduled_items
                if (setting.model_id, item.id) not in done
                and ((setting.model_id, item.id) in calls if recorded_plan else True)
            ]
            if not remaining:
                continue
            if not is_replay:
                estimated = estimate_cost_usd(setting, len(remaining), paths.prices)
                if spent + estimated > budget.hard_cap_usd:
                    if setting.role == "comparison" and len(remaining) > COMPARISON_REDUCED_ITEMS:
                        remaining = remaining[:COMPARISON_REDUCED_ITEMS]
                        done_for_model = sum(1 for model, _ in done if model == setting.model_id)
                        schedule[setting.model_id] = done_for_model + len(remaining)
                        _write_schedule(state.schedule_file, schedule)
                        estimated = estimate_cost_usd(setting, len(remaining), paths.prices)
                    if spent + estimated > budget.hard_cap_usd:
                        msg = (
                            f"budget guard: {setting.model_id!r} would cost about "
                            f"USD {estimated:.2f} on {len(remaining)} items with "
                            f"USD {spent:.2f} already spent against the "
                            f"USD {budget.hard_cap_usd:.2f} cap"
                        )
                        raise BudgetExceededError(msg)
                per_item = estimated / len(remaining) if remaining else 0.0
            else:
                per_item = 0.0

            client = factory(setting)
            try:
                for item in remaining:
                    if not is_replay and spent + per_item > budget.hard_cap_usd:
                        msg = (
                            f"budget guard: the next {setting.model_id!r} call would "
                            f"cross the USD {budget.hard_cap_usd:.2f} cap"
                        )
                        raise BudgetExceededError(msg)
                    card, stats = triage_item(
                        item,
                        client=client,
                        library=library,
                        rulebook=rulebook,
                        groups=groups,
                        keywords=keywords,
                        index=resolved_index,
                        embedder=resolved_embedder,
                        now=stamp,
                        clock=clock,
                    )
                    _append_card(state.cards_file, card)
                    done.add((setting.model_id, item.id))
                    if not is_replay:
                        row = _call_row(setting, item.id, stats, run_id=run_id)
                        _append_call(calls_path(paths.recordings), row)
                        calls[(setting.model_id, item.id)] = row
                        if isinstance(stats.cost_usd, (int, float)):
                            spent += float(stats.cost_usd)
                        else:
                            spent += per_item
            finally:
                close = getattr(client, "close", None)
                if callable(close):
                    close()

        all_cards = _sort_cards(load_cards(state.cards_file), items, settings)
        _rewrite_cards(state.cards_file, all_cards)

        # Record the plan actually executed (400 primary / 200 comparison for the live
        # run). Replay regenerates it from the committed calls; a record run writes it
        # at the cut too, so a crash before the end still leaves the cut on disk.
        if calls:
            executed = {
                setting.model_id: sum(1 for key in calls if key[0] == setting.model_id)
                for setting in settings
            }
            _write_schedule(
                state.schedule_file,
                {model: count for model, count in executed.items() if count},
            )

        finished = REPLAY_NOW if is_replay else (wall_clock or (lambda: datetime.now(UTC)))()
        total_cost = sum(
            float(row["cost_usd"])
            for row in calls.values()
            if isinstance(row.get("cost_usd"), (int, float))
        )
        known_costs = any(isinstance(row.get("cost_usd"), (int, float)) for row in calls.values())
        manifest = RunManifest(
            run_id=run_id,
            mode=mode,
            models=settings,
            sample_hash=_sample_hash(paths.items),
            item_count=len(items),
            started_at=start_stamp,
            finished_at=finished,
            cost_usd=total_cost if known_costs else None,
            schema_version=SCHEMA_VERSION,
        )

        metrics_payload: dict[str, Any] = {
            "run_id": run_id,
            "mode": mode.value,
            "fixture": paths.fixture,
            "item_count": len(items),
            "models": {
                setting.model_id: _model_metrics(
                    [card for card in all_cards if card.model_id == setting.model_id],
                    items,
                    calls=calls,
                    condition_keywords=condition_keywords,
                    settings=setting,
                    prices_path=paths.prices,
                    estimate_items=len(items),
                )
                for setting in settings
            },
            "budget": _budget_report(
                settings,
                all_cards,
                items=len(items),
                cap=budget.hard_cap_usd,
                calls=calls,
                prices_path=paths.prices,
            ),
        }
        _write_json(state.metrics_file, metrics_payload)
        _write_json(state.manifest_file, manifest.model_dump(mode="json"))
        return manifest
    except (BudgetExceededError, LlmError):
        # Leave a manifest that says the run did not finish; the cards already on disk
        # stay usable and a later run resumes from them.
        try:
            _write_json(
                state.manifest_file,
                {
                    "run_id": run_id,
                    "mode": mode.value,
                    "models": [model.model_dump(mode="json") for model in settings],
                    "sample_hash": _sample_hash(paths.items),
                    "item_count": len(items),
                    "started_at": start_stamp.isoformat(),
                    "finished_at": None,
                    "cost_usd": None,
                    "schema_version": SCHEMA_VERSION,
                    "incomplete": True,
                },
            )
        finally:
            raise
