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
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import typer

from field_return_triage.contracts import RunMode
from field_return_triage.data.io import load_eval, load_library
from field_return_triage.llm.client import ChatClient
from field_return_triage.llm.errors import LlmError
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
from field_return_triage.pipeline.run import BudgetExceededError, run_eval
from field_return_triage.pipeline.summary import write_manifest, write_summary
from field_return_triage.pipeline.triage import render_card, triage_text
from field_return_triage.rules.keywords import load_safety_keywords
from field_return_triage.rules.rulebook import load_rulebook
from field_return_triage.similar.embedder import default_embedder
from field_return_triage.similar.index import build_index, index_path, load_index

__all__ = [
    "app",
    "data_check_main",
    "eval_main",
    "index_cached_main",
    "results_main",
    "triage_main",
]

RESULTS_DIR: Final[Path] = Path("results")
RUN_ID_ENV: Final[str] = "FRT_RUN_ID"
RUNS_DIR_ENV: Final[str] = "FRT_RUNS_DIR"


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


if __name__ == "__main__":  # pragma: no cover - make entry point
    app()
