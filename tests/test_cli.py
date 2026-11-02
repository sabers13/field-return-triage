"""The CLI command tree: every lane command is listed and its options are wired."""

from __future__ import annotations

import pytest
from rich.text import Text
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


@pytest.mark.parametrize("force_color", [False, True])
def test_eval_lists_its_models_and_run_id_options(
    monkeypatch: pytest.MonkeyPatch, force_color: bool
) -> None:
    if force_color:
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("FORCE_COLOR", "1")
    else:
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("FORCE_COLOR", raising=False)
    result = runner.invoke(app, ["eval", "--help"])
    assert result.exit_code == 0
    output = Text.from_ansi(result.output).plain
    assert "--models" in output
    assert "--run-id" in output
    assert "--mode" in output


def test_eval_rejects_an_unknown_mode() -> None:
    result = runner.invoke(app, ["eval", "--mode", "live"])
    assert result.exit_code != 0
    assert "Invalid value" in combined_output(result)
