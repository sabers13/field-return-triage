"""``make all`` on fixtures, twice, byte for byte."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline_support import fixture_items, fixture_library, fixture_paths

from field_return_triage.contracts import RunMode
from field_return_triage.pipeline.baseline import (
    load_condition_keywords,
    run_baselines,
    write_baselines,
)
from field_return_triage.pipeline.data_check import check_data
from field_return_triage.pipeline.run import run_eval
from field_return_triage.pipeline.summary import write_manifest, write_summary
from field_return_triage.rules.keywords import load_safety_keywords
from field_return_triage.trend.cli import trend_main


def _build(root: Path) -> None:
    """The `make all` chain on the committed data and the fixture recordings."""
    result = check_data()
    assert result.ok, result.failures

    trend_main(results_dir=root / "trend")

    paths = fixture_paths()
    run_eval(
        mode=RunMode.REPLAY,
        models_path=paths.models,
        run_id="fixture",
        items_path=paths.items,
        out_dir=root / "runs",
        library_path=paths.library,
        groups_path=paths.groups,
        recordings_path=paths.recordings,
        prices_path=paths.prices,
        checksums_path=paths.checksums,
    )
    payload = run_baselines(
        fixture_items(),
        fixture_library(),
        safety_keywords=load_safety_keywords(),
        condition_keywords=load_condition_keywords(),
    )
    write_baselines(payload, root / "baseline")
    write_summary(runs_dir=root / "runs", results_dir=root)
    write_manifest(root)


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_make_all_on_fixtures_is_byte_identical_twice(tmp_path: Path) -> None:
    root = tmp_path / "results"
    _build(root)
    first = _tree(root)
    assert "SUMMARY.md" in first
    assert "MANIFEST.sha256" in first
    assert "runs/fixture/cards.jsonl" in first
    assert "runs/fixture/metrics.json" in first
    assert "baseline/group.json" in first
    assert "trend/backtest.json" in first

    _build(root)
    second = _tree(root)
    assert first == second

    summary = first["SUMMARY.md"].decode("utf-8")
    assert "Fixture run" in summary
    assert "`fixture-primary`" in summary
    assert "Alerts:" in summary
    assert "results/runs/fixture/metrics.json" in summary


def test_make_all_produces_two_identical_directories(tmp_path: Path) -> None:
    left, right = tmp_path / "left", tmp_path / "right"
    _build(left)
    _build(right)
    assert _tree(left) == _tree(right)


def test_the_manifest_lists_every_other_file_sorted(tmp_path: Path) -> None:
    root = tmp_path / "results"
    (root / "b").mkdir(parents=True)
    (root / "b" / "two.json").write_text("{}\n", encoding="utf-8")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    path = write_manifest(root)
    lines = path.read_text(encoding="utf-8").splitlines()
    names = [line.split("  ", 1)[1] for line in lines]
    assert names == ["a.txt", "b/two.json"]
    assert "MANIFEST.sha256" not in names
    first = path.read_bytes()
    write_manifest(root)
    assert path.read_bytes() == first


def test_a_changed_result_changes_one_manifest_line(tmp_path: Path) -> None:
    root = tmp_path / "results"
    root.mkdir(parents=True)
    target = root / "x.json"
    target.write_text(json.dumps({"value": 1}) + "\n", encoding="utf-8")
    write_manifest(root)
    before = (root / "MANIFEST.sha256").read_text(encoding="utf-8")
    target.write_text(json.dumps({"value": 2}) + "\n", encoding="utf-8")
    write_manifest(root)
    after = (root / "MANIFEST.sha256").read_text(encoding="utf-8")
    assert before != after
    assert len(before.splitlines()) == len(after.splitlines()) == 1
