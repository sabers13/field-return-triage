"""The pipeline command surface."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pipeline_support import FIXTURE_DIR, fixture_items
from typer.testing import CliRunner

from field_return_triage.cli import app
from field_return_triage.pipeline.cli import app as pipeline_app

runner = CliRunner()


def _fixture_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """R7 committed the real lock, so a test that wants fixtures names the fixture lock."""
    monkeypatch.setenv("FRT_MODELS", str(FIXTURE_DIR / "models.lock.toml"))


def test_triage_reads_a_file_and_prints_json_plus_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fixture_lock(monkeypatch)
    item = next(row for row in fixture_items() if row.id == "fx-001")
    complaint = tmp_path / "complaint.txt"
    complaint.write_text(item.narrative, encoding="utf-8")
    result = runner.invoke(app, ["triage", str(complaint)])
    assert result.exit_code == 0, result.output
    assert "battery_charging_12v" in result.output
    assert "Priority 2 (clear clues)" in result.output
    assert "A technician decides every case" in result.output
    json_text = result.output[result.output.index("{") : result.output.index("\n\n")]
    payload = json.loads(json_text)
    assert payload["complaint"]["id"] == "complaint"


def test_triage_reads_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fixture_lock(monkeypatch)
    item = next(row for row in fixture_items() if row.id == "fx-003")
    result = runner.invoke(app, ["triage", "-"], input=item.narrative)
    assert result.exit_code == 0, result.output
    assert "Priority 1 (safety)" in result.output


def test_triage_names_a_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["triage", str(tmp_path / "missing.txt")])
    assert result.exit_code == 1
    assert "frt triage" in (result.output + (result.stderr or ""))


def test_eval_writes_a_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRT_RUNS_DIR", str(tmp_path / "runs"))
    result = runner.invoke(
        app,
        [
            "eval",
            "--mode",
            "replay",
            "--models",
            str(FIXTURE_DIR / "models.lock.toml"),
            "--run-id",
            "cli",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "runs" / "cli" / "cards.jsonl").is_file()
    assert (tmp_path / "runs" / "cli" / "metrics.json").is_file()
    assert (tmp_path / "runs" / "cli" / "manifest.json").is_file()


def test_data_check_command_is_green() -> None:
    result = runner.invoke(pipeline_app, ["data-check"])
    assert result.exit_code == 0, result.output
    assert "match CHECKSUMS.txt" in result.output


def test_index_cached_is_a_no_op_in_fixture_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    _fixture_lock(monkeypatch)
    result = runner.invoke(pipeline_app, ["index-cached"])
    assert result.exit_code == 0, result.output
    assert "hashing index" in result.output
