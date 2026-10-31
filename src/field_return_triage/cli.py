"""The `frt` command line.

Wave 0 ships the command tree; later lanes own the command bodies. A lane adds
``src/field_return_triage/<lane>/cli.py`` with a named entry function, and this module
dispatches to it. A lane never edits this file, so no two lanes collide here.

Until a lane lands, its command prints ``not built yet (lane Rn)`` and exits with
status 2. That is deliberate: a stub must never look like a finished job.
"""

from __future__ import annotations

import importlib
from enum import StrEnum
from typing import Final, NoReturn

import typer

from field_return_triage import __version__

#: Command -> (module, entry function, owning lane). See ``docs/INTERFACES.md`` §1.
LANE_COMMANDS: Final[dict[str, tuple[str, str, str]]] = {
    "data": ("field_return_triage.data.cli", "data_main", "R1"),
    "index": ("field_return_triage.similar.cli", "index_main", "R3"),
    "triage": ("field_return_triage.pipeline.cli", "triage_main", "R6"),
    "eval": ("field_return_triage.pipeline.cli", "eval_main", "R6"),
    "review": ("field_return_triage.rules.cli", "review_main", "R4"),
    "trend": ("field_return_triage.trend.cli", "trend_main", "R5"),
}

app = typer.Typer(
    name="frt",
    help="Field Return Triage - which returned parts need a closer look, and which test first?",
    no_args_is_help=True,
    add_completion=False,
)


class EvalMode(StrEnum):
    """How `frt eval` gets its model answers."""

    REPLAY = "replay"
    RECORD = "record"


def _stub(lane: str) -> NoReturn:
    """Print the lane's stub message and exit non-zero."""
    typer.echo(f"frt: not built yet (lane {lane})", err=True)
    raise typer.Exit(code=2)


def _dispatch(command: str, *args: object) -> None:
    """Call the lane entry point for ``command``, or stub until the lane lands."""
    module_name, attribute, lane = LANE_COMMANDS[command]
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        # A missing lane package (or any parent of it) is the stub case. A missing
        # third-party dependency inside a lane module is a real bug and must surface.
        if missing and (module_name == missing or module_name.startswith(f"{missing}.")):
            _stub(lane)
        raise
    entry = getattr(module, attribute, None)
    if not callable(entry):
        _stub(lane)
    entry(*args)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"field-return-triage {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Print the version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Run a lane command; see `frt --help`."""


@app.command()
def data() -> None:
    """Fetch the NHTSA snapshot and derive the committed data files (lane R1)."""
    _dispatch("data")


@app.command()
def index() -> None:
    """Embed the library into the local vector cache (lane R3)."""
    _dispatch("index")


@app.command()
def triage(
    source: str = typer.Argument(
        ...,
        metavar="FILE|-",
        help="A file holding one complaint, or - to read the complaint from stdin.",
    ),
) -> None:
    """Triage one complaint into a card (lane R6)."""
    _dispatch("triage", source)


@app.command("eval")
def evaluate(
    mode: EvalMode = typer.Option(
        EvalMode.REPLAY,
        "--mode",
        help="replay committed recordings (no network) or record new answers.",
    ),
) -> None:
    """Run the evaluation set through the pipeline (lane R6)."""
    _dispatch("eval", mode.value)


@app.command()
def review() -> None:
    """Show one card and record the technician's decision (lane R4)."""
    _dispatch("review")


@app.command()
def trend() -> None:
    """Detect weekly complaint spikes and backtest them against recalls (lane R5)."""
    _dispatch("trend")
