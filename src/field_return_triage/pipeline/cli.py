"""The pipeline command surface: ``frt triage``, ``frt eval`` and ``make results``.

The root command tree dispatches to :func:`triage_main` and :func:`eval_main`
(``docs/INTERFACES.md`` section 1). ``python -m field_return_triage.pipeline.cli``
carries the make targets that are not user commands: ``results``, ``data-check``,
``index-cached`` and ``eval-replay``.

A library module never prints; this file does, because it is a terminal surface.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import typer

from field_return_triage.contracts import ModelSetting, RunMode
from field_return_triage.data.io import load_eval, load_library
from field_return_triage.extract.parse import parse_extraction
from field_return_triage.extract.prompt import build_messages
from field_return_triage.extract.schema import ExtractionAnswer
from field_return_triage.llm import policy
from field_return_triage.llm.client import ChatClient
from field_return_triage.llm.errors import LlmError, PolicyStopError
from field_return_triage.llm.settings import load_model_settings
from field_return_triage.pipeline.baseline import (
    load_condition_keywords,
    run_baselines,
    write_baselines,
)
from field_return_triage.pipeline.config import (
    Paths,
    load_group_descriptions,
    resolve_index,
    resolve_paths,
)
from field_return_triage.pipeline.data_check import check_data
from field_return_triage.pipeline.run import BudgetExceededError, calls_path, run_eval
from field_return_triage.pipeline.summary import write_manifest, write_summary
from field_return_triage.pipeline.triage import render_card, triage_text
from field_return_triage.rules.keywords import load_safety_keywords
from field_return_triage.rules.rulebook import load_rulebook
from field_return_triage.similar.embedder import default_embedder
from field_return_triage.similar.index import build_index, index_path, load_index

__all__ = [
    "PROBES_FILE",
    "app",
    "data_check_main",
    "eval_main",
    "index_cached_main",
    "live_main",
    "probe_main",
    "results_main",
    "triage_main",
]

RESULTS_DIR: Final[Path] = Path("results")
RUN_ID_ENV: Final[str] = "FRT_RUN_ID"
RUNS_DIR_ENV: Final[str] = "FRT_RUNS_DIR"

#: One probe call per locked model, written next to the recordings (owned by lane R7).
PROBES_FILE: Final[str] = "probes.json"

#: The calls sidecar tag for a probe call; a probe is not an evaluation item.
PROBE_RUN_ID: Final[str] = "probe"
PROBE_COMPLAINT_ID: Final[str] = "__probe__"


def _runs_dir() -> Path:
    from_env = os.environ.get(RUNS_DIR_ENV)
    return Path(from_env) if from_env else RESULTS_DIR / "runs"


def _run_id(explicit: str | None, paths: Paths) -> str:
    if explicit:
        return explicit
    from_env = os.environ.get(RUN_ID_ENV)
    if from_env:
        return from_env
    return "fixture" if paths.fixture else "live"


def _announce(paths: Paths) -> None:
    if paths.fixture:
        typer.echo(f"frt: {paths.describe()}", err=True)


def triage_main(source: str) -> None:
    """``frt triage FILE|-``: one complaint through the flow, JSON plus a text view."""
    try:
        if source == "-":
            text = sys.stdin.read()
            complaint_id = "stdin"
        else:
            path = Path(source)
            text = path.read_text(encoding="utf-8")
            complaint_id = path.stem or "cli"

        paths = resolve_paths()
        _announce(paths)
        settings = load_model_settings(paths.models)
        setting = next(
            (model for model in settings if model.role == "primary"),
            settings[0],
        )
        index, embedder = resolve_index(paths)
        client = ChatClient(
            setting,
            mode=RunMode.REPLAY,
            recordings=paths.recordings,
            prices_path=paths.prices,
        )
        try:
            card = triage_text(
                text,
                complaint_id=complaint_id,
                client=client,
                library=load_library(paths.library),
                rulebook=load_rulebook(),
                groups=load_group_descriptions(paths.groups),
                keywords=load_safety_keywords(),
                index=index,
                embedder=embedder,
                now=datetime.now(UTC),
            )
        finally:
            client.close()
    except (LlmError, OSError, ValueError) as exc:
        typer.echo(f"frt triage: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        json.dumps(card.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
    )
    typer.echo("")
    typer.echo(render_card(card))


def eval_main(
    mode: str = "replay",
    models: str | Path | None = None,
    run_id: str | None = None,
    limit: int | None = None,
) -> None:
    """``frt eval --mode replay|record``: run the evaluation set through the pipeline."""
    try:
        run_mode = RunMode(mode)
    except ValueError:
        typer.echo(f"frt eval: unknown mode {mode!r}; use replay or record", err=True)
        raise typer.Exit(code=2) from None

    model_path = Path(models) if models is not None else None
    try:
        paths = resolve_paths(models=model_path)
        _announce(paths)
        chosen = _run_id(run_id, paths)
        manifest = run_eval(
            mode=run_mode,
            models_path=paths.models,
            run_id=chosen,
            items_path=paths.items,
            out_dir=_runs_dir(),
            limit=limit,
            library_path=paths.library,
            groups_path=paths.groups,
            recordings_path=paths.recordings,
            prices_path=paths.prices,
            checksums_path=paths.checksums,
        )
    except (BudgetExceededError, LlmError, OSError, ValueError) as exc:
        typer.echo(f"frt eval: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    cost = "unknown" if manifest.cost_usd is None else f"USD {manifest.cost_usd:.4f}"
    typer.echo(
        f"frt eval: run {manifest.run_id} ({manifest.mode.value}) on "
        f"{manifest.item_count} items, cost {cost} -> "
        f"{_runs_dir() / manifest.run_id}"
    )


def _live_paths() -> Paths:
    """The real inputs, refusing fixture mode: a paid run needs the locked models."""
    paths = resolve_paths()
    if paths.fixture:
        typer.echo(
            "frt live: config/models.lock.toml is missing, so only the fixture lock "
            "is available; lock the models before a paid run",
            err=True,
        )
        raise typer.Exit(code=1)
    return paths


def _run_budget(run_dir: Path) -> dict[str, Any]:
    """The budget block a finished run wrote, or an empty one."""
    path = run_dir / "metrics.json"
    if not path.is_file():
        return {}
    try:
        metrics: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    budget = metrics.get("budget") if isinstance(metrics, dict) else None
    return budget if isinstance(budget, dict) else {}


def live_main(run_id: str = "live", limit: int | None = None) -> None:
    """``make live``: the one paid record-mode run (PLAN.md sections 7 and 8).

    The run is resumable and the budget guard stops before the cap. On a policy answer
    the client latches the process-wide stop and writes ``reports/STOP.md``; this exit
    code is then 3 and no later call is made. ``limit`` keeps the first N items, which
    the smoke step uses (``--limit 20``).
    """
    paths = _live_paths()
    try:
        locked = load_model_settings(paths.models)
        manifest = run_eval(
            mode=RunMode.RECORD,
            models_path=paths.models,
            run_id=run_id,
            items_path=paths.items,
            out_dir=_runs_dir(),
            limit=limit,
            library_path=paths.library,
            groups_path=paths.groups,
            recordings_path=paths.recordings,
            prices_path=paths.prices,
            checksums_path=paths.checksums,
        )
    except PolicyStopError as exc:
        typer.echo(
            f"frt live: policy stop, every call is stopped: {exc} (see reports/STOP.md)",
            err=True,
        )
        raise typer.Exit(code=3) from exc
    except (BudgetExceededError, LlmError, OSError, ValueError) as exc:
        typer.echo(f"frt live: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    run_dir = _runs_dir() / manifest.run_id
    budget = _run_budget(run_dir)
    roles = ", ".join(f"{model.model_id} ({model.role})" for model in locked)
    cost = "unknown" if manifest.cost_usd is None else f"USD {manifest.cost_usd:.4f}"
    typer.echo(
        f"frt live: run {manifest.run_id} on {manifest.item_count} items; "
        f"models {roles}; spend {cost}"
    )
    spent = budget.get("spent_usd")
    cap = budget.get("cap_usd")
    if isinstance(spent, (int, float)) and isinstance(cap, (int, float)):
        typer.echo(f"frt live: spend USD {float(spent):.4f} against the USD {float(cap):.2f} cap")
    for entry in budget.get("models", []):
        if not isinstance(entry, dict):
            continue
        reduced = " (budget cut)" if entry.get("reduced") else ""
        typer.echo(
            f"frt live: {entry.get('model_id')} {entry.get('items_run')}/"
            f"{entry.get('items_available')} items{reduced}"
        )
    typer.echo(f"frt live: run directory {run_dir}")


def _append_call_row(path: Path, row: dict[str, Any]) -> None:
    """Append one call row to the recordings sidecar (the runner owns the format)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def _probe_row(
    setting: ModelSetting,
    *,
    ok: bool,
    duration_ms: float,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: float | None = None,
    failure: str | None = None,
) -> dict[str, Any]:
    return {
        "role": setting.role,
        "model_id": setting.model_id,
        "base_url": setting.base_url,
        "ok": ok,
        "duration_ms": round(duration_ms, 3),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "failure": failure,
    }


def probe_main() -> None:
    """One paid call per locked model on the gateway's OpenAI-compatible endpoint.

    Each probe sends the real first-item prompt with the structured-output schema, so it
    exercises the same request shape the run will use. The outcome (schema validity,
    tokens, cost, latency) goes to ``recordings/probes.json``; a model that fails here
    falls back to its native format per PLAN.md section 7, logged in ``reports/RUN.md``.
    """
    paths = _live_paths()
    try:
        locked = load_model_settings(paths.models)
        items = load_eval(paths.items)
        groups = load_group_descriptions(paths.groups)
    except (LlmError, OSError, ValueError) as exc:
        typer.echo(f"frt probe: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if not items:
        typer.echo("frt probe: the evaluation set is empty", err=True)
        raise typer.Exit(code=1)

    messages = build_messages(items[0], groups)
    rows: list[dict[str, Any]] = []
    stopped = False
    for setting in locked:
        client = ChatClient(
            setting,
            mode=RunMode.RECORD,
            recordings=paths.recordings,
            prices_path=paths.prices,
        )
        started = time.monotonic()
        try:
            reply = client.complete(messages, schema=ExtractionAnswer)
            duration_ms = (time.monotonic() - started) * 1000.0
            _, reason = parse_extraction(reply.content)
            row = _probe_row(
                setting,
                ok=reason is None,
                duration_ms=duration_ms,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                cost_usd=reply.cost_usd,
                failure=reason,
            )
            _append_call_row(
                calls_path(paths.recordings),
                {
                    "run_id": PROBE_RUN_ID,
                    "model_id": setting.model_id,
                    "complaint_id": PROBE_COMPLAINT_ID,
                    "prompt_version": reply.prompt_version,
                    "input_tokens": reply.input_tokens,
                    "output_tokens": reply.output_tokens,
                    "cost_usd": reply.cost_usd,
                    "duration_ms": round(duration_ms, 3),
                    "failure": reason,
                },
            )
        except LlmError as exc:
            duration_ms = (time.monotonic() - started) * 1000.0
            row = _probe_row(
                setting,
                ok=False,
                duration_ms=duration_ms,
                failure=str(exc),
            )
            stopped = isinstance(exc, PolicyStopError) or policy.stop_reason() is not None
        finally:
            client.close()

        rows.append(row)
        state = "ok" if row["ok"] else f"FAILED: {row['failure']}"
        typer.echo(f"frt probe: {setting.model_id} ({setting.role}): {state}")
        if stopped:
            typer.echo("frt probe: policy stop; no further calls (see reports/STOP.md)", err=True)
            break

    payload = {
        "probed_at": datetime.now(UTC).isoformat(),
        "endpoint": locked[0].base_url + "/chat/completions",
        "models": rows,
    }
    path = paths.recordings / PROBES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    typer.echo(f"frt probe: outcomes -> {path}")
    if not all(row["ok"] for row in rows):
        raise typer.Exit(code=3 if stopped else 1)


def results_main(
    models: str | Path | None = None,
    run_id: str | None = None,
) -> None:
    """``make results``: replay eval, baselines, SUMMARY.md and MANIFEST.sha256."""
    model_path = Path(models) if models is not None else None
    try:
        paths = resolve_paths(models=model_path)
        _announce(paths)
        chosen = _run_id(run_id, paths)
        run_eval(
            mode=RunMode.REPLAY,
            models_path=paths.models,
            run_id=chosen,
            items_path=paths.items,
            out_dir=_runs_dir(),
            library_path=paths.library,
            groups_path=paths.groups,
            recordings_path=paths.recordings,
            prices_path=paths.prices,
            checksums_path=paths.checksums,
        )

        items = load_eval(paths.items)
        library = load_library(paths.library)
        payload = run_baselines(
            items,
            library,
            safety_keywords=load_safety_keywords(),
            condition_keywords=load_condition_keywords(),
        )
        paths_written = write_baselines(payload, RESULTS_DIR / "baseline")
        summary = write_summary(results_dir=RESULTS_DIR)
        manifest = write_manifest(RESULTS_DIR)
    except (BudgetExceededError, LlmError, OSError, ValueError) as exc:
        typer.echo(f"frt results: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"frt results: {len(paths_written)} baseline files, {summary.name} and "
        f"{manifest.name} -> {RESULTS_DIR} (run {chosen})"
    )


def data_check_main() -> None:
    """``make data-check``: verify every committed data file against CHECKSUMS.txt."""
    result = check_data()
    if not result.ok:
        for failure in result.failures:
            typer.echo(f"frt data-check: {failure}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"frt data-check: {result.checked} committed data files match CHECKSUMS.txt")


def index_cached_main() -> None:
    """``make index-cached``: reuse the embedding index, build it only when missing."""
    paths = resolve_paths()
    if paths.fixture:
        _announce(paths)
        typer.echo("frt index-cached: fixture mode uses the in-process hashing index")
        return
    try:
        ids, _ = load_index(index_path(paths.checksums))
    except (FileNotFoundError, ValueError):
        library = load_library(paths.library)
        path = build_index(library, embedder=default_embedder(), checksums=paths.checksums)
        typer.echo(f"frt index-cached: embedded {len(library)} complaints -> {path}")
        return
    typer.echo(f"frt index-cached: reusing the cached index for {len(ids)} complaints")


app = typer.Typer(
    name="frt-pipeline",
    help="Pipeline make targets for field-return-triage.",
    add_completion=False,
)


@app.command("results")
def _results_command() -> None:
    """Replay the eval set, then write the baselines, summary and manifest."""
    results_main()


@app.command("data-check")
def _data_check_command() -> None:
    """Verify the committed data against data/CHECKSUMS.txt."""
    data_check_main()


@app.command("index-cached")
def _index_cached_command() -> None:
    """Reuse the embedding index, or build it when it is missing."""
    index_cached_main()


@app.command("eval-replay")
def _eval_replay_command() -> None:
    """Score the evaluation set from the committed recordings."""
    eval_main("replay")


@app.command("live")
def _live_command(
    run_id: str = typer.Option(
        "live",
        "--run-id",
        metavar="ID",
        help="Results directory name under results/runs/.",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        metavar="N",
        min=1,
        help="Keep the first N items (the smoke step); default is every item.",
    ),
) -> None:
    """The one paid record-mode run (lane R7); resumable and budget-guarded."""
    live_main(run_id=run_id, limit=limit)


@app.command("probe")
def _probe_command() -> None:
    """One paid call per locked model, recorded to recordings/probes.json (lane R7)."""
    probe_main()


if __name__ == "__main__":  # pragma: no cover - make entry point
    app()
