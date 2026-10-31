"""End-to-end ``make trend`` behaviour on temporary tables."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
import typer
from trend_support import START, key, mondays, recall, weekly
from typer.testing import CliRunner

from field_return_triage.cli import app
from field_return_triage.trend.cli import trend_main

HEADER = "make,model,model_year,group,week,count\n"


def _write_weekly(
    path: Path, rows: list[tuple[object, object, object, object, object, object]]
) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(HEADER)
        for row in rows:
            handle.write(",".join(str(value) for value in row) + "\n")


def _weekly_rows(items: list[tuple[object, list[int]]]) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for series, values in items:
        for row in weekly(series, values):
            rows.append(
                (
                    row.series.make,
                    row.series.model,
                    row.series.model_year,
                    row.series.group,
                    row.week,
                    row.count,
                )
            )
    return rows


def _recalls(path: Path, rows: list[tuple[str, str, str, int, str, str]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("recall_id,make,model,model_year,group,report_date\n")
        for row in rows:
            handle.write(",".join(str(value) for value in row) + "\n")


def _tables(tmp_path: Path) -> tuple[Path, Path]:
    item = key()
    rows = _weekly_rows([(item, [1] * 26 + [12])])
    weekly_path = tmp_path / "weekly.csv.gz"
    _write_weekly(weekly_path, rows)
    recalls_path = tmp_path / "recalls.csv"
    _recalls(
        recalls_path,
        [("R-1", item.make, item.model, item.model_year, item.group, "2020-08-12")],
    )
    return weekly_path, recalls_path


def test_trend_main_writes_the_three_files(tmp_path: Path) -> None:
    weekly_path, recalls_path = _tables(tmp_path)
    results = tmp_path / "results"
    trend_main(weekly_path=weekly_path, recalls_path=recalls_path, results_dir=results)

    alerts = json.loads((results / "alerts.json").read_text(encoding="utf-8"))
    assert alerts["count"] == 1
    assert alerts["series_with_alerts"] == 1
    assert alerts["alerts"][0]["week"] == mondays(27)[-1].isoformat()
    assert alerts["alerts"][0]["count"] == 12

    backtest = json.loads((results / "backtest.json").read_text(encoding="utf-8"))
    assert backtest["alerts"]["total"] == 1
    assert backtest["alerts"]["preceding_recall"] == 1
    assert backtest["alerts"]["share"] == 1.0
    assert backtest["alerts"]["weak_join"] is True
    assert backtest["base_rate"]["draws"] == 1
    assert backtest["base_rate"]["seed"] == 20261031
    assert set(backtest["base_rate"]["ci95"]) == {"low", "high"}

    example = json.loads((results / "example_series.json").read_text(encoding="utf-8"))
    assert example["available"] is True
    assert example["series"]["make"] == "Acme"
    assert example["alert"]["count"] == 12
    assert example["recall"]["recall_id"] == "R-1"
    assert len(example["weeks"]) == 27


def test_trend_main_is_byte_identical_on_a_rerun(tmp_path: Path) -> None:
    weekly_path, recalls_path = _tables(tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    trend_main(weekly_path=weekly_path, recalls_path=recalls_path, results_dir=first)
    trend_main(weekly_path=weekly_path, recalls_path=recalls_path, results_dir=second)
    for name in ("alerts.json", "backtest.json", "example_series.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_trend_main_reports_an_unavailable_example(tmp_path: Path) -> None:
    item = key()
    weekly_path = tmp_path / "weekly.csv.gz"
    _write_weekly(weekly_path, _weekly_rows([(item, [0] * 26 + [5])]))
    recalls_path = tmp_path / "recalls.csv"
    _recalls(
        recalls_path, [("R-1", item.make, item.model, item.model_year, item.group, "2020-08-12")]
    )
    results = tmp_path / "results"
    trend_main(weekly_path=weekly_path, recalls_path=recalls_path, results_dir=results)
    example = json.loads((results / "example_series.json").read_text(encoding="utf-8"))
    assert example["available"] is False
    assert example["series"] is None
    assert "at least 20" in example["reason"]


def test_trend_main_fails_cleanly_without_data(tmp_path: Path) -> None:
    with pytest.raises(typer.Exit) as raised:
        trend_main(
            weekly_path=tmp_path / "missing.csv.gz",
            recalls_path=tmp_path / "missing.csv",
            results_dir=tmp_path / "results",
        )
    assert raised.value.exit_code == 1


def test_trend_main_fails_cleanly_on_a_bad_table(tmp_path: Path) -> None:
    weekly_path = tmp_path / "weekly.csv"
    weekly_path.write_text("make,model,mystery\n", encoding="utf-8")
    recalls_path = tmp_path / "recalls.csv"
    _recalls(recalls_path, [])
    with pytest.raises(typer.Exit) as raised:
        trend_main(weekly_path=weekly_path, recalls_path=recalls_path, results_dir=tmp_path / "r")
    assert raised.value.exit_code == 1


def test_trend_main_fails_cleanly_on_an_empty_table(tmp_path: Path) -> None:
    weekly_path = tmp_path / "weekly.csv"
    weekly_path.write_text(HEADER, encoding="utf-8")
    recalls_path = tmp_path / "recalls.csv"
    _recalls(recalls_path, [])
    with pytest.raises(typer.Exit) as raised:
        trend_main(weekly_path=weekly_path, recalls_path=recalls_path, results_dir=tmp_path / "r")
    assert raised.value.exit_code == 1


def test_the_frt_trend_command_dispatches_to_the_lane(tmp_path: Path) -> None:
    weekly_path, recalls_path = _tables(tmp_path)
    results = tmp_path / "results"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["trend"],
        env={
            "FRT_TREND_WEEKLY": str(weekly_path),
            "FRT_TREND_RECALLS": str(recalls_path),
            "FRT_TREND_RESULTS": str(results),
        },
    )
    assert result.exit_code == 0, result.output
    assert "1 alerts" in result.output
    assert (results / "alerts.json").is_file()


def test_a_recall_helper_can_anchor_the_window() -> None:
    assert recall(START, 0).report_date == START
