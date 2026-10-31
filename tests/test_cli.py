"""The CLI ships as stubs: every command must name its lane and exit non-zero."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from field_return_triage import __version__
from field_return_triage.cli import app

runner = CliRunner()

#: command -> lane that will replace the stub.
STUBBED = {
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
    for command in STUBBED:
        assert command in result.output


@pytest.mark.parametrize(("command", "args"), [("data", []), ("trend", [])])
def test_simple_stubs_name_their_lane(command: str, args: list[str]) -> None:
    result = runner.invoke(app, [command, *args])
    assert result.exit_code == 2
    assert f"not built yet (lane {STUBBED[command]})" in combined_output(result)


def test_triage_takes_a_file_or_stdin_and_names_lane_r6(tmp_path: Path) -> None:
    complaint = tmp_path / "complaint.txt"
    complaint.write_text("The dashboard went dark after rain.\n", encoding="utf-8")
    for source in (str(complaint), "-"):
        result = runner.invoke(app, ["triage", source])
        assert result.exit_code == 2
        assert "not built yet (lane R6)" in combined_output(result)


def test_eval_defaults_to_replay_and_accepts_record() -> None:
    for args in (["eval"], ["eval", "--mode", "record"], ["eval", "--mode", "replay"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 2
        assert "not built yet (lane R6)" in combined_output(result)


def test_eval_rejects_an_unknown_mode() -> None:
    result = runner.invoke(app, ["eval", "--mode", "live"])
    assert result.exit_code != 0
    assert "Invalid value" in combined_output(result)
