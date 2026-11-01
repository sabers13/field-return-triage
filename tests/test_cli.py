"""The CLI command tree: every lane command is listed and its options are wired."""

from __future__ import annotations

from typer.testing import CliRunner, Result

from field_return_triage import __version__
from field_return_triage.cli import app

runner = CliRunner()

#: Every command the CLI must list, and the lane that owns it.
COMMANDS = {
    "data": "R1",
    "index": "R3",
    "triage": "R6",
    "eval": "R6",
    "review": "R4",
    "trend": "R5",
}


def combined_output(result: Result) -> str:
    return (result.output or "") + getattr(result, "stderr", "")


def test_version_prints_and_exits_zero() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_lists_every_lane_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in COMMANDS:
        assert command in result.output


def test_eval_lists_its_models_and_run_id_options() -> None:
    result = runner.invoke(app, ["eval", "--help"])
    assert result.exit_code == 0
    assert "--models" in result.output
    assert "--run-id" in result.output
    assert "--mode" in result.output


def test_eval_rejects_an_unknown_mode() -> None:
    result = runner.invoke(app, ["eval", "--mode", "live"])
    assert result.exit_code != 0
    assert "Invalid value" in combined_output(result)
